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


# --- Meal plan ---

MEAL_TYPES = {0: "Breakfast", 1: "Lunch", 2: "Dinner", 3: "Snack"}
_MEAL_TYPE_BY_NAME = {v.lower(): k for k, v in MEAL_TYPES.items()}


def parse_meal_type(value: str | int) -> int:
    if isinstance(value, int) and value in MEAL_TYPES:
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _MEAL_TYPE_BY_NAME:
            return _MEAL_TYPE_BY_NAME[v]
        if v.isdigit() and int(v) in MEAL_TYPES:
            return int(v)
    raise ValueError(f"Unknown meal type {value!r}. Use one of: breakfast, lunch, dinner, snack")


def parse_date(value: str) -> str:
    try:
        d = datetime.strptime(value.strip()[:10], "%Y-%m-%d")
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid date {value!r}; use YYYY-MM-DD, e.g. 2026-11-20") from exc
    return d.strftime("%Y-%m-%d 00:00:00")


def add_meal(client: PaprikaClient, date: str, meal_type: str | int,
             name: str | None = None, recipe_uid: str | None = None) -> dict:
    if not name and not recipe_uid:
        raise ValueError("Give a name or recipe_uid for the meal")
    meal_date, type_num = parse_date(date), parse_meal_type(meal_type)
    if not name:
        name = _fetch_recipe(client, recipe_uid)["name"]
    meal = {
        "uid": new_uid(),
        "recipe_uid": recipe_uid,
        "date": meal_date,
        "type": type_num,
        "name": name,
        "order_flag": 0,
        "type_uid": "",
        "scale": None,
        "is_ingredient": False,
        "deleted": False,
    }
    client.upsert_meals([meal])
    client.notify()
    return meal


def _fetch_meal(client: PaprikaClient, uid: str) -> dict:
    for meal in client.list_meal_plans():
        if meal.get("uid") == uid:
            return meal
    raise ValueError(f"Meal {uid} not found")


def _save_meal(client: PaprikaClient, meal: dict) -> dict:
    client.upsert_meals([meal])
    client.notify()
    return meal


def update_meal(client: PaprikaClient, uid: str, date: str | None = None, meal_type: str | int | None = None,
                name: str | None = None, recipe_uid: str | None = None) -> dict:
    changes: dict = {}
    if date is not None:
        changes["date"] = parse_date(date)
    if meal_type is not None:
        changes["type"] = parse_meal_type(meal_type)
    if name is not None:
        changes["name"] = name
    if recipe_uid is not None:
        changes["recipe_uid"] = recipe_uid
    meal = _fetch_meal(client, uid)
    meal.update(changes)
    return _save_meal(client, meal)


def remove_meal(client: PaprikaClient, uid: str) -> dict:
    meal = _fetch_meal(client, uid)
    meal["deleted"] = True
    return _save_meal(client, meal)


def list_meals(client: PaprikaClient, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Meal plan entries (removed ones hidden), optionally within an inclusive date range."""
    start = parse_date(start_date)[:10] if start_date else None
    end = parse_date(end_date)[:10] if end_date else None
    result = []
    for meal in client.list_meal_plans():
        if meal.get("deleted"):
            continue
        day = (meal.get("date") or "")[:10]
        if (start and day < start) or (end and day > end):
            continue
        meal["meal_type_name"] = MEAL_TYPES.get(meal.get("type"), "Unknown")
        result.append(meal)
    return result
