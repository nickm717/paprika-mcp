import re

import httpx
import pytest

from paprika_mcp import ops
from tests.conftest import API, decode_upload

UID = "07975578-DE1A-42AB-B184-6E8FCB9AB753"
UPPER_UUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$")

SAMPLE = {
    "uid": UID,
    "name": "Jordan Marsh's Blueberry Muffins",
    "ingredients": "2 cups flour\n1 egg",
    "directions": "Bake.",
    "description": "",
    "notes": "Best fresh.",
    "nutritional_info": "",
    "servings": "12 muffins",
    "difficulty": "",
    "prep_time": "15 min",
    "cook_time": "25 min",
    "total_time": "40 min",
    "rating": 5,
    "categories": ["Breakfast", "Baking"],
    "source": "",
    "source_url": "",
    "image_url": "",
    "photo": "photo_filename.jpg",
    "photo_hash": "abc",
    "photo_large": None,
    "photo_url": "https://uploads.paprikaapp.com/x",
    "hash": "a" * 64,
    "created": "2024-06-15 10:30:00",
    "on_favorites": True,
    "on_grocery_list": None,
    "in_trash": False,
    "is_pinned": False,
    "scale": None,
}


def _mock_get(mock_api, status=200, body=None):
    return mock_api.get(f"{API}/v2/sync/recipe/{UID}/").mock(
        return_value=httpx.Response(status, json=body if body is not None else {"result": dict(SAMPLE)})
    )


def _mock_post(mock_api, uid=UID):
    mock_api.post(f"{API}/v2/sync/notify/").mock(return_value=httpx.Response(200, json={}))
    return mock_api.post(url__regex=rf"{re.escape(API)}/v2/sync/recipe/[^/]+/").mock(
        return_value=httpx.Response(200, json={"result": True})
    )


def test_create_recipe_posts_full_object(client, mock_api):
    route = _mock_post(mock_api)

    recipe = ops.create_recipe(client, name="Test Soup", ingredients="1 onion")

    uploaded = decode_upload(route.calls[0].request)
    assert UPPER_UUID.match(uploaded["uid"])
    assert route.calls[0].request.url.path == f"/api/v2/sync/recipe/{uploaded['uid']}/"
    assert uploaded["name"] == "Test Soup"
    assert uploaded["ingredients"] == "1 onion"
    assert uploaded["in_trash"] is False
    assert uploaded["categories"] == []
    assert re.fullmatch(r"[0-9a-f]{64}", uploaded["hash"])
    assert recipe == uploaded


def test_update_recipe_preserves_untouched_fields(client, mock_api):
    _mock_get(mock_api)
    route = _mock_post(mock_api)

    ops.update_recipe(client, UID, {"rating": 4})

    uploaded = decode_upload(route.calls[0].request)
    assert uploaded["rating"] == 4
    assert uploaded["hash"] != SAMPLE["hash"]
    for key, value in SAMPLE.items():
        if key not in ("rating", "hash"):
            assert uploaded[key] == value, key


def test_update_recipe_unknown_uid_raises(client, mock_api):
    _mock_get(mock_api, status=404, body={"error": "Not found"})
    route = _mock_post(mock_api)

    with pytest.raises(ValueError, match="not found"):
        ops.update_recipe(client, UID, {"rating": 4})

    assert not route.called


def test_update_recipe_rejects_unknown_field(client, mock_api):
    _mock_get(mock_api)
    route = _mock_post(mock_api)

    with pytest.raises(ValueError, match="colour"):
        ops.update_recipe(client, UID, {"colour": "red"})

    assert not route.called


def test_trash_recipe_sets_in_trash(client, mock_api):
    _mock_get(mock_api)
    route = _mock_post(mock_api)

    ops.trash_recipe(client, UID)

    assert decode_upload(route.calls[0].request)["in_trash"] is True
