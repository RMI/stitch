from collections.abc import MutableMapping
import click
import uvicorn
from stitch.api.main import app
import stitch.cli


@click.group(name="api")
def cli():
    """Stitch API utilities."""
    ...


@cli.command(name="dev-server")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
@click.option("--reload", is_flag=True)
@click.option("--workers", default=1, type=int, help="Number of worker processes.")
def start_api(host: str, port: int, reload: bool, workers: int):
    """Start the API dev server.

    Args:
        host: ip address for the host (default: 0.0.0.0/localhost)
        port: the server port (default: 8000)
        reload: enable auto-reload (default: True)
        workers: number of worker processes (default: 1)
    """
    uvicorn.run(
        app=app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


@stitch.cli.hookimpl
def register_command(cmd_dict: MutableMapping[str, click.Command]):
    command_name = "api"

    cmd_dict[command_name] = cli
    click.echo(f"added {command_name}")
    return cmd_dict
