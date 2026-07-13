#!/usr/bin/env python
"""
Crypto Bot v4.4 — Migration Runner

Usage:
    python scripts/migrate.py upgrade     # apply all pending migrations
    python scripts/migrate.py downgrade   # rollback last migration
    python scripts/migrate.py history     # show migration history
    python scripts/migrate.py auto        # auto-generate migration from models
"""

import os
import sys


def run_alembic(argv: list):
    """Run an Alembic command with proper sys.path setup."""
    # Ensure project root is on path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)

    from alembic.config import main as alembic_main
    os.chdir(project_root)
    alembic_main(argv=argv)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    # Map friendly commands to alembic args
    command_map = {
        "upgrade": ["-c", "alembic.ini", "upgrade", "head"],
        "downgrade": ["-c", "alembic.ini", "downgrade", "-1"],
        "history": ["-c", "alembic.ini", "history"],
        "current": ["-c", "alembic.ini", "current"],
        "auto": ["-c", "alembic.ini", "revision", "--autogenerate",
                 "-m", "auto_migration"],
    }

    if command in command_map:
        run_alembic(command_map[command])
    else:
        # Pass-through to alembic directly
        run_alembic(sys.argv[1:])
