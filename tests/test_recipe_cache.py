import json
import re

import httpx
import pytest

from paprika_mcp.recipe_cache import RecipeCache
from tests.conftest import API


def recipe(uid, name, ingredients="", categories=(), in_trash=False, h="h"):
    return {
        "uid": uid,
        "name": name,
        "ingredients": ingredients,
        "categories": list(categories),
        "in_trash": in_trash,
        "rating": 0,
        "total_time": "",
        "hash": h,
    }


@pytest.fixture
def server_recipes():
    return {}


@pytest.fixture
def api(mock_api, server_recipes):
    """Serve server_recipes from the list + per-recipe endpoints; return the per-recipe route."""
    mock_api.get(f"{API}/v2/sync/recipes/").mock(
        side_effect=lambda req: httpx.Response(
            200, json={"result": [{"uid": u, "hash": r["hash"]} for u, r in server_recipes.items()]}
        )
    )

    def one(request):
        uid = re.search(r"/recipe/([^/]+)/", request.url.path).group(1)
        return httpx.Response(200, json={"result": server_recipes[uid]})

    return mock_api.get(url__regex=rf"{re.escape(API)}/v2/sync/recipe/[^/]+/").mock(side_effect=one)


def fetched_uids(route):
    return sorted(re.search(r"/recipe/([^/]+)/", c.request.url.path).group(1) for c in route.calls)


def test_sync_fetches_only_changed(tmp_path, client, api, server_recipes):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({
        "A": {"hash": "h1", "recipe": recipe("A", "Apple", h="h1")},
        "B": {"hash": "h2", "recipe": recipe("B", "Banana", h="h2")},
        "GONE": {"hash": "g", "recipe": recipe("GONE", "Gone", h="g")},
    }))
    server_recipes.update(
        A=recipe("A", "Apple", h="h1"),
        B=recipe("B", "Banana bread", h="h2x"),
        C=recipe("C", "Cherry", h="h3"),
    )

    recipes = RecipeCache(path).sync(client)

    assert fetched_uids(api) == ["B", "C"]
    assert sorted(r["uid"] for r in recipes) == ["A", "B", "C"]
    assert {r["uid"]: r["name"] for r in recipes}["B"] == "Banana bread"
    assert "GONE" not in json.loads(path.read_text())


def test_search_matches_name_case_insensitive(tmp_path, client, api, server_recipes):
    server_recipes.update(A=recipe("A", "Chicken Tikka"), B=recipe("B", "Beef Stew"))

    results = RecipeCache(tmp_path / "c.json").search(client, query="chicken")

    assert [r["uid"] for r in results] == ["A"]


def test_search_by_ingredient(tmp_path, client, api, server_recipes):
    server_recipes.update(
        A=recipe("A", "Soup", ingredients="1 onion\n2 carrots"),
        B=recipe("B", "Salad", ingredients="lettuce"),
    )

    results = RecipeCache(tmp_path / "c.json").search(client, ingredient="Carrot")

    assert [r["uid"] for r in results] == ["A"]


def test_search_by_category(tmp_path, client, api, server_recipes):
    server_recipes.update(
        A=recipe("A", "Pancakes", categories=["Breakfast"]),
        B=recipe("B", "Breakfast Burrito Bowl", categories=["Dinner"]),
    )

    results = RecipeCache(tmp_path / "c.json").search(client, category="breakfast")

    assert [r["uid"] for r in results] == ["A"]


def test_search_excludes_trashed_by_default(tmp_path, client, api, server_recipes):
    server_recipes.update(A=recipe("A", "Old Soup", in_trash=True), B=recipe("B", "New Soup"))
    cache = RecipeCache(tmp_path / "c.json")

    assert [r["uid"] for r in cache.search(client, query="soup")] == ["B"]
    assert len(cache.search(client, query="soup", include_trashed=True)) == 2


def test_corrupt_cache_file_rebuilds(tmp_path, client, api, server_recipes):
    path = tmp_path / "c.json"
    path.write_text("not json")
    server_recipes.update(A=recipe("A", "Apple"))

    recipes = RecipeCache(path).sync(client)

    assert [r["uid"] for r in recipes] == ["A"]
    assert "A" in json.loads(path.read_text())
