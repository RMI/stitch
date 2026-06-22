from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_METHODS: Final[tuple[str, ...]] = (
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "OPTIONS",
)

ALLOWED_HEADERS: Final[tuple[str, ...]] = (
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
)


def register_cors(
    app: FastAPI,
    *,
    origins: Sequence[str],
    allow_credentials: bool = True,
) -> None:
    """Register the standard CORS policy shared across Stitch services.

    Origins are normalised (trailing slash stripped) to match how browsers send
    the ``Origin`` header.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.rstrip("/") for origin in origins],
        allow_credentials=allow_credentials,
        allow_methods=list(ALLOWED_METHODS),
        allow_headers=list(ALLOWED_HEADERS),
    )
