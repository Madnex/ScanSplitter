#!/usr/bin/env -S uv run --script
"""Load OpenRouter settings from .env and run the app or benchmark report."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def load_env(path: Path) -> None:
    """Load simple KEY=VALUE entries without adding a runtime dependency."""
    if not path.is_file():
        raise SystemExit(
            f"Missing {path}. Copy .env.example to .env and add your OpenRouter key."
        )
    for line_number, raw_line in enumerate(path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise SystemExit(f"Invalid .env entry on line {line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not key or not key.replace("_", "A").isalnum() or key[0].isdigit():
            raise SystemExit(f"Invalid environment variable name on line {line_number}")
        os.environ.setdefault(key, value)


def main() -> None:
    load_env(ENV_FILE)
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "sk-or-v1-replace-me":
        raise SystemExit("Set OPENROUTER_API_KEY in .env before running this helper.")

    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"
    extra_args = sys.argv[2:]
    if mode == "serve":
        os.environ.setdefault("SCANSPLITTER_BENCHMARK", "1")
        command = ["uv", "run", "scansplitter", "api", *extra_args]
    elif mode == "report":
        command = [
            "uv",
            "run",
            "benchmarks/evaluate.py",
            "--suite",
            "scansplitter",
            "--scan-detector",
            "openrouter",
            "--output",
            "benchmarks/results/openrouter.md",
            *extra_args,
        ]
    else:
        raise SystemExit("Usage: scripts/openrouter.py [serve|report] [extra arguments]")

    raise SystemExit(subprocess.call(command, cwd=ROOT, env=os.environ))


if __name__ == "__main__":
    main()
