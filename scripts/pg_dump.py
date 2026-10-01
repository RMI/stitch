#!/usr/bin/env python3
"""Dump/restore a database via the postgres Docker image; PG* come from the env files."""

import argparse
import os
import subprocess

from lib.env import load_script_env

load_script_env()
os.environ.setdefault("PGHOST", "stitch-staging.postgres.database.azure.com")
os.environ.setdefault("PGPORT", "5432")
os.environ.setdefault("PGDATABASE", "pr_0295_demo_integrate_6dbf")
os.environ.setdefault("PGSSLMODE", "require")

ENV_FLAGS = [
    f
    for v in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE")
    for f in ("-e", v)
]


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


parser = argparse.ArgumentParser()
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
parser.add_argument("-d", "--database", type=str, help="the database name")
args = parser.parse_args()

if args.database:
    os.environ["PGDATABASE"] = args.database

if args.smoke:
    docker_run("psql", "-tqc", "select 1")
    print("ok")
elif args.restore:
    if not args.file or not args.database:
        parser.error("[file] and --database required with --restore")
    with open(args.file, "rb") as f:
        dump_data = f.read()
    if dump_data.startswith(b"PGDMP"):
        cmd = ["pg_restore", "-d", args.database]
        if args.clean:
            cmd.append("-c")
        if args.create:
            cmd.append("-C")
        docker_run(*cmd, stdin_data=dump_data)
    else:
        docker_run(
            "psql", "-v", "ON_ERROR_STOP=1", "-d", args.database, stdin_data=dump_data
        )
    print(f"restored from {args.file}")
elif args.file:
    with open(args.file, "wb") as f:
        docker_run("pg_dump", "-Fc", stdout=f)
    print(f"dumped to {args.file}")
else:
    parser.error("file required unless --smoke")
