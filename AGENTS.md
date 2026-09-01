# Stitch AI Agent Instructions

## Operating Principles

* Prefer clarity over flexibility.
* Prefer simple interfaces over powerful interfaces.
* Prefer root-cause fixes over symptom-level fixes.
* Preserve existing behavior unless the task explicitly requires changing it.
* Minimize exposure of implementation details.
* Prefer small, safe, reversible changes.
* Read existing code, architecture, and conventions before making changes.
* Verify assumptions against the codebase rather than inferring them.
* Understand the problem before proposing solutions.
* When uncertain, state the uncertainty and choose the least risky path.
* Favor maintainability and clarity over short-term cleverness.
* Favor sensible defaults over requiring configuration.


## Working Style

Before significant changes:

1. Understand the existing implementation.
2. Restate the task as a verifiable success criterion (what would prove this is done).
3. Explain the proposed approach.
4. Identify meaningful tradeoffs.
5. Ask clarifying questions when requirements are ambiguous.
6. Push back when there is a simpler, safer, more maintainable, or more user-friendly solution.
7. Do not begin implementation when important product or technical decisions remain unresolved.

## AI-Agent Guardrails

* Do not make unrelated changes.
* Do not perform broad refactors unless requested.
* Do not replace working implementations with speculative rewrites.
* Do not create new abstractions until there explicit instruction.
* Do not introduce new architecture unless explicitly justified.
* Do not modify formatting in unrelated files.

## Code Quality

* Prefer boring, readable code over clever code.
* Keep changes minimal and cohesive.
* Use descriptive names.
* Handle errors explicitly.
* Do not silently ignore errors, exceptions, or failed promises.
* Remove any dead code that your change orphaned. Do not delete pre-existing dead code, surface it in the summary instead.
* Follow existing project patterns unless there is a compelling reason not to.
* Optimize for future maintainers reading the code.

For new files or files touched during implementation:

* Run available linters and formatters before committing.
* Resolve warnings that are directly related to the change.
* Do not ignore failing checks without explanation.

## Dependency Policy

Before adding or upgrading a dependency:

1. Check whether it is actively maintained.
2. Prefer mature, widely adopted, well-documented libraries.
3. Use the latest stable version unless compatibility requires otherwise.
4. Avoid deprecated, abandoned, or niche packages.
5. Check project runtime, framework, lockfile, and package manager compatibility.
6. Explain dependency choices briefly.
7. Do not introduce a dependency when the standard library or an existing dependency is sufficient.

## Testing

* Test changes proportionally to their risk.
* Prefer existing test patterns and frameworks.
* Add tests when introducing new behavior or fixing bugs where practical.
* Do not claim something works without verification.

## Git Workflow

* Do not commit unless explicitly asked.
* Before major edits, summarize the intended approach and affected files.
* After changes, provide a concise summary of what changed and why.
* Never rewrite history, push, or delete branches unless explicitly instructed.

## Security

* Never expose secrets or credentials.
* Treat `.env*`, tokens, keys, and production configuration as sensitive.
* Validate external inputs.
* Prefer parameterized queries and framework-native escaping.
* Call out security-sensitive changes explicitly.

## User Experience

* Prefer user-facing clarity and reduce cognitive load where possible.
* Use plain language rather than technical jargon.
* Favor interfaces that are easy for first-time users to understand.
* Explain technical concepts in terms of user goals and outcomes.
* Help users understand what to do next without requiring documentation.
* Optimize for first-time users.
* When technical concepts must be exposed, explain them in user-focused language.
* Prefer progressive disclosure: show only what most users need and reveal advanced details on demand.
* Use sensible, discoverable defaults; reveal advanced configuration only when needed.

## Currentness

For packages, APIs, frameworks, cloud services, security topics, and operational procedures:

* Verify current documentation rather than relying solely on memory.
* Prefer official documentation, release notes, maintainers, and primary sources.

## Project Docs

@ARCHITECTURE.md
@HACKING.md
@CONTRIBUTING.md
