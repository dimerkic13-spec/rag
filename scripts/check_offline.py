"""Run repository checks without credentials or external services."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    checks = (
        ("scripts/check_registry.py", "examples/documents.csv"),
        ("scripts/check_registry.py", "examples/pilot_catalog.csv"),
        ("-m", "unittest", "discover", "-s", "tests/unit", "-v"),
    )
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for arguments in checks:
        result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
