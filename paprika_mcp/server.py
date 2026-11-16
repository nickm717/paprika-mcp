from fastmcp import FastMCP

from . import ops
from .client import PaprikaClient
from .config import RECIPE_CACHE_FILE, get_settings, token_cache_path
from .recipe_cache import RecipeCache

mcp = FastMCP("Paprika Recipe Manager")

def _client() -> PaprikaClient:
    settings = get_settings()
    return PaprikaClient(
        email=settings.paprika_email,
        password=settings.paprika_password,
        token_cache_path=token_cache_path(),
    )


@mcp.tool()
def get_sync_status() -> dict:
    """Get sync status counters for all Paprika resource types.

    Returns change counters (not total counts) that increment on each
    modification. Useful for detecting which resource types have changed
    since the last sync.
    """
    return _client().get_sync_status()


@mcp.tool()
def list_recipes() -> list[dict]:
    """List all recipes as lightweight {uid, hash} pairs.

    Returns only uid and hash for each recipe — not full recipe data.
    Use get_recipe(uid) to fetch complete details for a specific recipe.
    The hash field can be used to detect changes without re-fetching unchanged recipes.
    """
    return _client().list_recipes()


@mcp.tool()
def get_recipe(uid: str) -> dict:
    """Get full details for a specific recipe by its UID.

    Returns the complete recipe object including name, ingredients, directions,
    notes, nutrition, timing, rating, categories, source, and metadata.

    Args:
        uid: The recipe's unique identifier (uppercase UUID4 format).
    """
    return _client().get_recipe(uid)


@mcp.tool()
def list_categories() -> list[dict]:
    """List all recipe categories.

    Returns category uid, name, order_flag, and parent_uid (for nested categories).
    Recipe objects reference categories by name, not UID.
    """
    return _client().list_categories()


@mcp.tool()
def list_grocery_lists() -> list[dict]:
    """List all grocery lists.

    Returns each list's uid, name, order_flag, is_default, and reminders_list fields.
    Use the uid from this response to filter grocery items by list.
    """
    return _client().list_grocery_lists()


@mcp.tool()
def list_grocery_items(list_uid: str | None = None, include_checked: bool = False) -> list[dict]:
    """List grocery items on a list (the default list if list_uid is omitted).

    Returns items with uid, name, quantity, ingredient, aisle, purchased status
    and recipe reference. Removed items are never shown; bought (checked) items
    are hidden unless include_checked is true.
    """
    return ops.list_grocery_items(_client(), list_uid, include_checked)


@mcp.tool()
def list_meal_plans(start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """List meal plan entries, optionally between two dates (YYYY-MM-DD, inclusive).

    Each entry has uid, name, date, type (0=Breakfast, 1=Lunch, 2=Dinner, 3=Snack),
    a readable meal_type_name, and recipe_uid when linked to a recipe.
    """
    return ops.list_meals(_client(), start_date, end_date)


@mcp.tool()
def get_meals_for_date(date: str) -> list[dict]:
    """Get meal plan entries for one date (YYYY-MM-DD)."""
    return ops.list_meals(_client(), date, date)


@mcp.tool()
def add_meal(date: str, meal_type: str, name: str | None = None, recipe_uid: str | None = None) -> dict:
    """Add a meal to the meal plan.

    date: YYYY-MM-DD. meal_type: breakfast, lunch, dinner or snack.
    Give recipe_uid to link a recipe (its name is used if name is omitted),
    or just a name for a text-only meal.
    """
    return ops.add_meal(_client(), date, meal_type, name, recipe_uid)


@mcp.tool()
def update_meal(
    uid: str,
    date: str | None = None,
    meal_type: str | None = None,
    name: str | None = None,
    recipe_uid: str | None = None,
) -> dict:
    """Move or edit a meal plan entry. Only the fields you pass change.

    date: YYYY-MM-DD. meal_type: breakfast, lunch, dinner or snack.
    """
    return ops.update_meal(_client(), uid, date, meal_type, name, recipe_uid)


@mcp.tool()
def remove_meal(uid: str) -> dict:
    """DESTRUCTIVE: remove a meal from the meal plan. Confirm with the user first."""
    return ops.remove_meal(_client(), uid)


@mcp.tool()
def add_grocery_item(
    name: str,
    quantity: str | None = None,
    instruction: str | None = None,
    list_uid: str | None = None,
    recipe_uid: str | None = None,
) -> dict:
    """Add one grocery item. Omit list_uid to use the default grocery list.

    Paprika assigns the aisle itself. To add several items, use add_grocery_items.
    """
    item = {"name": name, "quantity": quantity, "instruction": instruction, "recipe_uid": recipe_uid}
    return ops.add_grocery_items(_client(), [item], list_uid)[0]


@mcp.tool()
def add_grocery_items(items: list[dict], list_uid: str | None = None) -> list[dict]:
    """Add several grocery items in one go. Omit list_uid to use the default list.

    Each item is {"name": str, "quantity": str (optional), "instruction": str (optional)},
    e.g. [{"name": "Eggs", "quantity": "12"}, {"name": "Milk"}].
    """
    return ops.add_grocery_items(_client(), items, list_uid)


@mcp.tool()
def update_grocery_item(uid: str, changes: dict) -> dict:
    """Change fields on a grocery item, e.g. {"quantity": "2"} or {"list_uid": "..."} to move it.

    Editable: name, quantity, instruction, purchased, list_uid, aisle, ingredient.
    Other fields are kept as they are in Paprika.
    """
    return ops.update_grocery_item(_client(), uid, changes)


@mcp.tool()
def check_grocery_items(uids: list[str]) -> list[dict]:
    """Mark grocery items as bought (checked off)."""
    return ops.set_grocery_items_checked(_client(), uids, True)


@mcp.tool()
def uncheck_grocery_items(uids: list[str]) -> list[dict]:
    """Mark grocery items as not bought (put them back on the list)."""
    return ops.set_grocery_items_checked(_client(), uids, False)


@mcp.tool()
def remove_grocery_items(uids: list[str]) -> list[dict]:
    """DESTRUCTIVE: remove grocery items from their list. Confirm with the user first.

    Paprika has no true delete for groceries; items are marked deleted and bought.
    """
    return ops.remove_grocery_items(_client(), uids)


@mcp.tool()
def search_recipes(query: str = "", ingredient: str = "", category: str = "", limit: int = 20) -> list[dict]:
    """Search your recipes by name, ingredient and/or category (all case-insensitive).

    `query` matches the recipe name, `ingredient` matches text in the ingredient
    list, `category` must equal a category name. Terms given are combined (AND).
    Trashed recipes are excluded. Returns summaries; use get_recipe(uid) for full
    details. The first call downloads every recipe and may be slow; later calls
    only fetch recipes that changed.
    """
    results = RecipeCache(RECIPE_CACHE_FILE).search(
        _client(), query=query, ingredient=ingredient, category=category, limit=limit
    )
    keys = ("uid", "name", "categories", "rating", "total_time")
    return [{k: r.get(k) for k in keys} for r in results]


@mcp.tool()
def create_recipe(
    name: str,
    ingredients: str = "",
    directions: str = "",
    description: str = "",
    notes: str = "",
    servings: str = "",
    prep_time: str = "",
    cook_time: str = "",
    total_time: str = "",
    categories: list[str] | None = None,
    source: str = "",
    source_url: str = "",
    rating: int = 0,
) -> dict:
    """Create a new recipe in Paprika.

    `ingredients` and `directions` are newline-separated text (one ingredient or
    step per line). `categories` are category names (see list_categories).
    Returns the created recipe including its new uid.
    """
    return ops.create_recipe(
        _client(),
        name=name,
        ingredients=ingredients,
        directions=directions,
        description=description,
        notes=notes,
        servings=servings,
        prep_time=prep_time,
        cook_time=cook_time,
        total_time=total_time,
        categories=categories or [],
        source=source,
        source_url=source_url,
        rating=rating,
    )


@mcp.tool()
def update_recipe(uid: str, changes: dict) -> dict:
    """Update fields on an existing recipe.

    `changes` maps field names to new values, e.g. {"rating": 4, "notes": "..."}.
    Only the given fields change; the latest version is fetched from Paprika
    first so edits made in the app are kept. Editable fields: name, ingredients,
    directions, description, notes, nutritional_info, servings, difficulty,
    prep_time, cook_time, total_time, rating, categories, source, source_url,
    on_favorites, is_pinned.
    """
    return ops.update_recipe(_client(), uid, changes)


@mcp.tool()
def trash_recipe(uid: str) -> dict:
    """DESTRUCTIVE: move a recipe to Paprika's trash. Confirm with the user first.

    Paprika has no permanent delete; the recipe can be restored from the trash in the app.
    """
    return ops.trash_recipe(_client(), uid)


def main() -> None:
    settings = get_settings()
    mcp.run(transport="http", host="127.0.0.1", port=settings.paprika_port)


if __name__ == "__main__":
    main()
