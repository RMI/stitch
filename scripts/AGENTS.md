# scripts/

Local prototyping and dev tools. These rules override the repo defaults here.

- Everything is a prototype. Keep it short and simple.
- Do what was asked, then see what fails. Don't anticipate problems.
- Don't pre-check failure modes, edge cases, or security risks. Run it and read the error.
- Don't investigate beyond what the task needs.
- Just run things, and freely overwrite anything in `scripts/data/`.
- Raise concerns beforehand only for destructive or irreversible actions outside `scripts/data/`.
- No inline comments. One-line docstrings if any at all.
- Shared helpers live in `scripts/lib/`.
