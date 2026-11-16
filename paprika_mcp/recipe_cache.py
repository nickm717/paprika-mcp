"""Local recipe cache keyed by Paprika's per-recipe hash, plus search over it."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .client import PaprikaClient


class RecipeCache:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)

    def sync(self, client: PaprikaClient) -> list[dict]:
        """Refresh the cache, fetching only recipes whose hash changed. Returns all recipes."""
        cached = self._load()
        fresh: dict = {}
        try:
            for n, entry in enumerate(client.list_recipes(), 1):
                uid, h = entry["uid"], entry.get("hash")
                hit = cached.get(uid)
                if hit and hit.get("hash") == h:
                    fresh[uid] = hit
                    continue
                try:
                    fresh[uid] = {"hash": h, "recipe": client.get_recipe(uid)}
                except Exception as exc:
                    # Keep the stale copy (old hash, so it's retried next sync) or skip it.
                    print(f"paprika-mcp: could not fetch recipe {uid}: {exc}", file=sys.stderr)
                    if hit:
                        fresh[uid] = hit
                if n % 50 == 0:
                    self._save({**cached, **fresh})
        except Exception:
            self._save({**cached, **fresh})  # keep progress if the listing itself breaks off
            raise
        self._save(fresh)
        return [v["recipe"] for v in fresh.values()]

    def search(
        self,
        client: PaprikaClient,
        query: str = "",
        ingredient: str = "",
        category: str = "",
        include_trashed: bool = False,
        limit: int = 20,
    ) -> list[dict]:
        """Return recipes matching every given term (case-insensitive)."""
        q, ing, cat = query.lower(), ingredient.lower(), category.lower()
        results = []
        for r in self.sync(client):
            if r.get("in_trash") and not include_trashed:
                continue
            if q and q not in _text(r.get("name")):
                continue
            if ing and ing not in _text(r.get("ingredients")):
                continue
            cats = r.get("categories") or []
            if isinstance(cats, str):
                cats = [cats]
            if cat and cat not in [str(c).lower() for c in cats]:
                continue
            results.append(r)
        results.sort(key=lambda r: _text(r.get("name")))
        return results[:limit]


def _text(value) -> str:
    """Lower-cased text of a field that should be a string but might not be."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value).lower()
    return str(value).lower()
