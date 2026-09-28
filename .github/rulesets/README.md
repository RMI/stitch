# GitHub Rulesets

This directory defines the [GitHub Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
this repo expects to be in effect. CI compares them against the repo's **live**
rulesets and fails if they drift.

The check logic and the shared ruleset **templates** are maintained centrally in
[**RMI/actions**](https://github.com/RMI/actions) — see
[`actions/admin/rulesets-check`](https://github.com/RMI/actions/tree/main/actions/admin/rulesets-check)
for the full template list, overlay format, and merge semantics. This repo's
workflow ([`admin-check_rulesets.yml`](../workflows/admin-check_rulesets.yml))
just delegates to that action.

## Overlay files (`*.overlay.json`)

Each ruleset is described by a small **overlay** that names a shared template and
lists only what this repo changes on top of it. A key is checked *only if* an
overlay (or its template) defines it — everything else GitHub returns is ignored.

```jsonc
{
  "template": "gitflow-main",          // required: a template from RMI/actions
  "rules": {                            // sparse overrides, keyed by rule type
    "pull_request": {
      "parameters": { "required_approving_review_count": 1 }
    },
    "required_status_checks": {         // required-check contexts are per-repo
      "parameters": { "required_status_checks": [ /* ...this repo's checks... */ ] }
    }
  }
}
```

A template-only overlay (`{ "template": "gitflow-next-pr" }`) means "use the
template verbatim". For a ruleset that maps to no shared template, use the
`blank` template and author the whole thing in the overlay.

Current overlays here: `gitflow-main`, `gitflow-production`,
`gitflow-next-lifecycle`, `gitflow-next-pr`.

## Changing a ruleset

The overlay is the *intended* state; the live GitHub ruleset is *reality*. To
change one, update **both** so they match (CI verifies they do):

1. Edit the relevant `*.overlay.json` here.
2. Update the live ruleset to match, in **Repo Settings → Rules → Rulesets**
   (or via `gh api`).
3. Push — the rulesets check confirms the overlay and the live ruleset agree.

To change a setting for *all* RMI repos rather than just this one, change the
template in [RMI/actions](https://github.com/RMI/actions) instead of overriding
it here.

## Notes

- `bypass_actors` and other volatile/identity fields are intentionally **not**
  tracked (see the acknowledged-untracked list in RMI/actions). Bypass lists are
  treated as UI-managed policy, not verified by CI.
- New properties GitHub adds to the ruleset schema are caught centrally by a
  nightly coverage check in RMI/actions, not by this repo's PR check.
