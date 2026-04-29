from typing import Final
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stitch.llm.settings import Settings

ALLOWED_METHODS: Final[tuple[str, ...]] = (
    "GET",
    "OPTIONS",
)

ALLOWED_HEADERS: Final[tuple[str, ...]] = (
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
)


def register_middlewares(application: FastAPI, settings: Settings) -> None:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.frontend_origin_url).rstrip("/")],
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
