## Tasks

### Obsidian

- init vault: `poe vault:init`
  - calls `srcx vault-init .agents/<project or directory name>`
- cp file to vault: `poe vault:cp [-d/--vault-dir=inbox] path/to/file`
  - copies the file into the obsidian vault at `.agents/<project or directory name>`
- open file in Obsidian:
  - restrict to .md files
  - run cp task
  - use Obsidian CLI to open the file

### Editing

- easier file editing: `poe edit -p/--package <package name, eg stitch-tasks> <file>`
  - file can be partial
  - search to find the most likely candidate (searching can probably be a common utility)
  - open the file in $EDITOR
- check documentation
- delete inline comments from file/directory/package
- create docstring stubs
- generate new member package
- generate new task module
- add copyright preamble to module or generate new module with copyright

### Info

- `poe info <package-name>`
- `poe info:tree <package-name>` - directory tree
- `poe info:api --include-private -d/--depth N <package or module name>`
- `poe info:deps <package name>` - dependency graph
- `poe info:calls <package name>` - call graph
- line counts
- complexity
- `poe search` ?
- `poe search:semantic` ?

> [!NOTE]
> For lint, format, test, and type check, if <package-name> isn't specified, run across all member packages.

### Application

various tasks that call on member package api functions

### Local Docker Environments

- `poe up ...` - spin up api, frontend, and docker containers with docker compose
- `poe down ...` - stop containers
- `poe local db restore path/to/pgdump/file.{dump,sql}` - restores a local docker volume from the dump file
- `poe local db dump path/to/pgdump/file.{dump,sql}` - dump the currently running db to a file, file defaults to `<repo root>/data/db/backups/<container name>-<timestamp>.dump`

### Azure

- `poe backup:get <env:production> [timestamp:now()]` - downloads the latest db dump from <env> prior to the passed timestamp/now
- `poe backup:run <job details>`
- `poe deploy:{prod,dev,staging}`

### Packaging

- `poe release` - create gh release
- `poe publish [index:PyPi` - publish to index, defaults to pypi.org

### Linting

- `poe lint -f/--fix <package-name>`

### Formatting

- `poe [format|fmt] -c/--check <package name>`

### Type Checking

- `poe tc <package name>`

### Testing

- `poe test <package name>` - run all package tests
- `poe test:lf <package name>` - run last failed tests first
- `poe test:fail <package name>` - run only failed tests
- `poe test:mark -m/--marks <comma-separated test marsk> <package-name>`
- `poe coverage <package-name>`

### Multi tasks

- `poe check <package-name>` - type check, lint, test, and coverage in parallel

### Agent-safe aliases

allows setting `Bash(poe agent *)` in claude settings "allow" list

- `poe agent <cmd>`

## Shared Utilities/Libraries

- file reading & writing
- uv/python workspace operations
- template processing
- git
- gh
- azure
- jira
- env handling (getting & setting, env files)

## Exploration

- does `poe` support grouped subcommands? does `poethepoet-tasks`?
