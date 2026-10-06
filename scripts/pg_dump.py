#!/usr/bin/env python3
"""Dump or restore a database via the postgres Docker image; target from lib.settings."""

import argparse
import os
import subprocess

from lib.settings import script_settings

DOCKER_HOST_GATEWAY = "host.docker.internal"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LOCAL_HOSTS = LOOPBACK_HOSTS | {DOCKER_HOST_GATEWAY}

PG_VARS = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE")

ENV_FLAGS = [flag for var in PG_VARS for flag in ("-e", var)]


def pg_env(url) -> dict[str, str]:
    """The PG* variables the containerized client needs to reach ``url``."""
    host = url.host or "localhost"
    is_local = host in LOCAL_HOSTS
    return {
        "PGHOST": DOCKER_HOST_GATEWAY if is_local else host,
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": url.database or "postgres",
        "PGUSER": url.username or "postgres",
        "PGPASSWORD": url.password or "",
        "PGSSLMODE": "disable" if is_local else "require",
    }


def docker_run(*cmd, stdout=None, stdin_data=None):
    docker_flags = ["--rm"]
    if stdin_data is not None:
        docker_flags.append("-i")

    if stdin_data is not None:
        proc = subprocess.Popen(
            ["docker", "run", *docker_flags, *ENV_FLAGS, "postgres:17", *cmd],
            stdin=subprocess.PIPE,
            stdout=stdout,
        )
        proc.communicate(input=stdin_data)
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, proc.args)
    else:
        subprocess.run(
            ["docker", "run", *docker_flags, *ENV_FLAGS, "postgres:17", *cmd],
            check=True,
            stdout=stdout,
        )


parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("file", nargs="?")
parser.add_argument(
    "--smoke", "--dry-run", action="store_true", help="check the connection, don't dump"
)
parser.add_argument(
    "-r",
    "--restore",
    action="store_true",
    help="restore from dump file instead of dumping",
)
parser.add_argument(
    "-c", "--clean", action="store_true", help="drop existing objects before restore"
)
parser.add_argument(
    "-C",
    "--create",
    action="store_true",
    help="create the database from the archive before restoring into it",
)
parser.add_argument(
    "--db-url", help="whole SQLAlchemy URL; overrides every other target option"
)
parser.add_argument(
    "--db-host", help="hostname, or a shorthand: local, staging (see lib.settings)"
)
parser.add_argument("--db-port", type=int, help="database port")
parser.add_argument(
    "-d", "--db-name", "--database", dest="db_name", help="database name"
)
parser.add_argument("--db-user", help="database user")
args = parser.parse_args()

url = script_settings().database_url(
    url=args.db_url,
    host=args.db_host,
    port=args.db_port,
    database=args.db_name,
    user=args.db_user,
)
os.environ.update(pg_env(url))
print(f"db: {url}")

if args.smoke:
    docker_run("psql", "-tqc", "select 1")
    print("ok")
elif args.restore:
    if not args.file or not args.db_name:
        parser.error("[file] and --db-name required with --restore")
    with open(args.file, "rb") as f:
        dump_data = f.read()
    database = url.database
    if dump_data.startswith(b"PGDMP"):
        cmd = ["pg_restore", "-d", database]
        if args.clean:
            cmd.append("-c")
        if args.create:
            cmd.append("-C")
        docker_run(*cmd, stdin_data=dump_data)
    else:
        docker_run(
            "psql", "-v", "ON_ERROR_STOP=1", "-d", database, stdin_data=dump_data
        )
    print(f"restored from {args.file}")
elif args.file:
    with open(args.file, "wb") as f:
        docker_run("pg_dump", "-Fc", stdout=f)
    print(f"dumped to {args.file}")
else:
    parser.error("file required unless --smoke")
