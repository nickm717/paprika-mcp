# Grocery aisle filing: short design

**Why:** in the live test on 2026-11-16, every grocery item added through the
MCP landed in Miscellaneous. The Paprika server never assigns aisles. The apps
do it on the device: they parse the ingredient out of the line, look it up in
the account's learned map (`GET /v2/sync/groceryingredients/`, which returns
`{uid, name, aisle_uid}`), and send `ingredient`, `aisle` and `aisle_uid` with
the item.

**Goal:** items added through the MCP land in the same aisle the app would put
them in. Ingredients the account doesn't know stay in Miscellaneous, unless
Claude names an aisle.

**Non-goals:**
- Writing to `groceryingredients`, i.e. teaching Paprika new mappings.
- Guessing aisles for ingredients the account has never filed.

**Approaches:**
1. *Mirror the app (chosen).* Parse the ingredient name, look it up in the
   account's own map, and set `aisle_uid` and `aisle`. Uses the account's data,
   so it matches the user's own filing.
2. Let Claude choose an aisle for every item. This adds more model work and
   ignores mappings the user has already taught the app.
3. Hard-code a generic ingredient→aisle table. It would disagree with the
   user's own filing, and the account's aisle names differ anyway.

Approach 1 is the default. Approach 2 is kept as an optional override, via an
explicit `aisle` name.

**Design:**
- `ingredients.ingredient_name(line) -> str`:
  - Lowercases the line.
  - Drops a leading quantity: digits, fractions, unicode fractions, ranges.
  - Drops a leading unit: cup, tbsp, tsp, oz, lb, g, ml, can, clove, pinch and
    similar, singular or plural, with an optional period.
  - Drops parentheticals and anything after the first comma.
  - Examples: "1 1/2 cups Arborio risotto rice ((Note 1))" → "arborio risotto
    rice"; "2 tbsp chives (, finely chopped)" → "chives"; "butter" → "butter".
- Aisle lookup, once per call:
  - Fetch `groceryaisles` and `groceryingredients`.
  - Match the parsed name exactly. If that fails, try singular and plural
    variants: drop a trailing "s" or "es", or add "s".
  - On a hit, set `aisle_uid` and the aisle's `name`. On a miss, leave both
    empty, so the item goes to Miscellaneous.
- Explicit `aisle`:
  - Items in `add_grocery_items`, `add_grocery_item`, and `update_grocery_item`
    changes accept an aisle name.
  - The name is matched case-insensitively against `groceryaisles`. An unknown
    name raises `ValueError` listing the aisles.
  - An explicit aisle beats the lookup.
- New items store the parsed name in `ingredient`. They used to store
  `name.lower()`.
- New read tool `list_grocery_aisles`, so Claude can name an aisle.

**Left to the builder:** the exact unit list, and the regex details.
