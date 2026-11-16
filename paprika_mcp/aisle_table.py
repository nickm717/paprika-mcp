"""Fallback aisles for common foods the account hasn't learned.

Paprika's apps ship a built-in food list that the sync API doesn't expose, so
the account's learned map (groceryingredients) only holds what the user filed
by hand. This table covers everyday ingredients. Aisle names are Paprika's
default aisles; a name the account doesn't have is simply not used.
"""

from __future__ import annotations

_TABLE: dict[str, str] = {}


def _add(aisle: str, words: str) -> None:
    for w in words.split(","):
        w = w.strip()
        if w:
            _TABLE[w] = aisle


_add("Produce", """
    apple, banana, orange, lemon, lime, grapefruit, grape, strawberry, blueberry, raspberry,
    blackberry, berry, cherry, peach, pear, plum, mango, pineapple, kiwi, melon, watermelon,
    cantaloupe, avocado, tomato, cherry tomato, potato, sweet potato, onion, red onion,
    yellow onion, shallot, scallion, green onion, spring onion, garlic, ginger, carrot, celery,
    cucumber, zucchini, squash, butternut squash, pumpkin, eggplant, bell pepper, pepper,
    jalapeno, chili, broccoli, cauliflower, cabbage, brussels sprout, kale, spinach,
    baby spinach, lettuce, romaine, arugula, salad, mixed greens, asparagus, green bean,
    pea, snap pea, corn, mushroom, beet, radish, turnip, parsnip, leek, fennel, okra,
    herb, basil, cilantro, parsley, dill, mint, rosemary, thyme, sage, chive
""")
_add("Dairy", """
    milk, whole milk, skim milk, buttermilk, cream, heavy cream, whipping cream, half and half,
    sour cream, butter, unsalted butter, egg, cheese, parmesan, mozzarella, feta, ricotta,
    cottage cheese, cream cheese, goat cheese, yogurt, greek yogurt, oat milk, almond milk
""")
_add("Meat", """
    chicken, chicken breast, chicken thigh, ground beef, beef, steak, pork, pork chop,
    pork loin, bacon, sausage, ground turkey, turkey, lamb, ham, ground pork, veal, chorizo
""")
_add("Seafood", "salmon, tuna steak, shrimp, prawn, cod, tilapia, halibut, scallop, crab, lobster, fish, mussel, clam")
_add("Deli", "salami, prosciutto, pepperoni, sliced turkey, hummus")
_add("Bakery", "baguette, croissant, bagel, bun, roll, pita, naan, tortilla, sourdough")
_add("Breads and Cereals", "bread, cereal, oats, rolled oats, oatmeal, granola, breadcrumbs, panko, crackers")
_add("Baking Goods", """
    flour, all-purpose flour, bread flour, sugar, brown sugar, powdered sugar, baking soda,
    baking powder, yeast, cornstarch, vanilla, vanilla extract, chocolate chips, cocoa powder,
    honey, maple syrup, molasses
""")
_add("Pasta, Rice and Beans", """
    pasta, spaghetti, penne, linguine, fettuccine, macaroni, lasagna, noodle, egg noodle,
    rice, brown rice, basmati rice, jasmine rice, arborio rice, quinoa, couscous, lentil,
    chickpea, black bean, kidney bean, pinto bean, bean
""")
_add("Canned and Jar Goods", """
    coconut milk, broth, stock, chicken broth, chicken stock, vegetable broth, beef broth,
    canned tomatoes, diced tomatoes, crushed tomatoes, tomato paste, tomato sauce, tuna,
    olives, pickles, jam
""")
_add("Sauces and Condiments", """
    peanut butter, ketchup, mustard, dijon mustard, mayonnaise, mayo, soy sauce, hot sauce,
    sriracha, salsa, bbq sauce, worcestershire sauce, fish sauce, pesto, marinara, tahini,
    vinegar, balsamic vinegar
""")
_add("Oils and Dressings", "oil, olive oil, vegetable oil, canola oil, sesame oil, coconut oil, cooking spray, dressing")
_add("Spices and Seasonings", """
    salt, kosher salt, sea salt, black pepper, peppercorn, cumin, paprika, smoked paprika,
    chili powder, cinnamon, nutmeg, oregano, dried oregano, bay leaf, turmeric, curry powder,
    garlic powder, onion powder, red pepper flakes, cayenne, coriander, garam masala, spice
""")
_add("Frozen Foods", "ice cream, frozen pizza, frozen vegetables, frozen fruit")
_add("Snacks", "chips, tortilla chips, popcorn, pretzels, nuts, almonds, cashews, walnuts, peanuts, cookies")
_add("Beverages", "coffee, tea, juice, orange juice, soda, sparkling water, water")
_add("Beer, Wine and Spirits", "beer, wine, red wine, white wine, vodka, rum, whiskey, gin, tequila")


def _forms(word: str) -> list[str]:
    forms = [word]
    if word.endswith("ies"):
        forms.append(word[:-3] + "y")
    if word.endswith("es"):
        forms.append(word[:-2])
    if word.endswith("s"):
        forms.append(word[:-1])
    return forms


def table_aisle(ingredient: str) -> str | None:
    """Default aisle name for a common ingredient, or None.

    Tries the whole name, then shorter endings ("red bell pepper" -> "bell pepper"),
    then shorter beginnings ("chicken thighs" -> "chicken"), each singular or plural.
    """
    words = (ingredient or "").strip().lower().split()
    if not words:
        return None
    if words[0] == "frozen":
        return "Frozen Foods"
    n = len(words)
    candidates = [" ".join(words)]
    candidates += [" ".join(words[i:]) for i in range(1, n)]
    candidates += [" ".join(words[:i]) for i in range(n - 1, 0, -1)]
    for cand in candidates:
        last = cand.split()
        for form in _forms(last[-1]):
            key = " ".join(last[:-1] + [form])
            if key in _TABLE:
                return _TABLE[key]
    return None
