"""Local recipe cache keyed by Paprika's per-recipe hash, plus search over it."""

from __future__ import annotations

import json
import os
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
        for entry in client.list_recipes():
            uid, h = entry["uid"], entry.get("hash")
            hit = cached.get(uid)
            if hit and hit.get("hash") == h:
                fresh[uid] = hit
            else:
                fresh[uid] = {"hash": h, "recipe": client.get_recipe(uid)}
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
            if q and q not in (r.get("name") or "").lower():
                continue
            if ing and ing not in (r.get("ingredients") or "").lower():
                continue
            if cat and cat not in [c.lower() for c in r.get("categories") or []]:
                continue
            results.append(r)
        results.sort(key=lambda r: (r.get("name") or "").lower())
        return results[:limit]
