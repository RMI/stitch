
## Stitch CLI

The package `dev/stitch-cli` exposes a plugin interface to allow developers to easily add & run custom `stitch` subcommands.

To install the CLI and all registered commands, run

```bash
uv sync --extra cli
```

Now, the subcommands (or groups) will be accessible via the `stitch` binary in your virtual environment.
To get a list of available commands, run

```bash
uv run stitch --help

# or for a specific command
uv run stitch [COMMAND] --help
```

`stitch-cli` exposes its plugin entry point via the `stitchcli` string.
To create a new subcommand, create a new package in `dev/`:

```bash
uv init --package --name some-cool-command dev/some-cool-command
```

Add `stitch-cli` as a dependency:

```bash
uv add --package some-cool-command stitch-cli
```

Create a module (the name doesn't matter) for the plugin interface:

```bash
touch src/some_cool_command/plugin.py
```

and add the following:

```python
from click import Command

import stitch.cli

@stitch.cli.hookimpl
def register_command(cmd_dict: MutableMapping[str, Command]): # the function name MUST match the specified function in `stitch.cli.hookspecs`
  ...
```

Create your `click.Group` or `click.Command` and assign it to the `cmd_dict` under an appropriate command name.
