"""Tool logic as plain functions over a PaprikaClient, so it can be tested without FastMCP."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

import httpx

from .client import PaprikaClient

# Writable recipe fields and their defaults (API_REFERENCE.md "Recipe Object Fields").
RECIPE_DEFAULTS: dict[str, Any] = {
    "name": "",
    "ingredients": "",
    "directions": "",
    "description": "",
    "notes": "",
    "nutritional_info": "",
    "servings": "",
    "difficulty": "",
    "prep_time": "",
    "cook_time": "",
    "total_time": "",
    "rating": 0,
    "categories": [],
    "source": "",
    "source_url": "",
    "image_url": "",
    "photo": "",
    "photo_hash": "",
    "photo_large": None,
    "created": "",
    "on_favorites": False,
    "on_grocery_list": None,
    "in_trash": False,
    "is_pinned": False,
    "scale": None,
}
READ_ONLY_RECIPE_FIELDS = {"uid", "hash", "photo_url"}


def new_uid() -> str:
    return str(uuid.uuid4()).upper()


def new_hash() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


def _check_recipe_fields(fields: dict) -> None:
    bad = [k for k in fields if k not in RECIPE_DEFAULTS or k in READ_ONLY_RECIPE_FIELDS]
    if bad:
        raise ValueError(
            f"Unknown or read-only recipe field(s): {', '.join(sorted(bad))}. "
            f"Allowed: {', '.join(RECIPE_DEFAULTS)}"
        )


def _fetch_recipe(client: PaprikaClient, uid: str) -> dict:
    try:
        recipe = client.get_recipe(uid)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(f"Recipe {uid} not found") from exc
        raise
    if not recipe:
        raise ValueError(f"Recipe {uid} not found")
    return recipe


def create_recipe(client: PaprikaClient, name: str, ingredients: str = "", directions: str = "", **fields: Any) -> dict:
    _check_recipe_fields(fields)
    recipe = {k: (list(v) if isinstance(v, list) else v) for k, v in RECIPE_DEFAULTS.items()}
    recipe.update(fields)
    recipe.update(
        uid=new_uid(),
        hash=new_hash(),
        name=name,
        ingredients=ingredients,
        directions=directions,
        created=fields.get("created") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    client.upsert_recipe(recipe)
    client.notify()
    return recipe


def update_recipe(client: PaprikaClient, uid: str, changes: dict) -> dict:
    _check_recipe_fields(changes)
    recipe = _fetch_recipe(client, uid)
    recipe.update(changes)
    recipe["hash"] = new_hash()
    client.upsert_recipe(recipe)
    client.notify()
    return recipe


def trash_recipe(client: PaprikaClient, uid: str) -> dict:
    return update_recipe(client, uid, {"in_trash": True})
