#!/usr/bin/env python3
"""Fail the deploy when the downstream ETL token cannot read every source.

Auth0 freezes the RBAC permission array into an access token at issuance, so a
grant added after a token was minted never reaches it. The token keeps
authenticating and only the newest `source:read:<key>` is absent, which the ETL
surfaces as dedupe re-posting every record for that one dataset rather than as
any error. Checking before the deploy turns that into a named CI failure.

Reads CURRENT_TOKEN from the environment, never argv, and prints no token.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
from datetime import datetime, timezone

# Source keys are defined upstream in packages/stitch-ogsi/src/stitch/ogsi/model
# as `<NAME>_SRC` constants, and each ETL dataset imports its key from there.
# Listed by hand to keep this job dependency-free, so adding a dataset means
# adding its key here too.
REQUIRED_PERMISSIONS = frozenset(
    {
        "source:write",
        "source:read:alb",
        "source:read:bc",
        "source:read:ccr",
        "source:read:gem",
        "source:read:nor",
        "source:read:wm",
    }
)


def claims_of(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a three-part JWT")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def main() -> int:
    token = os.environ.get("CURRENT_TOKEN", "")
    if not token:
        sys.exit("CURRENT_TOKEN must be set")

    try:
        claims = claims_of(token)
    except (ValueError, json.JSONDecodeError, binascii.Error) as exc:
        sys.exit(f"Downstream token is undecodable ({exc}).")

    expiry = claims.get("exp")
    if isinstance(expiry, (int, float)):
        expires_at = datetime.fromtimestamp(expiry, tz=timezone.utc)
        hours = (expires_at - datetime.now(timezone.utc)).total_seconds() / 3600
        floor = float(os.environ.get("MIN_REMAINING_HOURS", "24"))
        print(f"Token expires {expires_at:%Y-%m-%d %H:%M} UTC ({hours:.1f}h left)")
        if hours <= 0:
            sys.exit("Downstream token has already expired.")
        if hours < floor:
            print(f"::warning::Downstream token has {hours:.1f}h left, below the {floor:.0f}h floor")
    else:
        print("::warning::Downstream token carries no exp claim")

    missing = sorted(REQUIRED_PERMISSIONS - set(claims.get("permissions") or []))
    if missing:
        sys.exit(
            "Downstream token is missing "
            + ", ".join(missing)
            + ". An Auth0 grant only reaches tokens minted after it was added, so "
            "re-mint the service account's token and update the environment secret."
        )

    print(f"Downstream token carries all {len(REQUIRED_PERMISSIONS)} required permissions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
