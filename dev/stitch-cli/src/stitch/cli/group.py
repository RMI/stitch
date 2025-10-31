from typing import MutableMapping, override
import click
from pluggy import PluginManager

from stitch.cli import hookspecs, PLUGIN_MARKER


class StitchGroup(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pm = PluginManager(PLUGIN_MARKER)
        pm.add_hookspecs(hookspecs)
        pm.load_setuptools_entrypoints(PLUGIN_MARKER)
        self.pm = pm
        _commands: MutableMapping[str, click.Command] = {}
        pm.hook.register_command(cmd_dict=_commands)
        self._commands = _commands

    @override
    def list_commands(self, ctx: click.Context) -> list[str]:
        base = super().list_commands(ctx)
        click.echo(f"base: {base}")
        added = sorted(self._commands.keys())
        click.echo(f"added: {added}")
        return base + added

    @override
    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self._commands:
            return self._commands[cmd_name]
        return super().get_command(ctx, cmd_name)

    def _call_hooks(self): ...
