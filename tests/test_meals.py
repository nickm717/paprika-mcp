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
    "type_uid": "TYPEUID",
    "scale": None,
    "is_ingredient": False,
}


@pytest.fixture
def api(mock_api):
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
    assert meal["type_uid"] == ""
    assert meal["deleted"] is False


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
