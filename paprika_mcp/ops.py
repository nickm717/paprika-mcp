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


# --- Groceries ---

def default_list_uid(client: PaprikaClient) -> str:
    lists = client.list_grocery_lists()
    if not lists:
        raise ValueError("No grocery lists exist in Paprika")
    for gl in lists:
        if gl.get("is_default"):
            return gl["uid"]
    return lists[0]["uid"]


def list_grocery_items(client: PaprikaClient, list_uid: str | None = None, include_checked: bool = False) -> list[dict]:
    """Items on one list (default list if omitted); removed items are always hidden."""
    target = list_uid or default_list_uid(client)
    items = [i for i in client.list_grocery_items() if i.get("list_uid") == target and not i.get("deleted")]
    if not include_checked:
        items = [i for i in items if not i.get("purchased")]
    return items


def _new_grocery_item(list_uid: str, name: str, quantity: str | None = None,
                      instruction: str | None = None, recipe_uid: str | None = None) -> dict:
    return {
        "uid": new_uid(),
        "recipe_uid": recipe_uid,
        "name": name,
        "order_flag": 0,
        "purchased": False,
        "aisle": "",
        "ingredient": name.lower(),
        "recipe": None,
        "instruction": instruction or "",
        "quantity": quantity or "",
        "separate": False,
        "list_uid": list_uid,
    }


def add_grocery_items(client: PaprikaClient, items: list[dict], list_uid: str | None = None) -> list[dict]:
    """Add items ({name, quantity?, instruction?, recipe_uid?}) in one request."""
    if not items:
        raise ValueError("No items given")
    target = list_uid or default_list_uid(client)
    built = []
    for item in items:
        if not item.get("name"):
            raise ValueError(f"Grocery item is missing a name: {item!r}")
        built.append(_new_grocery_item(
            target, item["name"], item.get("quantity"), item.get("instruction"), item.get("recipe_uid")
        ))
    client.upsert_grocery_items(built)
    client.notify()
    return built


def _fetch_grocery_items(client: PaprikaClient, uids: list[str]) -> list[dict]:
    by_uid = {i["uid"]: i for i in client.list_grocery_items()}
    missing = [u for u in uids if u not in by_uid]
    if missing:
        raise ValueError(f"Grocery item(s) not found: {', '.join(missing)}")
    return [by_uid[u] for u in uids]


def _save_grocery_items(client: PaprikaClient, items: list[dict]) -> list[dict]:
    client.upsert_grocery_items(items)
    client.notify()
    return items


GROCERY_EDITABLE = {"name", "quantity", "instruction", "purchased", "list_uid", "aisle", "ingredient"}


def update_grocery_item(client: PaprikaClient, uid: str, changes: dict) -> dict:
    bad = sorted(set(changes) - GROCERY_EDITABLE)
    if bad:
        raise ValueError(f"Unknown grocery field(s): {', '.join(bad)}. Allowed: {', '.join(sorted(GROCERY_EDITABLE))}")
    (item,) = _fetch_grocery_items(client, [uid])
    item.update(changes)
    return _save_grocery_items(client, [item])[0]


def set_grocery_items_checked(client: PaprikaClient, uids: list[str], checked: bool) -> list[dict]:
    items = _fetch_grocery_items(client, uids)
    for item in items:
        item["purchased"] = checked
    return _save_grocery_items(client, items)


def remove_grocery_items(client: PaprikaClient, uids: list[str]) -> list[dict]:
    """Soft delete: Paprika has no real delete for groceries."""
    items = _fetch_grocery_items(client, uids)
    for item in items:
        item["purchased"] = True
        item["deleted"] = True
    return _save_grocery_items(client, items)
