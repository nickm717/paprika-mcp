import pytest

from paprika_mcp.ingredients import ingredient_name


@pytest.mark.parametrize("line, expected", [
    ("1 1/2 cups Arborio risotto rice ((Note 1))", "arborio risotto rice"),
    ("2 tbsp chives (, finely chopped)", "chives"),
    ("butter", "butter"),
    ("2 cups flour", "flour"),
    ("1 egg", "egg"),
    ("½ tsp. salt", "salt"),
    ("2-3 cloves garlic, minced", "garlic"),
    ("1 (14 oz) can chickpeas, drained", "chickpeas"),
    ("400g spaghetti", "spaghetti"),
    ("  Cheddar Cheese  ", "cheddar cheese"),
    ("1 large onion", "onion"),
])
def test_ingredient_name(line, expected):
    assert ingredient_name(line) == expected


def test_ingredient_name_never_empty_for_text():
    assert ingredient_name("2 cups") == "2 cups"
