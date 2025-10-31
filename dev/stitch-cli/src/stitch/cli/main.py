import click
from stitch.cli.group import StitchGroup


@click.command(cls=StitchGroup)
@click.version_option()
@click.pass_context
def main(ctx: click.Context):
    pass
