import pytest

from paprika_mcp.aisle_table import table_aisle


@pytest.mark.parametrize("ingredient, aisle", [
    ("bananas", "Produce"),
    ("banana", "Produce"),
    ("eggs", "Dairy"),
    ("egg", "Dairy"),
    ("flour", "Baking Goods"),
    ("milk", "Dairy"),
    ("cheddar cheese", "Dairy"),          # falls back to "cheese"
    ("red bell pepper", "Produce"),       # falls back to "bell pepper"
    ("coconut milk", "Canned and Jar Goods"),  # full name beats "milk"
    ("peanut butter", "Sauces and Condiments"),
    ("chicken thighs", "Meat"),
    ("salmon", "Seafood"),
    ("spaghetti", "Pasta, Rice and Beans"),
    ("olive oil", "Oils and Dressings"),
    ("salt", "Spices and Seasonings"),
    ("frozen peas", "Frozen Foods"),
])
def test_table_aisle(ingredient, aisle):
    assert table_aisle(ingredient) == aisle


def test_unknown_ingredient_has_no_aisle():
    assert table_aisle("unicorn dust") is None
    assert table_aisle("") is None
