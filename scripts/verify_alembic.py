#!/usr/bin/env python
"""Verify Alembic migrations are valid.

Usage:
    python scripts/verify_alembic.py

Runs 'alembic upgrade head --sql' to validate all migration files can be
loaded and produce valid SQL without requiring a live database connection.

Exit codes:
    0 - All migrations are valid
    1 - Migration validation failed
"""

import os
import subprocess
import sys


def main() -> int:
    # Resolve paths relative to the SyncServer project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    alembic_ini = os.path.join(project_root, "alembic.ini")

    if not os.path.isfile(alembic_ini):
        print(f"ERROR: alembic.ini not found at {alembic_ini}", file=sys.stderr)
        return 1

    # Load .env if present so settings can resolve DATABASE_URL
    env_file = os.path.join(project_root, ".env")
    if os.path.isfile(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            pass

    # Validate that DATABASE_URL is set (required by alembic/env.py)
    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL environment variable is not set", file=sys.stderr)
        print("Set it or create a .env file with DATABASE_URL=postgresql+asyncpg://...", file=sys.stderr)
        return 1

    # Run alembic upgrade head --sql to validate migrations without a DB
    cmd = [sys.executable, "-m", "alembic", "-c", alembic_ini, "upgrade", "head", "--sql"]

    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {project_root}")
    print("-" * 60)

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("ERROR: alembic upgrade --sql timed out after 60s", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("ERROR: alembic not found. Install it: pip install alembic", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print("FAILED: alembic upgrade --sql returned non-zero exit code", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return 1

    # Count the SQL statements produced as a sanity check
    sql_lines = [line for line in result.stdout.splitlines() if line.strip() and not line.strip().startswith("--")]
    print(f"OK: {len(sql_lines)} SQL statements generated from migrations")
    print("All migrations are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
