"""Turn a recipe's ingredient text into grocery item names."""

from __future__ import annotations

import re


def ingredient_lines(text: str) -> list[str]:
    """Non-empty, stripped lines, skipping section headers like 'For the sauce:'."""
    lines = (line.strip() for line in (text or "").splitlines())
    return [line for line in lines if line and not line.endswith(":")]


_QTY = r"(?:\d+(?:[.,/]\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞])"
_UNITS = (
    "cups?|c|tablespoons?|tbsps?|tbs|tbl|teaspoons?|tsps?|t|ounces?|oz|pounds?|lbs?|"
    "grams?|g|kilograms?|kgs?|kg|milliliters?|millilitres?|ml|liters?|litres?|l|"
    "cans?|tins?|jars?|packages?|pkgs?|packets?|bags?|boxes|box|bottles?|"
    "cloves?|pinch(?:es)?|dash(?:es)?|handfuls?|bunch(?:es)?|sprigs?|slices?|"
    "sticks?|heads?|stalks?|pieces?|large|medium|small"
)
_LEADING = re.compile(
    rf"^(?:{_QTY}\s*(?:-|to|–)?\s*)+(?:\s*(?:{_UNITS})(?:\.|\b))?\s*(?:of\s+)?", re.IGNORECASE
)
_PARENS = re.compile(r"\([^()]*\)")


def ingredient_name(line: str) -> str:
    """Best-effort ingredient from a grocery line: '2 cups flour, sifted' -> 'flour'."""
    original = (line or "").strip()
    text = original
    while _PARENS.search(text):
        text = _PARENS.sub(" ", text)
    text = text.split(",", 1)[0]
    text = _LEADING.sub("", text.strip())
    text = re.sub(rf"^(?:{_UNITS})\.?\s+", "", text, flags=re.IGNORECASE)  # unit after "(14 oz)"
    text = " ".join(text.split()).lower()
    return text or original.lower()
