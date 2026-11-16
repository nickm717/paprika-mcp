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
    # real lines from the account's recipes
    ("1 ½ cups/185 grams grated zucchini", "zucchini"),
    ("⅓ cup/80 milliliters plain Greek yogurt", "greek yogurt"),
    ("⅔ cup/140 grams light brown sugar", "brown sugar"),
    ("1 teaspoon/2 grams finely grated lemon zest", "lemon zest"),
    ("1 ounce/30 g shelled walnuts", "walnuts"),
    ("A good pinch of chile powder or chopped dried chile", "chile powder"),
    ("1 tablespoon coconut oil or olive oil", "coconut oil"),
    ("Sea salt and freshly ground pepper", "sea salt"),
    ("A large bunch of cilantro", "cilantro"),
    ("Juice of 1/2 a lemon", "lemon"),
    ("1 tablespoon good olive oil", "olive oil"),
    ("Rice or flatbreads, to serve (optional)", "rice"),
    ("1 lb ground beef", "ground beef"),
    ("1 (14-ounce/400-g) can black-eyed peas", "black-eyed peas"),
    ("3 to 4 pounds boneless, skinless pork shoulder, cut into chunks", "pork shoulder"),
    ("2 tablespoons toasted sesame seeds", "sesame seeds"),
    ("coarsely chopped fresh cilantro/mint", "cilantro"),
    ("5 cups homemade or store-bought low-sodium vegetable broth", "vegetable broth"),
    ("1 17.6-oz. package shelf-stable or refrigerated gnocchi", "gnocchi"),
    ("1 (2 1/2 to 3-pound) cooked, halved spaghetti squash", "spaghetti squash"),
])
def test_ingredient_name(line, expected):
    assert ingredient_name(line) == expected


def test_ingredient_name_never_empty_for_text():
    assert ingredient_name("2 cups") == "2 cups"
