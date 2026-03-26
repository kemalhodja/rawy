#!/usr/bin/env python3
"""
PostgreSQL smoke:
1) alembic upgrade head
2) pytest smoke tests

Usage:
  DATABASE_URL=postgresql://rawy:rawy@localhost:5432/rawy python scripts/smoke_pg.py
"""

from __future__ import annotations

import os
import subprocess
import sys


def run(cmd: list[str]) -> None:
    print("[smoke_pg]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    db_url = (os.environ.get("DATABASE_URL") or "").strip().lower()
    if not db_url.startswith("postgresql"):
        print("[smoke_pg] ERROR: DATABASE_URL postgresql:// ile başlamalı")
        return 2

    run([sys.executable, "-m", "alembic", "upgrade", "head"])
    run([sys.executable, "-m", "pytest", "tests/test_api_smoke.py", "-q"])
    print("[smoke_pg] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
