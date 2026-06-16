from typing import Final
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stitch.api.observability import RequestTimingMiddleware
from stitch.api.settings import Settings

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


def register_middlewares(application: FastAPI, settings: Settings):
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.frontend_origin_url).rstrip("/")],
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
    # Added last so it is the outermost middleware and times the full request,
    # including time spent in CORS handling.
    application.add_middleware(RequestTimingMiddleware)
