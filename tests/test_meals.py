import httpx
import pytest

from paprika_mcp import ops
from tests.conftest import API, decode_upload

MEAL = {
    "uid": "M1",
    "recipe_uid": "R1",
    "date": "2026-11-20 00:00:00",
    "type": 2,
    "name": "Salmon",
    "order_flag": 1,
    "type_uid": "U_DINNER",
    "scale": None,
    "is_ingredient": False,
}


MEAL_TYPES = [
    {"uid": "U_DINNER", "name": "Dinner", "order_flag": 2, "original_type": 2},
    {"uid": "U_LUNCH", "name": "Lunch", "order_flag": 1, "original_type": 1},
    {"uid": "U_BREAKFAST", "name": "Breakfast", "order_flag": 0, "original_type": 0},
    {"uid": "U_SNACKS", "name": "Snacks", "order_flag": 3, "original_type": 3},
]


@pytest.fixture
def api(mock_api):
    mock_api.get(f"{API}/v2/sync/mealtypes/").mock(return_value=httpx.Response(200, json={"result": MEAL_TYPES}))
    mock_api.get(f"{API}/v2/sync/meals/").mock(return_value=httpx.Response(200, json={"result": [dict(MEAL)]}))
    mock_api.get(f"{API}/v2/sync/recipe/R9/").mock(
        return_value=httpx.Response(200, json={"result": {"uid": "R9", "name": "Chili"}})
    )
    mock_api.post(f"{API}/v2/sync/notify/").mock(return_value=httpx.Response(200, json={}))
    return mock_api.post(f"{API}/v2/sync/meals/").mock(return_value=httpx.Response(200, json={"result": True}))


def test_parse_meal_type():
    assert ops.parse_meal_type("dinner") == 2
    assert ops.parse_meal_type("Dinner") == 2
    assert ops.parse_meal_type(2) == 2
    with pytest.raises(ValueError, match="breakfast, lunch, dinner, snack"):
        ops.parse_meal_type("supper")


def test_parse_date():
    assert ops.parse_date("2026-11-20") == "2026-11-20 00:00:00"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        ops.parse_date("next tuesday")


def test_add_meal_with_recipe_uses_recipe_name(client, api):
    ops.add_meal(client, "2026-11-21", "dinner", recipe_uid="R9")

    (meal,) = decode_upload(api.calls[0].request)
    assert meal["name"] == "Chili"
    assert meal["recipe_uid"] == "R9"
    assert meal["date"] == "2026-11-21 00:00:00"
    assert meal["type"] == 2
    assert meal["type_uid"] == "U_DINNER"
    assert meal["deleted"] is False


@pytest.mark.parametrize("given, num, uid", [
    ("breakfast", 0, "U_BREAKFAST"), ("Lunch", 1, "U_LUNCH"), ("snack", 3, "U_SNACKS"), ("snacks", 3, "U_SNACKS"),
])
def test_add_meal_sets_the_accounts_meal_type_uid(client, api, given, num, uid):
    ops.add_meal(client, "2026-11-21", given, name="Toast")

    (meal,) = decode_upload(api.calls[0].request)
    assert (meal["type"], meal["type_uid"]) == (num, uid)


def test_add_meal_unknown_type_lists_the_accounts_types(client, api):
    with pytest.raises(ValueError, match="Breakfast, Lunch, Dinner, Snacks"):
        ops.add_meal(client, "2026-11-21", "supper", name="Toast")

    assert not api.called


def test_update_meal_type_changes_type_uid_too(client, api):
    ops.update_meal(client, "M1", meal_type="lunch")

    (meal,) = decode_upload(api.calls[0].request)
    assert (meal["type"], meal["type_uid"]) == (1, "U_LUNCH")


def test_update_meal_repairs_missing_type_uid(client, mock_api, api):
    broken = {**MEAL, "type_uid": ""}
    mock_api.get(f"{API}/v2/sync/meals/").mock(return_value=httpx.Response(200, json={"result": [broken]}))

    ops.update_meal(client, "M1", name="Salmon bowl")

    (meal,) = decode_upload(api.calls[0].request)
    assert meal["type_uid"] == "U_DINNER"


def test_add_meal_requires_name_or_recipe(client, api):
    with pytest.raises(ValueError, match="name or recipe_uid"):
        ops.add_meal(client, "2026-11-21", "lunch")

    assert not api.called


def test_update_meal_moves_date_preserving_rest(client, api):
    ops.update_meal(client, "M1", date="2026-11-22")

    (meal,) = decode_upload(api.calls[0].request)
    assert meal == {**MEAL, "date": "2026-11-22 00:00:00"}


def test_update_unknown_meal_raises(client, api):
    with pytest.raises(ValueError, match="not found"):
        ops.update_meal(client, "NOPE", name="x")

    assert not api.called


def test_remove_meal_sets_deleted(client, api):
    ops.remove_meal(client, "M1")

    (meal,) = decode_upload(api.calls[0].request)
    assert meal["deleted"] is True
    assert meal["name"] == "Salmon"


def test_list_meals_hides_deleted_and_filters_dates(client, mock_api):
    meals = [
        {**MEAL, "uid": "A", "date": "2026-11-19 00:00:00"},
        {**MEAL, "uid": "B", "date": "2026-11-20 00:00:00"},
        {**MEAL, "uid": "C", "date": "2026-11-20 00:00:00", "deleted": True},
        {**MEAL, "uid": "D", "date": "2026-11-23 00:00:00"},
    ]
    mock_api.get(f"{API}/v2/sync/meals/").mock(return_value=httpx.Response(200, json={"result": meals}))

    result = ops.list_meals(client, "2026-11-20", "2026-11-22")

    assert [m["uid"] for m in result] == ["B"]
    assert result[0]["meal_type_name"] == "Dinner"
    assert [m["uid"] for m in ops.list_meals(client)] == ["A", "B", "D"]
