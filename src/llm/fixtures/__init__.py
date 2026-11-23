"""Canonical Pydantic schema fixtures for offline LLM testing and simulation (P8-5)."""

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.resolve()

__all__ = ["FIXTURES_DIR"]
