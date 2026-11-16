"""Turn a recipe's ingredient text into grocery item names."""

from __future__ import annotations


def ingredient_lines(text: str) -> list[str]:
    """Non-empty, stripped lines, skipping section headers like 'For the sauce:'."""
    lines = (line.strip() for line in (text or "").splitlines())
    return [line for line in lines if line and not line.endswith(":")]
