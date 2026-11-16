"""Tool logic as plain functions over a PaprikaClient, so it can be tested without FastMCP."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

import httpx

from .client import PaprikaClient
from .aisle_table import table_aisle
from .ingredients import ingredient_lines, ingredient_name

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


def _check_recipe_fields(fields: dict) -> dict:
    """Validate field names and coerce LLM-style values to Paprika's types. Returns a new dict."""
    bad = [k for k in fields if k not in RECIPE_DEFAULTS or k in READ_ONLY_RECIPE_FIELDS]
    if bad:
        raise ValueError(
            f"Unknown or read-only recipe field(s): {', '.join(sorted(bad))}. "
            f"Allowed: {', '.join(RECIPE_DEFAULTS)}"
        )
    return {k: _coerce_recipe_value(k, v) for k, v in fields.items()}


def _coerce_recipe_value(key: str, value: Any) -> Any:
    default = RECIPE_DEFAULTS[key]
    if value is None or default is None:
        return value
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError(f"Recipe field {key} must be true or false, got {value!r}")
        return value
    if key == "rating":
        try:
            rating = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"rating must be a whole number 0-5, got {value!r}") from exc
        if not 0 <= rating <= 5:
            raise ValueError(f"rating must be 0-5, got {rating}")
        return rating
    if key == "categories":
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, list) and all(isinstance(c, str) for c in value):
            return value
        raise ValueError(f"categories must be a list of category names, got {value!r}")
    if isinstance(default, str):
        if isinstance(value, list):
            return "\n".join(str(v) for v in value)
        return str(value)
    return value


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
    fields = _check_recipe_fields(fields)
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
    changes = _check_recipe_fields(changes)
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


def resolve_list_uid(client: PaprikaClient, list_uid: str | None) -> str:
    """Default list if None; else an exact uid or a list name (case-insensitive)."""
    if not list_uid:
        return default_list_uid(client)
    lists = client.list_grocery_lists()
    for gl in lists:
        if gl.get("uid") == list_uid:
            return list_uid
    for gl in lists:
        if (gl.get("name") or "").strip().lower() == list_uid.strip().lower():
            return gl["uid"]
    names = ", ".join(repr(gl.get("name")) for gl in lists)
    raise ValueError(f"Grocery list {list_uid!r} not found. Lists: {names}")


def list_grocery_items(client: PaprikaClient, list_uid: str | None = None, include_checked: bool = False) -> list[dict]:
    """Items on one list (default list if omitted); removed items are always hidden."""
    target = resolve_list_uid(client, list_uid)
    items = [i for i in client.list_grocery_items() if i.get("list_uid") == target and not i.get("deleted")]
    if not include_checked:
        items = [i for i in items if not i.get("purchased")]
    return items


class Aisles:
    """The account's aisles, its learned ingredient-to-aisle map, then a common-foods table.

    The server never assigns aisles, so the client has to.
    """

    def __init__(self, client: PaprikaClient) -> None:
        self.aisles = sorted(client.list_grocery_aisles(), key=lambda a: a.get("order_flag") or 0)
        by_uid = {a["uid"]: a for a in self.aisles}
        self.learned: dict[str, dict] = {}
        for g in client.list_grocery_ingredients():
            aisle = by_uid.get(g.get("aisle_uid"))
            if aisle and g.get("name"):
                self.learned.setdefault(str(g["name"]).strip().lower(), aisle)

    def named(self, name: str) -> dict:
        for a in self.aisles:
            if (a.get("name") or "").strip().lower() == str(name).strip().lower():
                return a
        names = ", ".join(a.get("name", "") for a in self.aisles)
        raise ValueError(f"Grocery aisle {name!r} not found. Aisles: {names}")

    def guess(self, ingredient: str) -> dict | None:
        n = ingredient.strip().lower()
        variants = [n, n + "s", n + "es"]
        if n.endswith("es"):
            variants.append(n[:-2])
        if n.endswith("s"):
            variants.append(n[:-1])
        for v in variants:
            if v in self.learned:
                return self.learned[v]
        fallback = table_aisle(n)
        if fallback:
            for a in self.aisles:
                if (a.get("name") or "").strip().lower() == fallback.lower():
                    return a
        return None


def list_grocery_aisles(client: PaprikaClient) -> list[dict]:
    """Aisles in store order, as {uid, name}."""
    return [{"uid": a["uid"], "name": a.get("name")} for a in Aisles(client).aisles]


def _new_grocery_item(list_uid: str, name: str, quantity: str | None = None,
                      instruction: str | None = None, recipe_uid: str | None = None,
                      ingredient: str | None = None, aisle: dict | None = None) -> dict:
    return {
        "uid": new_uid(),
        "recipe_uid": recipe_uid,
        "name": name,
        "order_flag": 0,
        "purchased": False,
        "aisle": aisle["name"] if aisle else "",
        "aisle_uid": aisle["uid"] if aisle else None,
        "ingredient": ingredient if ingredient is not None else ingredient_name(name),
        "recipe": None,
        "instruction": instruction or "",
        "quantity": quantity or "",
        "separate": False,
        "list_uid": list_uid,
    }


def add_grocery_items(client: PaprikaClient, items: list[dict], list_uid: str | None = None) -> list[dict]:
    """Add items ({name, quantity?, instruction?, recipe_uid?, aisle?}) in one request.

    Each item is filed into the aisle the account has learned for its ingredient,
    unless an explicit aisle name is given.
    """
    if not items:
        raise ValueError("No items given")
    target = resolve_list_uid(client, list_uid)
    aisles = Aisles(client)
    built = []
    for item in items:
        if not item.get("name"):
            raise ValueError(f"Grocery item is missing a name: {item!r}")
        ingredient = ingredient_name(item["name"])
        aisle = aisles.named(item["aisle"]) if item.get("aisle") else aisles.guess(ingredient)
        built.append(_new_grocery_item(
            target, item["name"], item.get("quantity"), item.get("instruction"), item.get("recipe_uid"),
            ingredient, aisle,
        ))
    client.upsert_grocery_items(built)
    client.notify()
    return built


def filing_report(items: list[dict]) -> dict:
    """Wrap added items with the ones no aisle was found for, and what to do about them."""
    unfiled = [{"uid": i["uid"], "name": i["name"]} for i in items if not i.get("aisle_uid")]
    report: dict = {"items": items, "unfiled": unfiled}
    if unfiled:
        report["next_step"] = (
            "These items are in Miscellaneous. If you can tell which aisle each belongs in, "
            "call update_grocery_item(uid, {\"aisle\": <name from list_grocery_aisles>}); "
            "leave any you're unsure of."
        )
    return report


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
    if "list_uid" in changes:
        changes = {**changes, "list_uid": resolve_list_uid(client, changes["list_uid"])}
    if changes.get("aisle"):
        aisle = Aisles(client).named(changes["aisle"])
        changes = {**changes, "aisle": aisle["name"], "aisle_uid": aisle["uid"]}
    elif "aisle" in changes:
        changes = {**changes, "aisle": "", "aisle_uid": None}
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


def add_recipe_to_grocery_list(client: PaprikaClient, recipe_uid: str, list_uid: str | None = None) -> list[dict]:
    """Add each ingredient line of a recipe as a grocery item (Paprika parses quantities)."""
    recipe = _fetch_recipe(client, recipe_uid)
    lines = ingredient_lines(recipe.get("ingredients", ""))
    if not lines:
        raise ValueError(f"Recipe {recipe.get('name', recipe_uid)!r} has no ingredients")
    return add_grocery_items(client, [{"name": line, "recipe_uid": recipe_uid} for line in lines], list_uid)
