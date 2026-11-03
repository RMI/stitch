from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

__all__ = ["responses_joke"]


def _metadata(rows: dict[str, str]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column(style="dim")
    for label, value in rows.items():
        table.add_row(label, value)
    return table


async def _joke(topic: str) -> None:
    from stitch.api.llm import get_llm_client, get_llm_settings

    settings = get_llm_settings()
    client = get_llm_client()
    console = Console()
    with console.status(f"[dim]asking about {topic}...", spinner="dots"):
        response = await client.responses.create(
            model=settings.azure_openai_model or "",
            input=f"Tell me a one-line joke about {topic}.",
            store=False,
        )
    usage = response.usage

    console.print()
    console.print(
        Panel(
            Text(response.output_text.strip(), style="bold bright_white"),
            title=f"[cyan]{topic}[/]",
            title_align="left",
            border_style="cyan",
            padding=(1, 3),
        )
    )
    console.print(
        _metadata(
            {
                "model": response.model,
                "status": response.status or "unknown",
                "tokens": (
                    f"{usage.input_tokens} in / {usage.output_tokens} out"
                    if usage
                    else "unreported"
                ),
                "endpoint": str(settings.azure_openai_base_url),
            }
        )
    )
    console.print()


def responses_joke(topic: str) -> None:
    asyncio.run(_joke(topic))
