# Contributing to Stitch

Thanks for your interest in contributing to `stitch`.

This guide covers how to open issues and pull requests. For local setup, commands, and development workflows, see [`HACKING.md`](./HACKING.md).

## The Most Important Rule

You must understand your code.

If you submit a change, you should be able to explain:
- what it does,
- why it is correct,
- what tradeoffs it introduces,
- and how it was tested.

Using AI tools is allowed. Submitting AI-generated changes you do not understand is not.

## AI-Assisted Change Scope

AI assistance does not change PR quality standards.

- Keep AI-assisted PRs small and focused on a single concern.
- Do not submit broad, architecture-wide rewrites unless that architectural change is explicitly planned and tracked.
- Avoid mixing refactors with behavior changes in the same PR.
- Split large AI-generated output into multiple PRs that can be reviewed independently.
- In your PR description, explicitly call out:
  - what AI was used for,
  - what you verified manually,
  - and what tests validate the change.

## How to Contribute

### External Contributors (without write access)

- Fork the repository and branch from `main`.
- Make your changes in your fork.
- Open a PR from your fork when the changes are ready for review.

### Contributors with write access

- Create a branch directly in this repository.
- Open a PR to `main` when ready.
- Merge after required approvals and checks pass.

## Issues

External contributors can open issues to report bugs or suggest features. Please provide as much detail as possible, including steps to reproduce, expected vs actual behavior, and any relevant logs or screenshots.

## Pull Request Expectations

Work in this repo often happens in Draft PRs. These have the advantage of running the CI Suite and preparing preview environments that can be externally validated and inspected.

When opening a PR, consider opening as Draft, and marking as ready for review once all checks are green.

PRs are most likely to be accepted when they:
- stay focused on one concern,
- include tests for behavior changes,
- update docs for user-facing changes,
- clearly describe what changed and why,
- link related JIRA issues (`STIT-#<number>`) in title when relevant.

Avoid mixing unrelated refactors into feature/fix PRs.

As a rule of thumb: a PR is a request for someone else's time and expertise. Respect that by making it easy to review.

For more information, see RMI's pull request practices: https://rmi.github.io/practices/pull_request.html

## Commit and Branch Guidelines

- Prefer Conventional Commits (for example: `feat(api): add resource ownership filter`).
- Keep commit messages clear and specific.
- Use short, descriptive branch names (for example: `docs/add-contributing-guide`, `fix/api-auth-header`).

## Development and Testing

Before opening a PR, run checks from the repository root:

```bash
make check
```

If you need narrower loops, see `HACKING.md` for package-specific lint/test/format commands.

## Documentation Requirements

Update documentation when behavior changes, including:
- API behavior or endpoints,
- setup and run instructions,
- environment/configuration expectations,
- frontend behavior visible to users.

## Code of Conduct

Be respectful and constructive. Focus feedback on code and behavior. See our [code of conduct](./CODE_OF_CONDUCT.md) for more details.

## Licensing

By contributing, you agree your contributions are licensed under this repository's [license](./LICENSE).

## References

