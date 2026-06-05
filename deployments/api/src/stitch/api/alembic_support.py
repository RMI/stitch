from __future__ import annotations

import os

from sqlalchemy.engine import make_url

from stitch.api.settings import Settings as ApiSettings


def build_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        parsed = make_url(url)
        if parsed.drivername == "sqlite+aiosqlite":
            parsed = parsed.set(drivername="sqlite+pysqlite")
        return parsed.render_as_string(hide_password=False)
    return ApiSettings().get_sync_database_url().render_as_string(hide_password=False)
