import re

import httpx
import pytest

from paprika_mcp import ops
from tests.conftest import API, decode_upload

UPPER_UUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$")

LISTS = [
    {"uid": "L1", "name": "Costco", "order_flag": 0, "is_default": False},
    {"uid": "L2", "name": "My Grocery List", "order_flag": 1, "is_default": True},
]
ITEM = {
    "uid": "I1",
    "recipe_uid": None,
    "name": "Milk",
    "order_flag": 3,
    "purchased": False,
    "aisle": "Dairy",
    "ingredient": "milk",
    "recipe": None,
    "instruction": "",
    "quantity": "1 gal",
    "separate": False,
    "list_uid": "L2",
}


@pytest.fixture
def api(mock_api):
    mock_api.get(f"{API}/v2/sync/grocerylists/").mock(return_value=httpx.Response(200, json={"result": LISTS}))
    mock_api.get(f"{API}/v2/sync/groceries/").mock(return_value=httpx.Response(200, json={"result": [dict(ITEM)]}))
    mock_api.get(f"{API}/v2/sync/groceryaisles/").mock(return_value=httpx.Response(200, json={"result": []}))
    mock_api.get(f"{API}/v2/sync/groceryingredients/").mock(return_value=httpx.Response(200, json={"result": []}))
    mock_api.post(f"{API}/v2/sync/notify/").mock(return_value=httpx.Response(200, json={}))
    return mock_api.post(f"{API}/v2/sync/groceries/").mock(return_value=httpx.Response(200, json={"result": True}))


def test_add_items_single_post_array(client, api):
    ops.add_grocery_items(client, [{"name": "Eggs"}, {"name": "Bread", "quantity": "2"}, {"name": "Apples"}], "L1")

    assert api.call_count == 1
    uploaded = decode_upload(api.calls[0].request)
    assert [i["name"] for i in uploaded] == ["Eggs", "Bread", "Apples"]
    for item in uploaded:
        assert UPPER_UUID.match(item["uid"])
        assert item["aisle"] == ""
        assert item["ingredient"] == item["name"].lower()  # bare names parse to themselves
        assert item["aisle_uid"] is None
        assert item["list_uid"] == "L1"
        assert item["purchased"] is False
    assert uploaded[1]["quantity"] == "2"


def test_add_items_defaults_to_default_list(client, api):
    ops.add_grocery_items(client, [{"name": "Eggs"}])

    assert decode_upload(api.calls[0].request)[0]["list_uid"] == "L2"


def test_default_list_falls_back_to_first(client, mock_api):
    mock_api.get(f"{API}/v2/sync/grocerylists/").mock(
        return_value=httpx.Response(200, json={"result": [{"uid": "X", "is_default": False}, {"uid": "Y"}]})
    )

    assert ops.default_list_uid(client) == "X"


def test_update_item_preserves_other_fields(client, api):
    ops.update_grocery_item(client, "I1", {"quantity": "2 gal"})

    uploaded = decode_upload(api.calls[0].request)
    assert uploaded == [{**ITEM, "quantity": "2 gal"}]


def test_update_unknown_item_raises(client, api):
    with pytest.raises(ValueError, match="not found"):
        ops.update_grocery_item(client, "NOPE", {"quantity": "2"})

    assert not api.called


def test_check_and_uncheck(client, api):
    ops.set_grocery_items_checked(client, ["I1"], True)
    ops.set_grocery_items_checked(client, ["I1"], False)

    assert decode_upload(api.calls[0].request)[0]["purchased"] is True
    assert decode_upload(api.calls[1].request)[0]["purchased"] is False


def test_remove_sets_purchased_and_deleted(client, api):
    ops.remove_grocery_items(client, ["I1"])

    uploaded = decode_upload(api.calls[0].request)[0]
    assert uploaded["purchased"] is True
    assert uploaded["deleted"] is True
    assert uploaded["name"] == "Milk"


def test_list_items_filters_list_checked_and_deleted(client, mock_api):
    items = [
        {**ITEM, "uid": "A"},
        {**ITEM, "uid": "B", "purchased": True},
        {**ITEM, "uid": "C", "purchased": True, "deleted": True},
        {**ITEM, "uid": "D", "list_uid": "L1"},
    ]
    mock_api.get(f"{API}/v2/sync/groceries/").mock(return_value=httpx.Response(200, json={"result": items}))
    mock_api.get(f"{API}/v2/sync/grocerylists/").mock(return_value=httpx.Response(200, json={"result": LISTS}))

    assert [i["uid"] for i in ops.list_grocery_items(client, "L2")] == ["A"]
    assert [i["uid"] for i in ops.list_grocery_items(client, None, include_checked=True)] == ["A", "B"]


def test_list_uid_resolves_by_name(client, api):
    ops.add_grocery_items(client, [{"name": "Eggs"}], "costco")

    assert decode_upload(api.calls[0].request)[0]["list_uid"] == "L1"


def test_unknown_list_raises(client, api):
    with pytest.raises(ValueError, match="Grocery list 'Groceries' not found"):
        ops.add_grocery_items(client, [{"name": "Eggs"}], "Groceries")
    with pytest.raises(ValueError, match="not found"):
        ops.list_grocery_items(client, "BOGUS")
    with pytest.raises(ValueError, match="not found"):
        ops.update_grocery_item(client, "I1", {"list_uid": "BOGUS"})

    assert not api.called
