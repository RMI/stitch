# Remediate Dependabot Security Alerts (RMI/stitch)

## Context

The repo has **15 open Dependabot security alerts** (5 high, 5 medium, 5 low) across 5 Python
packages, all surfaced against the root `uv.lock`. The goal is to clear every alert with the
smallest safe change, then add a `dependabot.yml` so future vulnerable dependencies are caught
and PR'd automatically (there is currently no `.github/dependabot.yml` — only ambient scanning).

Investigation confirmed **all 15 alerts resolve with a lockfile-only upgrade**: every affected
package's existing version constraint in the `pyproject.toml` files already permits the patched
version, and FastAPI 0.136.1's pins (`starlette>=0.46.0`, `python-multipart>=0.0.18`) do not cap
the transitive upgrades. **No `pyproject.toml` edits are required.**

## Alerts → target versions

| Package | Locked → Target | # Alerts | Severity | How it's pulled in |
|---|---|---|---|---|
| `pyjwt` | 2.12.1 → **2.13.0** | 5 | 1 high, 3 med, 1 low | **direct** — `stitch-auth` (`pyjwt[crypto]>=2.12.0`); security-critical JWT validation |
| `python-multipart` | 0.0.28 → **0.0.32** | 4 | 1 high, 3 low | transitive via `fastapi[standard-no-fastapi-cloud-cli]` |
| `starlette` | 1.0.1 → **1.3.1** | 3 | 2 high, 1 low | transitive via `fastapi` |
| `cryptography` | 48.0.0 → **49.0.0** | 1 | high | transitive via `pyjwt[crypto]` (OpenSSL-in-wheels fix) |
| `pydantic-settings` | 2.14.1 → **2.14.2** | 1 | medium | **direct** — auth/api/llm/entity-linkage |

Decisions confirmed with user:
- **cryptography → 49.0.0** (latest). Breaking changes in 49.0.0 (arm64-only macOS wheels,
  removed deprecated type aliases, stricter X.509/OCSP parsing) do not affect this project —
  cryptography is only a transitive dep of `pyjwt[crypto]` for standard RSA/EC JWT validation,
  and deploys run on Linux Docker. Team dev machines are arm64 (confirmed via local `uv`).
- **Add `.github/dependabot.yml`** for ongoing automation.

## Changes

### 1. Upgrade the lockfile (root)

Run a targeted lockfile upgrade for exactly the five packages:

```
uv lock \
  --upgrade-package pyjwt \
  --upgrade-package python-multipart \
  --upgrade-package starlette \
  --upgrade-package cryptography \
  --upgrade-package pydantic-settings
```

This touches only `uv.lock`. After running, confirm each package landed on (or above) its target
version in the table. If `uv` picks a version at or above the target that isn't the exact one
listed (e.g. a later patch), that's fine — the requirement is `>= patched version`.

- File modified: `uv.lock`
- No `pyproject.toml` changes.

### 2. Add `.github/dependabot.yml` (new file)

Enable scheduled version-update PRs (weekly) for the ecosystems in the repo. Group updates to
keep PR volume low. Covers:
- **uv** ecosystem at `/` (root `uv.lock` + workspace members)
- **npm** at `/deployments/stitch-frontend` (only `package.json` in the repo)
- **github-actions** at `/` (the ~30 workflow files under `.github/workflows/`)

Proposed content:

```yaml
version: 2
updates:
  - package-ecosystem: "uv"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      python-dependencies:
        patterns: ["*"]
  - package-ecosystem: "npm"
    directory: "/deployments/stitch-frontend"
    schedule:
      interval: "weekly"
    groups:
      npm-dependencies:
        patterns: ["*"]
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      actions:
        patterns: ["*"]
```

Note: security updates themselves are governed by repo settings (already active — that's why the
alerts exist). This file adds proactive *version* updates so deps don't drift far enough to
accumulate CVEs, and groups them so review stays manageable.

## Verification

1. **Lockfile integrity:** `make py-lock-check` (runs `uv lock --check`) — must pass, proving the
   lock is consistent with all `pyproject.toml` constraints.
2. **Sync + tests:** `make py-test` (api, entity-linkage, seed, stitch-llm deployments + all
   packages). Pay special attention to **`make pkg-test-auth`** — `stitch-auth` is the only code
   that directly exercises the security-critical upgrades (`pyjwt` + `cryptography` for JWT
   validation).
3. **Full gate:** `make check` (aggregates lint + test + format-check + lock-check).
4. **Alert confirmation after merge:** re-check `gh api repos/RMI/stitch/dependabot/alerts` (or
   the Security tab) — all 15 should auto-close once the patched `uv.lock` lands on the default
   branch.
5. **dependabot.yml validity:** it's picked up on push to the default branch; confirm no config
   error appears under Insights → Dependency graph → Dependabot after merge.

## Risk / rollback

- Change is confined to `uv.lock` (regenerable) + one new CI config file. Fully reversible via
  `git revert`.
- Main behavioral watch items: `starlette` 1.0.1 → 1.3.1 (largest jump; FastAPI's request/form
  handling rides on it) and `pyjwt` 2.12.1 → 2.13.0 (auth path). Both are covered by the existing
  test suites in step 2.
- No production config, secrets, or app source is modified.
