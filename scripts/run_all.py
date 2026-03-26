#!/usr/bin/env python3
"""
Sırayı otomatik çalıştır: alembic upgrade head → pytest
Onay sormaz; PostgreSQL kapalıysa migration adımı hata verir.

Sadece test (migration atla):  set SKIP_ALEMBIC=1   veya   SKIP_ALEMBIC=1 python scripts/run_all.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    os.chdir(ROOT)
    skip = os.environ.get("SKIP_ALEMBIC", "").lower() in ("1", "true", "yes")
    if not skip:
        print("[run_all] alembic upgrade head ...")
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
        )
    else:
        print("[run_all] SKIP_ALEMBIC=1 -> migration atlandi")
    print("[run_all] pytest ...")
    subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        check=True,
    )
    print("[run_all] tamam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
