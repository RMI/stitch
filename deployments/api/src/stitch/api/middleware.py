from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stitch.api.settings import Settings


def register_middlewares(application: FastAPI, settings: Settings):
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.frontend_url)],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
