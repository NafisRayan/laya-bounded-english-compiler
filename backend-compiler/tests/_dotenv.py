"""Tiny .env loader (no dependency) for the harness tiers.

Reads ``KEY=VALUE`` lines from ``backend-compiler/.env`` into ``os.environ``
when the variable is not already set (shell wins over the file). Compliant
with the ``.env.example`` template and the repo's ``.gitignore``.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or _ENV_PATH
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value