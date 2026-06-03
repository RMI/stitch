from __future__ import annotations

from stitch.api.alembic import run_upgrade


def main() -> None:
    run_upgrade("head")


if __name__ == "__main__":
    main()
