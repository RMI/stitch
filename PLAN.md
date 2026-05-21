# Dress-Rehearsal Deployment Rollout Plan

## Summary
Set up a production-like deployment flow in the dev resource group by making `production` a first-class deploy branch for the long-lived dress-rehearsal target, while keeping `main` as the long-lived development target. Introduce three deployment lanes, each backed by a GitHub Environment: `development`, `staging`, and `dress-rehearsal`.

Use two workflow concepts consistently:
- `deployment_lane`: the deploy class and GitHub Environment name (`development`, `staging`, `dress-rehearsal`)
- `deployment_name`: the concrete target name used for DB, Container App, and frontend naming (`main`, `pr-57`, `next`, `hotfix-fix-auth`, `production`)

PRs to `main` remain in the `development` lane and continue to create preview deployments. PRs into `production` from `next` or `hotfix/*` create branch-derived staging deployments in the `staging` lane. Pushes to `production` deploy the long-lived dress-rehearsal target. Replace the `seed` post-deploy step with Azure-run ETL jobs using private GHCR images published from `RMI/stitch-etl-poc`.

## PR Set

### PR 1: Branch Governance and GitHub Environment Setup
- Add repository ruleset JSON files under `.github/rulesets` for `production`, `next`, and `hotfix/*`, matching the PBTAR branch-governance model and the existing ruleset pattern in this repo.
- Keep `production` protected with at least the current required checks/review policy plus any new deploy-readiness checks needed by the rehearsal flow.
- Protect `next` so it is updated only through PRs.
- Protect `hotfix/*` with PR-based merge flow consistent with the intended emergency-release process.
- Create three GitHub Environments:
  - `development` for pushes to `main` and PRs to `main`
  - `staging` for PRs into `production` from `next` and `hotfix/*`
  - `dress-rehearsal` for pushes to `production`
- Define lane-specific secrets and variables in GitHub Environments for all target-specific deploy inputs.
- Keep only truly global plumbing values at repo scope, such as shared Azure identity/subscription values if they are intentionally common across lanes.
- Add fail-fast workflow validation for required lane-specific values so deploy jobs error clearly when a required environment variable or secret is missing.
- Fold setup and configuration documentation into the PR as the GitHub Environments and rulesets are introduced.

### PR 2: Trigger Model and Naming Refactor
- Refactor `.github/workflows/build-and-deploy.yml` and related reusable workflows around explicit `deployment_lane` and `deployment_name` computation.
- Set workflow behavior as follows:
  - push to `main` -> `deployment_lane=development`, `deployment_name=main`
  - PR to `main` -> `deployment_lane=development`, `deployment_name=pr-<number>`
  - push to `production` -> `deployment_lane=dress-rehearsal`, `deployment_name=production`
  - PR from `next` to `production` -> `deployment_lane=staging`, `deployment_name=next`
  - PR from `hotfix/*` to `production` -> `deployment_lane=staging`, `deployment_name=<normalized branch name>`
- Do not create staging deployments from direct pushes to `next` or `hotfix/*`; only PRs targeting `production` should create them.
- Replace ambiguous existing “environment” naming in workflows and runtime config with the new explicit terms.
- Keep documentation updates in this PR alongside the trigger/naming changes.

### PR 3: Environment-Aware Azure Deploy Plumbing
- Update reusable workflows such as `deploy-container.yml`, `deploy-db.yml`, `run-db-init.yml`, frontend deploy workflow, and cleanup workflow to take lane/name-aware configuration instead of relying on fixed dev-only assumptions.
- Use `deployment_lane` to select the GitHub Environment and its lane-specific configuration.
- Use `deployment_name` to derive normalized DB names, Container App names, frontend labels, and teardown targets.
- Remove hardcoded assumptions around `STITCH-DEV-RG`, `stitch-dev`, and similar single-target values by routing them through required lane-scoped variables.
- Keep PR-to-`main` previews in the `development` lane.
- Keep PRs from `next` / `hotfix/*` into `production` in the `staging` lane, but with branch-derived `deployment_name` values.
- Preserve current destroy/recreate database behavior for now.
- Explicitly defer restore-from-backup and migration-safe promotion logic to a later PR set.
- Include the necessary deployment/configuration docs updates in this PR.

### PR 4: ETL Image Contract and Registry Integration
- Define the integration contract between `stitch` and `RMI/stitch-etl-poc` around two private one-shot GHCR images with fixed default entrypoints:
  - `etl-gem`
  - `etl-woodmac`
- Document expected image naming, tags/digests, and how this repo pins or resolves the image references used in deploy workflows.
- Configure GitHub-side access so Actions in this repo can consume the private GHCR package(s).
- Configure Azure-side registry credentials so Azure-run ETL jobs can pull private GHCR images at runtime.
- Keep the workflow contract registry-agnostic enough that a later move to ACR does not require redesigning the orchestration flow.
- Include the ETL integration and credential-setup documentation in this PR.

### PR 5: Replace `seed` with Azure-Run ETL Jobs
- Remove the `seed` image build/run from the release path.
- Introduce Azure-native one-shot execution for `etl-gem` and `etl-woodmac` after API deployment.
- Run `etl-gem` and `etl-woodmac` independently so failure/reporting is per job rather than bundled.
- Use the deployed API endpoint for both jobs, matching the current conceptual role of `seed`.
- Supply job configuration through lane-scoped GitHub Environment values and secrets.
- For `etl-woodmac`, use secret-managed API credentials, with GitHub Environment secret handling acceptable for the first cut.
- For `etl-gem`, fetch the private input from Azure Blob Storage via lane-scoped URL/SAS-style secret configuration rather than embedding the file in the image or storing it in GitHub.
- Make the ETL jobs safe to rerun on repeated PR updates and redeploys.
- Include the necessary operational/documentation updates in this PR.

## Public Interfaces and Workflow Contract Changes
- `production` becomes a first-class deployment branch.
- `deployment_lane` becomes the canonical workflow concept for selecting GitHub Environment and lane-scoped config.
- `deployment_name` becomes the canonical workflow/runtime concept for naming specific deployed targets.
- Reusable deployment workflows will require explicit lane/name-aware inputs or computed context rather than fixed single-environment assumptions.
- Target-specific deploy values move to GitHub Environment scope and are required to exist for the selected lane; workflows should fail loudly when they are missing.
- The post-deploy data-loading contract changes from one `seed` step to two Azure-run ETL jobs, `etl-gem` and `etl-woodmac`.

## Test Plan
- Validate the new ruleset JSON files and confirm branch protections apply to `production`, `next`, and `hotfix/*` as intended.
- Verify push-to-`main` deploys using `deployment_lane=development`, `deployment_name=main`, and GitHub Environment `development`.
- Verify PRs to `main` deploy preview targets using `deployment_lane=development` and `deployment_name=pr-<number>`.
- Verify push-to-`production` deploys the long-lived dress-rehearsal target using `deployment_lane=dress-rehearsal`, `deployment_name=production`, and GitHub Environment `dress-rehearsal`.
- Verify PR from `next` into `production` deploys a staging target using `deployment_lane=staging` and `deployment_name=next`, and tears it down on PR close.
- Verify PR from `hotfix/*` into `production` deploys a staging target using `deployment_lane=staging` and normalized branch-derived `deployment_name`, and tears it down on PR close.
- Verify direct pushes to `next` do not trigger staging deployment flows.
- Verify required lane-specific secrets/variables fail fast with clear error messages when missing.
- Verify both ETL jobs run independently, can both succeed for the same deployment, and no longer depend on the old `seed` path.
- Verify `etl-gem` fails clearly when blob access is unavailable and `etl-woodmac` fails clearly when its API credential is missing.

## Assumptions and Defaults
- `main` remains the long-lived development branch and target.
- PRs to `main` remain preview deployments and use the `development` lane.
- `production` deploys the long-lived dress-rehearsal target in the dev resource group until the real production resource group exists.
- PRs into `production` from `next` and `hotfix/*` create staging deployments only while the PR is open.
- Staging deployments are keyed by branch-derived `deployment_name`, not PR number.
- All lane-specific deploy configuration should be supplied through GitHub Environments, with workflows failing loudly when required values are absent.
- Repo-level values should be reserved for intentionally global plumbing, not as silent fallbacks for lane-specific config.
- Database backup restore and migration-safe promotion are explicitly deferred.
- `RMI/stitch-etl-poc` publishes two runnable one-shot images with fixed default entrypoints.
- `etl-gem` private input will be hosted in Azure Blob Storage and accessed via secret-managed credentials.
