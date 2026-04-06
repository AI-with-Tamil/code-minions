"""Lightweight env-file loading for repo-local SDK config."""

from __future__ import annotations

import os
from pathlib import Path


def read_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Parse a loose env file.

    Supports normal dotenv lines and loose JSON-ish pairs like:
        "KEY": "value"
    """
    env_path = Path(path)
    if not env_path.exists():
        return {}

    data: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line and ":" not in line.split("=", 1)[0]:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue

        key = _clean_env_token(key)
        value = _clean_env_token(value)
        if key:
            data[key] = value

    return data


def load_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Load env values into os.environ without overwriting existing values."""
    parsed = read_env_file(path)
    for key, value in parsed.items():
        os.environ.setdefault(key, value)
    return parsed


def _clean_env_token(token: str) -> str:
    token = token.strip().rstrip(",")
    if token.startswith(("'", '"')):
        token = token[1:]
    if token.endswith(("'", '"')):
        token = token[:-1]
    return token.strip()
