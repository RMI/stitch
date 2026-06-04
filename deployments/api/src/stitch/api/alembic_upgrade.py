from __future__ import annotations

import sys

from stitch.api.alembic import run_upgrade


def main() -> None:
    revision = sys.argv[1] if len(sys.argv) > 1 else "head"
    run_upgrade(revision)


if __name__ == "__main__":
    main()
