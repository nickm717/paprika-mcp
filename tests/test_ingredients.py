import httpx

from paprika_mcp import ops
from paprika_mcp.ingredients import ingredient_lines
from tests.conftest import API, decode_upload


def test_ingredient_lines_skips_blank_and_headers():
    assert ingredient_lines("2 cups flour\n\nFor the sauce:\n 1 egg ") == ["2 cups flour", "1 egg"]


def test_add_recipe_to_grocery_list(client, mock_api):
    mock_api.get(f"{API}/v2/sync/recipe/R1/").mock(
        return_value=httpx.Response(200, json={"result": {"uid": "R1", "name": "Soup", "ingredients": "1 onion\nDressing:\n2 carrots"}})
    )
    mock_api.get(f"{API}/v2/sync/grocerylists/").mock(
        return_value=httpx.Response(200, json={"result": [{"uid": "L1", "name": "Costco"}]})
    )
    mock_api.get(f"{API}/v2/sync/groceryaisles/").mock(return_value=httpx.Response(200, json={"result": []}))
    mock_api.get(f"{API}/v2/sync/groceryingredients/").mock(return_value=httpx.Response(200, json={"result": []}))
    mock_api.post(f"{API}/v2/sync/notify/").mock(return_value=httpx.Response(200, json={}))
    route =mock_api.post(f"{API}/v2/sync/groceries/").mock(return_value=httpx.Response(200, json={"result": True}))

    ops.add_recipe_to_grocery_list(client, "R1", "L1")

    assert route.call_count == 1
    uploaded = decode_upload(route.calls[0].request)
    assert [i["name"] for i in uploaded] == ["1 onion", "2 carrots"]
    assert all(i["recipe_uid"] == "R1" and i["list_uid"] == "L1" for i in uploaded)


def test_list_pantry_items(client, mock_api):
    route = mock_api.get(f"{API}/v2/sync/pantry/").mock(
        return_value=httpx.Response(200, json={"result": [{"uid": "P1", "ingredient": "rice"}]})
    )

    assert client.list_pantry_items() == [{"uid": "P1", "ingredient": "rice"}]
    assert route.called
