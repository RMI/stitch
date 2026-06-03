from __future__ import annotations

from stitch.api.alembic import run_autogenerate


def main() -> None:
    run_autogenerate("baseline")


if __name__ == "__main__":
    main()
