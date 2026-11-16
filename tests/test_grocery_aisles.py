import httpx
import pytest

from paprika_mcp import ops
from tests.conftest import API, decode_upload

LISTS = [{"uid": "L1", "name": "My Grocery List", "is_default": True}]
AISLES = [
    {"uid": "A_DAIRY", "name": "Dairy", "order_flag": 3},
    {"uid": "A_BAKING", "name": "Baking Goods", "order_flag": 2},
    {"uid": "A_PRODUCE", "name": "Produce", "order_flag": 1},
]
LEARNED = [
    {"uid": "G1", "name": "flour", "aisle_uid": "A_BAKING"},
    {"uid": "G2", "name": "eggs", "aisle_uid": "A_DAIRY"},
    {"uid": "G3", "name": "Banana", "aisle_uid": "A_PRODUCE"},
]
ITEM = {"uid": "I1", "name": "Milk", "ingredient": "milk", "aisle": "", "purchased": False, "list_uid": "L1"}


@pytest.fixture
def api(mock_api):
    mock_api.get(f"{API}/v2/sync/grocerylists/").mock(return_value=httpx.Response(200, json={"result": LISTS}))
    mock_api.get(f"{API}/v2/sync/groceryaisles/").mock(return_value=httpx.Response(200, json={"result": AISLES}))
    mock_api.get(f"{API}/v2/sync/groceryingredients/").mock(return_value=httpx.Response(200, json={"result": LEARNED}))
    mock_api.get(f"{API}/v2/sync/groceries/").mock(return_value=httpx.Response(200, json={"result": [dict(ITEM)]}))
    mock_api.post(f"{API}/v2/sync/notify/").mock(return_value=httpx.Response(200, json={}))
    return mock_api.post(f"{API}/v2/sync/groceries/").mock(return_value=httpx.Response(200, json={"result": True}))


def filed(route):
    return {i["name"]: (i["ingredient"], i["aisle"], i["aisle_uid"]) for i in decode_upload(route.calls[0].request)}


def test_add_items_files_into_learned_aisles(client, api):
    ops.add_grocery_items(client, [{"name": "2 cups flour"}, {"name": "1 egg"}, {"name": "bananas"}, {"name": "cheddar cheese"}])

    assert filed(api) == {
        "2 cups flour": ("flour", "Baking Goods", "A_BAKING"),
        "1 egg": ("egg", "Dairy", "A_DAIRY"),
        "bananas": ("bananas", "Produce", "A_PRODUCE"),
        "cheddar cheese": ("cheddar cheese", "Dairy", "A_DAIRY"),  # via the table
    }


def test_explicit_aisle_wins_and_is_case_insensitive(client, api):
    ops.add_grocery_items(client, [{"name": "flour", "aisle": "dairy"}])

    assert filed(api)["flour"] == ("flour", "Dairy", "A_DAIRY")


def test_unknown_explicit_aisle_raises_listing_aisles(client, api):
    with pytest.raises(ValueError, match="Produce, Baking Goods, Dairy"):
        ops.add_grocery_items(client, [{"name": "flour", "aisle": "Spaceship"}])

    assert not api.called


def test_update_item_aisle_by_name(client, api):
    ops.update_grocery_item(client, "I1", {"aisle": "Produce"})

    (item,) = decode_upload(api.calls[0].request)
    assert (item["aisle"], item["aisle_uid"]) == ("Produce", "A_PRODUCE")


def test_add_recipe_to_grocery_list_files_aisles(client, api, mock_api):
    mock_api.get(f"{API}/v2/sync/recipe/R1/").mock(
        return_value=httpx.Response(200, json={"result": {"uid": "R1", "name": "Cake", "ingredients": "2 cups flour\n3 eggs"}})
    )

    ops.add_recipe_to_grocery_list(client, "R1")

    assert {n: a for n, (_, a, _) in filed(api).items()} == {"2 cups flour": "Baking Goods", "3 eggs": "Dairy"}


def test_list_grocery_aisles_in_store_order(client, api):
    assert [a["name"] for a in ops.list_grocery_aisles(client)] == ["Produce", "Baking Goods", "Dairy"]


def test_update_item_clearing_aisle_clears_uid(client, api, mock_api):
    mock_api.get(f"{API}/v2/sync/groceries/").mock(
        return_value=httpx.Response(200, json={"result": [{**ITEM, "aisle": "Dairy", "aisle_uid": "A_DAIRY"}]})
    )

    ops.update_grocery_item(client, "I1", {"aisle": ""})

    (item,) = decode_upload(api.calls[0].request)
    assert (item["aisle"], item["aisle_uid"]) == ("", None)


def test_common_foods_fall_back_to_table(client, api):
    ops.add_grocery_items(client, [{"name": "1 cup milk"}, {"name": "2 lb chicken thighs"}, {"name": "unicorn dust"}])

    got = filed(api)
    assert got["1 cup milk"][1:] == ("Dairy", "A_DAIRY")
    assert got["unicorn dust"][1:] == ("", None)
    assert got["2 lb chicken thighs"][1:] == ("", None)  # "Meat" isn't one of this account's aisles


def test_learned_aisle_beats_table(client, api, mock_api):
    mock_api.get(f"{API}/v2/sync/groceryingredients/").mock(
        return_value=httpx.Response(200, json={"result": [{"uid": "G9", "name": "milk", "aisle_uid": "A_PRODUCE"}]})
    )

    ops.add_grocery_items(client, [{"name": "milk"}])

    assert filed(api)["milk"][1] == "Produce"


def test_filing_report_lists_unfiled_items():
    items = [
        {"uid": "U1", "name": "milk", "aisle": "Dairy", "aisle_uid": "A_DAIRY"},
        {"uid": "U2", "name": "unicorn dust", "aisle": "", "aisle_uid": None},
    ]

    report = ops.filing_report(items)

    assert report["items"] == items
    assert report["unfiled"] == [{"uid": "U2", "name": "unicorn dust"}]
    assert "update_grocery_item" in report["next_step"]


def test_filing_report_all_filed_has_no_next_step():
    report = ops.filing_report([{"uid": "U1", "name": "milk", "aisle": "Dairy", "aisle_uid": "A_DAIRY"}])

    assert report["unfiled"] == []
    assert "next_step" not in report
