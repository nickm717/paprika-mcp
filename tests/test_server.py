import asyncio

from paprika_mcp.server import mcp

EXPECTED = {
    "get_sync_status", "list_recipes", "get_recipe", "search_recipes", "create_recipe", "update_recipe",
    "trash_recipe", "list_categories", "list_grocery_lists", "list_grocery_aisles", "list_grocery_items", "add_grocery_item",
    "add_grocery_items", "update_grocery_item", "check_grocery_items", "uncheck_grocery_items",
    "remove_grocery_items", "list_meal_plans", "get_meals_for_date", "add_meal", "update_meal",
    "remove_meal", "list_pantry_items", "add_recipe_to_grocery_list",
}
DESTRUCTIVE = {"trash_recipe", "remove_grocery_items", "remove_meal"}


def _tools():
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def test_all_tools_registered():
    assert set(_tools()) == EXPECTED


def test_destructive_tools_are_flagged():
    tools = _tools()
    for name in DESTRUCTIVE:
        assert tools[name].description.startswith("DESTRUCTIVE:"), name
    for name in EXPECTED - DESTRUCTIVE:
        assert "DESTRUCTIVE" not in (tools[name].description or ""), name
