import click
import uvicorn
from stitch.api.main import app


@click.command()
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
@click.option("--reload", is_flag=True)
@click.option("--workers", default=1, type=int, help="Number of worker processes.")
def main(host: str, port: int, reload: bool, workers: int):
    uvicorn.run(
        app=app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


if __name__ == "__main__":
    main()
