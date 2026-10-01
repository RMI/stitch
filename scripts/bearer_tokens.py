#!/usr/bin/env python3
"""Mint and inspect the two downstream bearer tokens.

    ./scripts/bearer_tokens.py mint                 # mint and write locally
    ./scripts/bearer_tokens.py mint --push          # also all three environments
    ./scripts/bearer_tokens.py mint --push staging  # just one
    ./scripts/bearer_tokens.py check                # report what the tokens carry
    ./scripts/bearer_tokens.py check --file ../stitch-etl/.env --min-hours 168

Run `mint` through `refresh_tokens.sh`, which widens the API's token lifetime and
turns the password grant on around the call, then puts both back. On its own
`mint` still works, but the tokens will only live as long as the API's current
setting allows.

Plain `password` would need a tenant Default Directory, which is unset here, so
the realm is named explicitly. No scope is requested: permissions come from RBAC
on the API regardless, and asking for `openid` would also make the token valid
against /userinfo for no benefit.

Service-account emails and subjects identify real privileged accounts, so they
are read from `SCRIPTS__<ACCOUNT>_EMAIL` and `SCRIPTS__<ACCOUNT>_SUB` in
`.env.scripts` instead of living in this file. Passwords stay in
`scripts/.env.auth0.pw` (chmod 600):

    ETL_PASSWORD=...
    LLM_PASSWORD=...

`mint` writes `scripts/.env.stitch-tokens` (0600) and never prints a token.
`check` exits non-zero when a token is expired, carries the wrong subject, or is
missing an expected permission, so it also doubles as a pre-share gate.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lib.env import load_script_env

DOMAIN = "rmi-spd.us.auth0.com"
AUDIENCE = "https://stitch-api.local"
CLIENT_ID = "TS1V1soQbccAV1sitFFCfUaIlSwHD2S2"
REALM = "Username-Password-Authentication"
REPO = "RMI/stitch"
ENVIRONMENTS = ("development", "staging", "production")
FRESH_SECONDS = 86400
EXTRA_PREFIX = "SCRIPTS__"

_DIR = Path(__file__).resolve().parent
PW_FILE = _DIR / ".env.auth0.pw"
DEFAULT_OUT = _DIR / ".env.stitch-tokens"

# `gh` on this machine is a zsh function wrapping `op plugin run`, and a script
# never sees it, so the plugin is invoked by name instead.
GH = ["op", "plugin", "run", "--", "gh"] if shutil.which("op") else ["gh"]

# Widening this to log a raw value, or raising http.client's debuglevel, would
# dump the password in the form body and the permissions in the token.
SENSITIVE = frozenset({"access_token", "id_token", "password", "refresh_token"})

logger = logging.getLogger("bearer")


@dataclass(frozen=True)
class Account:
    key: str
    var: str
    expected: frozenset[str]


# Dedupe reads every source before posting, so a missing source:read:<key> would
# silently re-post that dataset instead of failing.
ACCOUNTS = (
    Account(
        "etl",
        "STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN",
        frozenset(
            {
                "source:write",
                "source:read:alb",
                "source:read:bc",
                "source:read:ccr",
                "source:read:gem",
                "source:read:nor",
                "source:read:wm",
            }
        ),
    ),
    Account("llm", "STITCH_CLIENT_LLM_BEARER_TOKEN", frozenset({"resource:read"})),
)


def required_env(name: str) -> str:
    """One ``SCRIPTS__`` value from the env files, or exit naming the missing key."""
    key = f"{EXTRA_PREFIX}{name}"
    value = os.environ.get(key)
    if not value:
        sys.exit(
            f"{key} is not set. Add it to .env.scripts; see this script's docstring."
        )
    return value


def email_of(account: Account) -> str:
    return required_env(f"{account.key.upper()}_EMAIL")


def sub_of(account: Account) -> str:
    return required_env(f"{account.key.upper()}_SUB")


def redact(mapping: dict) -> dict:
    return {
        key: (f"<{len(str(value))} chars>" if key in SENSITIVE else value)
        for key, value in mapping.items()
    }


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    logger.info(
        "Read %d keys from %s: %s", len(values), path, ", ".join(sorted(values))
    )
    return values


def claims_of(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def reusable_tokens() -> dict[str, str] | None:
    """The tokens already on disk, if every one has more than a day left.

    Minting is the expensive half: it needs the passwords, and it makes
    refresh_tokens.sh widen the API lifetime and the client's grants. None of
    that is worth doing to re-push tokens that are still good.
    """
    if not DEFAULT_OUT.exists():
        logger.info("%s does not exist yet", DEFAULT_OUT)
        return None

    values = read_env_file(DEFAULT_OUT)
    now = datetime.now(timezone.utc).timestamp()
    tokens = {}
    for account in ACCOUNTS:
        token = values.get(account.var)
        if not token:
            logger.info("%s is absent from %s", account.var, DEFAULT_OUT)
            return None
        try:
            remaining = claims_of(token)["exp"] - now
        except (
            ValueError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
            binascii.Error,
        ) as exc:
            logger.info("%s is undecodable (%s)", account.var, exc)
            return None
        logger.info("%s has %.1fh left", account.var, remaining / 3600)
        if remaining <= FRESH_SECONDS:
            return None
        tokens[account.var] = token
    return tokens


def mint_one(account: Account, password: str) -> str:
    email, expected_sub = email_of(account), sub_of(account)
    form = {
        "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
        "client_id": CLIENT_ID,
        "realm": REALM,
        "audience": AUDIENCE,
        "username": email,
        "password": password,
    }
    url = f"https://{DOMAIN}/oauth/token"
    logger.info("[%s] password-realm as %s in %s", account.key, email, REALM)
    logger.info("[%s] POST %s", account.key, url)
    logger.debug("[%s] form %s", account.key, json.dumps(redact(form), sort_keys=True))

    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
            logger.info(
                "[%s] HTTP %s in %.2fs",
                account.key,
                response.status,
                time.monotonic() - started,
            )
            logger.debug(
                "[%s] reply %s", account.key, json.dumps(redact(body), sort_keys=True)
            )
            token = body["access_token"]
    except urllib.error.HTTPError as exc:
        logger.info(
            "[%s] HTTP %s in %.2fs", account.key, exc.code, time.monotonic() - started
        )
        sys.exit(
            f"[{account.key}] Auth0 refused: {exc.read().decode(errors='replace')[:300]}"
        )
    except urllib.error.URLError as exc:
        sys.exit(f"[{account.key}] Could not reach {url}: {exc}")

    claims = claims_of(token)
    logger.debug(
        "[%s] claims %s", account.key, json.dumps(redact(claims), sort_keys=True)
    )

    # A token for the wrong account authenticates fine and fails much later, as a
    # permission error pointing nowhere near the real cause.
    if claims.get("sub") != expected_sub:
        sys.exit(f"[{account.key}] sub is {claims.get('sub')}, expected {expected_sub}")

    granted = set(claims.get("permissions") or [])
    missing = sorted(account.expected - granted)
    seconds = claims["exp"] - claims["iat"]
    print(f"\n=== {account.key} -> {account.var} ===")
    print(
        f"expires     {datetime.fromtimestamp(claims['exp'], timezone.utc):%Y-%m-%d %H:%M} UTC"
    )
    print(f"lifetime    {seconds / 86400:.1f} days ({seconds}s)")
    print(f"permissions {len(granted)} granted, {len(missing)} missing")
    if missing:
        print(f"  missing: {', '.join(missing)}")
    return token


def push(tokens: dict[str, str], environments: list[str]) -> None:
    """Set both secrets on each GitHub environment, under the same names."""
    for environment in environments:
        for var, token in tokens.items():
            # Value on stdin, never argv, so it stays out of the process list.
            command = [*GH, "secret", "set", var, "--repo", REPO, "--env", environment]
            logger.info("Running: %s (value on stdin)", " ".join(command))
            started = time.monotonic()
            result = subprocess.run(
                command, input=token, text=True, capture_output=True
            )
            logger.info(
                "  exit %d in %.2fs", result.returncode, time.monotonic() - started
            )
            if result.returncode:
                hint = ""
                if "not accessible by personal access token" in result.stderr:
                    # Reading repos and environments needs no Secrets permission,
                    # so the token looks fine right up until this call.
                    hint = (
                        "\nThe token authenticated but lacks the Secrets permission. Add "
                        "Repository permissions -> Secrets: Read and write for "
                        f"{REPO}, and have an RMI owner approve it if the org requires that."
                    )
                sys.exit(
                    f"gh secret set {var} ({environment}): {result.stderr.strip()[:300]}{hint}"
                )
            print(f"  {environment:12} {var}")


def mint(args: argparse.Namespace) -> int:
    logger.info("Client %s, audience %s, realm %s", CLIENT_ID, AUDIENCE, REALM)

    tokens = None if args.force_auth0 else reusable_tokens()
    if args.force_auth0:
        logger.info("--force-auth0 given; not reusing %s", DEFAULT_OUT)

    # refresh_tokens.sh runs this first and only widens Auth0 when it says yes,
    # so every SCRIPTS__ key has to be resolved here, before the tenant is
    # touched, rather than part way through the mint.
    if args.needs_mint:
        for account in ACCOUNTS:
            email_of(account)
            sub_of(account)
        return 0 if tokens is None else 1

    if tokens:
        print(f"Tokens in {DEFAULT_OUT} still have over a day left; skipping Auth0.")
    else:
        logger.info("Minting: %s", ", ".join(a.key for a in ACCOUNTS))
        if not PW_FILE.exists():
            sys.exit(f"{PW_FILE} is missing (ETL_PASSWORD=, LLM_PASSWORD=)")
        passwords = read_env_file(PW_FILE)

        # Mint both before writing either, so a failure on the second account
        # cannot leave the output file half updated.
        tokens = {}
        for account in ACCOUNTS:
            password = passwords.get(f"{account.key.upper()}_PASSWORD")
            if not password:
                sys.exit(f"{account.key.upper()}_PASSWORD is not in {PW_FILE}")
            tokens[account.var] = mint_one(account, password)

        existed = DEFAULT_OUT.exists()
        descriptor = os.open(DEFAULT_OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write("".join(f"{var}={token}\n" for var, token in tokens.items()))
        logger.info("%s %s (0600)", "Overwrote" if existed else "Created", DEFAULT_OUT)
        print(f"\nWrote {', '.join(tokens)} to {DEFAULT_OUT} (0600).")

    # argparse gives None when --push is absent and [] when it is bare.
    if args.push is not None:
        environments = args.push or list(ENVIRONMENTS)
        print(f"\nSetting secrets on {REPO}:")
        push(tokens, environments)
    return 0


def describe(
    account: Account, token: str, now: datetime, args: argparse.Namespace
) -> list[str]:
    """Print one account's claims. Returns the problems found, empty if none."""
    problems = []
    try:
        claims = claims_of(token)
    except (ValueError, IndexError, json.JSONDecodeError, binascii.Error) as exc:
        return [f"{account.var} is undecodable ({exc})"]

    sub = claims.get("sub")
    granted = set(claims.get("permissions") or [])
    print(f"sub         {sub}")

    expiry, issued = claims.get("exp"), claims.get("iat")
    if isinstance(expiry, (int, float)):
        expires_at = datetime.fromtimestamp(expiry, tz=timezone.utc)
        hours = (expires_at - now).total_seconds() / 3600
        print(f"expires     {expires_at:%Y-%m-%d %H:%M} UTC ({hours:.1f}h left)")
        if isinstance(issued, (int, float)):
            seconds = int(expiry - issued)
            print(f"lifetime    {seconds / 86400:.1f} days ({seconds}s)")
        if hours <= 0:
            problems.append(f"{account.var} expired {-hours:.1f}h ago")
        elif hours < args.min_hours:
            print(
                f"  note: below the {args.min_hours:.0f}h floor; re-mint before sharing"
            )
    else:
        problems.append(f"{account.var} carries no exp claim")

    expected_sub = sub_of(account)
    if sub != expected_sub and not str(sub).endswith("@clients"):
        problems.append(f"{account.var} has sub {sub}, expected {expected_sub}")

    missing = sorted(account.expected - granted)
    print(f"permissions {len(granted)} granted, {len(missing)} missing")
    if missing:
        problems.append(f"{account.var} is missing {', '.join(missing)}")
    if not args.quiet:
        for name in sorted(granted):
            flag = "  " if name in account.expected else " +"
            print(f"           {flag}{name}")
        extra = sorted(granted - account.expected)
        if extra:
            print(
                f"  note: {len(extra)} permission(s) beyond what this account needs (+)"
            )
    return problems


def check(args: argparse.Namespace) -> int:
    if not args.file.exists():
        sys.exit(f"{args.file} does not exist. Run `bearer_tokens.py mint` first.")

    values = read_env_file(args.file)
    now = datetime.now(timezone.utc)
    accounts = [a for a in ACCOUNTS if not args.only or a.key == args.only]

    problems = []
    for account in accounts:
        print(f"\n=== {account.key} -> {account.var} ===")
        token = values.get(account.var)
        if not token:
            problems.append(f"{account.var} is not in {args.file}")
            print(f"  missing from {args.file}")
            continue
        problems.extend(describe(account, token, now, args))

    known = {a.var for a in ACCOUNTS}
    for name in sorted(set(values) - known):
        print(f"\nnote: {name} is in {args.file} but is not a known account")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"\nAll {len(accounts)} token(s) valid, in date, and fully permissioned.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # Shared via parents= so -v is accepted on either side of the subcommand;
    # declaring it on both parsers would let the subparser reset it to False.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log every step: files read, the grant, each request and reply, and each gh call",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    minter = subparsers.add_parser(
        "mint", parents=[shared], help="mint both tokens and write them locally"
    )
    minter.set_defaults(run=mint)
    minter.add_argument(
        "--push",
        nargs="*",
        choices=ENVIRONMENTS,
        metavar="ENV",
        help=f"also set both secrets on {REPO} environments "
        f"({', '.join(ENVIRONMENTS)}); bare --push means all of them",
    )
    minter.add_argument(
        "--force-auth0",
        action="store_true",
        help="mint even when the tokens on disk still have more than a day left",
    )
    # How refresh_tokens.sh asks whether it needs to widen Auth0 at all.
    minter.add_argument("--needs-mint", action="store_true", help=argparse.SUPPRESS)

    checker = subparsers.add_parser(
        "check", parents=[shared], help="report what the tokens on disk carry"
    )
    checker.set_defaults(run=check)
    checker.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_OUT,
        help=f"env file holding the tokens (default {DEFAULT_OUT.name})",
    )
    checker.add_argument(
        "--only", choices=[a.key for a in ACCOUNTS], help="check just this account"
    )
    checker.add_argument(
        "--min-hours",
        type=float,
        default=24.0,
        help="warn when less than this many hours remain (default 24)",
    )
    checker.add_argument(
        "--quiet", action="store_true", help="counts only, do not list each permission"
    )

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    load_script_env()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
