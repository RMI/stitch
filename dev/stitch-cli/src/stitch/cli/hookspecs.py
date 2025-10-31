from typing import MutableMapping
from click import Command
from stitch.cli import hookspec


@hookspec
def register_command(cmd_dict: MutableMapping[str, Command]):
    """Define your subcommand and add it to the dictionary"""
    ...
