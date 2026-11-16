"""Turn a recipe's ingredient text into grocery item names."""

from __future__ import annotations

import re


def ingredient_lines(text: str) -> list[str]:
    """Non-empty, stripped lines, skipping section headers like 'For the sauce:'."""
    lines = (line.strip() for line in (text or "").splitlines())
    return [line for line in lines if line and not line.endswith(":") and not _NOT_AN_INGREDIENT.match(line)]


# Markdown section headers ("**Pasta**") and recipe-scaling widgets ("1x 2x 3x").
_NOT_AN_INGREDIENT = re.compile(r"^(?:\*\*.*\*\*|(?:\d+x\s*)+)$", re.IGNORECASE)


_QTY = r"(?:\d+(?:[.,/]\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞])"
_UNITS = (
    "cups?|c|tablespoons?|tbsps?|tbs|tbl|teaspoons?|tsps?|t|ounces?|oz|pounds?|lbs?|"
    "grams?|g|kilograms?|kgs?|kg|milliliters?|millilitres?|ml|liters?|litres?|l|"
    "cans?|tins?|jars?|packages?|pkgs?|packets?|bags?|boxes|box|bottles?|"
    "cloves?|pinch(?:es)?|dash(?:es)?|handfuls?|bunch(?:es)?|sprigs?|slices?|"
    "sticks?|heads?|stalks?|pieces?|grating"
)
# Words that describe an ingredient rather than name it ("ground" is kept: ground beef).
_DESCRIPTORS = (
    "a|an|some|of|good|large|medium|small|extra|finely|roughly|coarsely|thinly|freshly|fresh|"
    "grated|chopped|minced|diced|sliced|shredded|shelled|peeled|plain|light|runny|unwaxed|"
    "ripe|softened|melted|packed|heaped|heaping|level|boneless|skinless|toasted|homemade|"
    "store-bought|store bought|low-sodium|reduced-sodium|long|thick-cut|thin|thick|or|"
    "shelf-stable|refrigerated|cooked|uncooked|halved"
)
_LEAD = re.compile(
    rf"^(?:{_QTY}(?:\s*(?:-|–|to)\s*{_QTY})?|[/-]|(?:juice|zest) of|(?:{_UNITS})(?:\.|\b)|(?:{_DESCRIPTORS})\b)\s*",
    re.IGNORECASE,
)
_ALTERNATIVES = re.compile(r"(?:\s+(?:or|and|to serve|for)\s+|\s*/).*$")
_KEEP_WHOLE = {"half and half"}
_PARENS = re.compile(r"\([^()]*\)")


def ingredient_name(line: str) -> str:
    """Best-effort ingredient from a grocery line: '2 cups/250 g flour, sifted' -> 'flour'."""
    original = (line or "").strip()
    text = ""
    for segment in _segments(_strip_parens(original)):
        text = segment
        while True:
            stripped = _LEAD.sub("", text, count=1)
            if stripped == text:
                break
            text = stripped
        if text:  # "boneless, skinless pork" -> first segment is all descriptors, try the next
            break
    if text not in _KEEP_WHOLE:
        text = _ALTERNATIVES.sub("", text)
    text = text.strip()
    return text or original.lower()


def _strip_parens(text: str) -> str:
    while _PARENS.search(text):
        text = _PARENS.sub(" ", text)
    return text


def _segments(text: str) -> list[str]:
    """Comma-separated parts of a line, lower-cased with whitespace collapsed."""
    return [" ".join(part.split()).lower() for part in text.split(",")]
