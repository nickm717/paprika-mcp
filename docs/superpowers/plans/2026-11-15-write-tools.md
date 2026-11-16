# Paprika MCP Write Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the forked Paprika MCP server with write tools for recipes, groceries and meal plans, plus recipe search, pantry, recipe→grocery and stdio transport.

**Architecture:** `client.py` gains a single gzip-multipart POST helper and thin per-resource write methods. Tool logic lives in plain functions in `paprika_mcp/ops.py` that take a `PaprikaClient` (unit-testable without FastMCP); `server.py` keeps only thin `@mcp.tool()` wrappers. Recipe search reads a JSON cache that refetches only recipes whose `hash` changed.

**Tech Stack:** Python ≥3.10, FastMCP, httpx; tests with pytest + respx.

**Spec:** `docs/superpowers/specs/2026-11-15-write-tools-design.md`

## Global Constraints

- All writes: gzip-compressed JSON, posted as multipart field `data` (`files={"data": ("data", payload)}`).
- Recipes: POST one at a time to `/v2/sync/recipe/{uid}/`; never POST to `/v2/sync/recipes/` (returns 500).
- Groceries: POST a JSON **array** to `/v2/sync/groceries/`. Leave `aisle` as `""`.
- Meals: POST a JSON **array** to `/v2/sync/meals/`; no per-uid endpoint. `date` format `"YYYY-MM-DD 00:00:00"`; `type` 0=Breakfast, 1=Lunch, 2=Dinner, 3=Snack.
- New uids: `str(uuid.uuid4()).upper()`.
- Every update re-fetches the current object and merges only the caller's changed fields onto it.
- Any recipe write sets a new `hash` (`hashlib.sha256(uuid4 bytes).hexdigest()`, 64-char hex), otherwise other devices won't pick up the change.
- Destructive tool docstrings start with `DESTRUCTIVE:` and tell the model to confirm with the user first.
- No photo upload. Don't touch `paprika/` (Go CLI).
- Per `AGENTS.md`: README + `API_REFERENCE.md` updated with tool changes; E2E check run after network/runtime changes.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Updating a uid that doesn't exist (recipe or meal or grocery item) → clear `ValueError("... not found")`, never silently creates a blank object. (Tasks 2, 4, 5)
2. Updating one field leaves every other field exactly as fetched (edits made in the app survive). (Tasks 2, 4, 5)
3. Meal date/type input the model is likely to send: `"2026-11-20"` accepted; `"next tuesday"` → ValueError naming the format; meal type by name, case-insensitive (`"dinner"`, `"Dinner"`), unknown (`"supper"`) → ValueError listing valid names. (Task 5)
4. Grocery tools called without `list_uid` → use the list with `is_default: true`; if none, the first list. (Task 4)
5. Adding recipe ingredients to the grocery list skips blank lines and section headers (lines ending in `:`). (Task 6)

---

## File Structure

- Modify `paprika_mcp/client.py` — `_post_gzip`, `notify`, `upsert_recipe`, `upsert_grocery_items`, `upsert_meals`, `list_pantry_items`.
- Create `paprika_mcp/ops.py` — tool logic (pure functions over a client).
- Create `paprika_mcp/recipe_cache.py` — hash-keyed recipe cache + search.
- Create `paprika_mcp/ingredients.py` — ingredient text → grocery item names.
- Modify `paprika_mcp/server.py` — thin tool wrappers; stdio/http choice in `main`.
- Modify `paprika_mcp/cli.py` — `run --stdio`.
- Modify `pyproject.toml` — `[project.optional-dependencies] dev = ["pytest>=8", "respx>=0.21"]`.
- Create `tests/conftest.py`, `tests/test_client_writes.py`, `tests/test_recipes.py`, `tests/test_recipe_cache.py`, `tests/test_groceries.py`, `tests/test_meals.py`, `tests/test_ingredients.py`.
- Modify `README.md`, `API_REFERENCE.md`.

---

### Task 1: Test harness and gzip write helper

**Files:**
- Modify: `pyproject.toml`, `paprika_mcp/client.py`
- Create: `tests/conftest.py`, `tests/test_client_writes.py`

**Interfaces:**
- Produces:
  - fixture `client` → `PaprikaClient(email="e", password="p", token_cache_path=None)` with `_token = "TOKEN"`.
  - helper `decode_upload(request: httpx.Request) -> Any` in `tests/conftest.py`: parses the multipart body, gunzips field `data`, returns parsed JSON.
  - `PaprikaClient._post_gzip(self, path: str, payload: Any) -> dict`
  - `PaprikaClient.notify(self) -> None` — POST `/v2/sync/notify/`, swallows any error (best-effort).

- [ ] **Step 1:** Add dev extras to `pyproject.toml`; `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`. Expected: installs cleanly.
- [ ] **Step 2: Write failing tests** in `tests/test_client_writes.py`:
  - `test_post_gzip_sends_gzipped_json_in_data_field`: respx route `POST https://www.paprikaapp.com/api/v2/sync/groceries/` → `{"result": true}`; `client._post_gzip("/v2/sync/groceries/", [{"a": 1}])`; assert `decode_upload(route.calls[0].request) == [{"a": 1}]`, `Authorization == "Bearer TOKEN"`, returns `{"result": True}`.
  - `test_notify_ignores_errors`: route notify → 500; `client.notify()` does not raise.
- [ ] **Step 3:** Run `.venv/bin/pytest tests/test_client_writes.py -v`. Expected: FAIL (`_post_gzip` missing).
- [ ] **Step 4:** Implement `_post_gzip` via existing `_request("POST", path, files=...)`; refactor `create_grocery_item` to use it. Implement `notify`.
- [ ] **Step 5:** Run tests. Expected: PASS.
- [ ] **Step 6:** Commit `test: add pytest harness and gzip write helper`.

### Task 2: Recipe create / update / trash

**Files:**
- Modify: `paprika_mcp/client.py`, `paprika_mcp/server.py`
- Create: `paprika_mcp/ops.py`, `tests/test_recipes.py`

**Interfaces:**
- Consumes: `_post_gzip`, `notify`, `get_recipe(uid)`.
- Produces:
  - `PaprikaClient.upsert_recipe(self, recipe: dict) -> dict` — POST to `/v2/sync/recipe/{recipe["uid"]}/`.
  - `ops.new_hash() -> str`
  - `ops.create_recipe(client, name: str, ingredients: str = "", directions: str = "", **fields) -> dict` — fills every field from the API_REFERENCE "Recipe Object Fields" table with its default, `created` = now `"%Y-%m-%d %H:%M:%S"`; returns the posted recipe.
  - `ops.update_recipe(client, uid: str, changes: dict) -> dict` — fetch, raise `ValueError(f"Recipe {uid} not found")` on 404, reject keys not in the field table or in `{"uid","hash","photo_url"}` with ValueError, merge, new hash, post, notify.
  - `ops.trash_recipe(client, uid: str) -> dict` — `update_recipe(client, uid, {"in_trash": True})`.
  - Tools `create_recipe`, `update_recipe`, `trash_recipe` (docstring starts `DESTRUCTIVE:`).

- [ ] **Step 1: Write failing tests** in `tests/test_recipes.py`:
  - `test_create_recipe_posts_full_object`: uploaded object has uppercase-UUID `uid`, `name`, `in_trash is False`, `categories == []`, 64-char `hash`; POST went to `/v2/sync/recipe/{uid}/`.
  - `test_update_recipe_preserves_untouched_fields`: GET returns the sample recipe from API_REFERENCE; `update_recipe(client, uid, {"rating": 4})`; uploaded == original except `rating == 4` and `hash != original hash`.
  - `test_update_recipe_unknown_uid_raises`: GET → 404; `pytest.raises(ValueError, match="not found")`; no POST made.
  - `test_update_recipe_rejects_unknown_field`: `{"colour": "red"}` → ValueError.
  - `test_trash_recipe_sets_in_trash`.
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_recipes.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement client method, ops functions, tool wrappers.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat: recipe create, update and trash tools`.

### Task 3: Recipe cache and search

**Files:**
- Create: `paprika_mcp/recipe_cache.py`, `tests/test_recipe_cache.py`
- Modify: `paprika_mcp/config.py` (add `RECIPE_CACHE_FILE = CONFIG_DIR / "recipe_cache.json"`), `paprika_mcp/server.py`

**Interfaces:**
- Produces:
  - `class RecipeCache(path: Path)` with `sync(self, client) -> list[dict]` and `search(self, client, query: str = "", ingredient: str = "", category: str = "", include_trashed: bool = False, limit: int = 20) -> list[dict]`.
  - Cache file format: `{"<uid>": {"hash": str, "recipe": dict}}`.
  - Tool `search_recipes(query="", ingredient="", category="", limit=20)` returning summaries `{uid, name, categories, rating, total_time}`.

- [ ] **Step 1: Write failing tests:**
  - `test_sync_fetches_only_changed`: cache has uid A (hash h1) and B (h2); list returns A:h1, B:h2x, C:h3; assert GET only for B and C; A, B, C present; uid removed from list is dropped from cache.
  - `test_search_matches_name_case_insensitive`, `test_search_by_ingredient`, `test_search_by_category` (exact category name, case-insensitive).
  - `test_search_excludes_trashed_by_default`.
  - `test_corrupt_cache_file_rebuilds` (file contains `"not json"` → full refetch, no exception).
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_recipe_cache.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. All terms given are ANDed; write the cache file with mode 0600.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat: hash-keyed recipe cache and search_recipes tool`.

### Task 4: Grocery writes

**Files:**
- Modify: `paprika_mcp/client.py`, `paprika_mcp/ops.py`, `paprika_mcp/server.py`
- Create: `tests/test_groceries.py`

**Interfaces:**
- Produces:
  - `PaprikaClient.upsert_grocery_items(self, items: list[dict]) -> dict`
  - `ops.default_list_uid(client) -> str` — `is_default` list, else first; ValueError if no lists.
  - `ops.add_grocery_items(client, items: list[dict], list_uid: str | None = None) -> list[dict]` — each input `{name, quantity?, instruction?, recipe_uid?}`; builds the full object shape from API_REFERENCE (same defaults as existing `create_grocery_item`); one POST.
  - `ops.update_grocery_item(client, uid: str, changes: dict) -> dict`
  - `ops.set_grocery_items_checked(client, uids: list[str], checked: bool) -> list[dict]`
  - `ops.remove_grocery_items(client, uids: list[str]) -> list[dict]` — sets `purchased: True` and `deleted: True`.
  - Tools: `add_grocery_items`, `update_grocery_item`, `check_grocery_items`, `uncheck_grocery_items`, `remove_grocery_items` (`DESTRUCTIVE:`). Keep the existing `add_grocery_item`, delegating to `add_grocery_items`; make its `list_uid` optional too.

- [ ] **Step 1: Write failing tests:**
  - `test_add_items_single_post_array` (3 items → one POST, array of 3, each with uppercase uid, `aisle == ""`, `ingredient == name.lower()`).
  - `test_add_items_defaults_to_default_list` / `test_default_list_falls_back_to_first`.
  - `test_update_item_preserves_other_fields`, `test_update_unknown_item_raises`.
  - `test_check_and_uncheck`.
  - `test_remove_sets_purchased_and_deleted`.
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_groceries.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement; updates fetch via `list_grocery_items()` and find by uid.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat: grocery add, update, check and remove tools`.

### Task 5: Meal plan writes

**Files:**
- Modify: `paprika_mcp/client.py`, `paprika_mcp/ops.py`, `paprika_mcp/server.py`
- Create: `tests/test_meals.py`

**Interfaces:**
- Produces:
  - `PaprikaClient.upsert_meals(self, meals: list[dict]) -> dict`
  - `ops.parse_meal_type(value: str | int) -> int`
  - `ops.parse_date(value: str) -> str` — `"YYYY-MM-DD"` → `"YYYY-MM-DD 00:00:00"`; else ValueError mentioning `YYYY-MM-DD`.
  - `ops.add_meal(client, date: str, meal_type: str | int, name: str | None = None, recipe_uid: str | None = None) -> dict` — needs `name` or `recipe_uid`; if only `recipe_uid`, name taken from `get_recipe`. Object shape per API_REFERENCE create example, `type_uid: ""`, `deleted: False`.
  - `ops.update_meal(client, uid: str, date: str | None = None, meal_type: str | int | None = None, name: str | None = None, recipe_uid: str | None = None) -> dict`
  - `ops.remove_meal(client, uid: str) -> dict` — `deleted: True`.
  - Tools `add_meal`, `update_meal`, `remove_meal` (`DESTRUCTIVE:`).
  - Move `MEAL_TYPES` into `ops.py`; `server.py` imports it.

- [ ] **Step 1: Write failing tests:**
  - `test_parse_meal_type` — `"dinner"`, `"Dinner"`, `2` → 2; `"supper"` → ValueError whose message contains `breakfast, lunch, dinner, snack`.
  - `test_parse_date` — `"2026-11-20"` OK; `"next tuesday"` → ValueError containing `YYYY-MM-DD`.
  - `test_add_meal_with_recipe_uses_recipe_name`.
  - `test_add_meal_requires_name_or_recipe`.
  - `test_update_meal_moves_date_preserving_rest`, `test_update_unknown_meal_raises`.
  - `test_remove_meal_sets_deleted`.
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_meals.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat: meal plan add, update and remove tools`.

### Task 6: Pantry and recipe → grocery list

**Files:**
- Create: `paprika_mcp/ingredients.py`, `tests/test_ingredients.py`
- Modify: `paprika_mcp/client.py`, `paprika_mcp/ops.py`, `paprika_mcp/server.py`

**Interfaces:**
- Consumes: `ops.add_grocery_items`.
- Produces:
  - `PaprikaClient.list_pantry_items(self) -> list` — GET `/v2/sync/pantry/`.
  - `ingredients.ingredient_lines(text: str) -> list[str]` — stripped non-empty lines, excluding lines ending in `:`.
  - `ops.add_recipe_to_grocery_list(client, recipe_uid: str, list_uid: str | None = None) -> list[dict]` — each line becomes an item with `name` = the full line and `recipe_uid` set (Paprika parses quantities itself; don't split them).
  - Tools `list_pantry_items`, `add_recipe_to_grocery_list`.

- [ ] **Step 1: Write failing tests:**
  - `test_ingredient_lines_skips_blank_and_headers`: `"2 cups flour\n\nFor the sauce:\n 1 egg "` → `["2 cups flour", "1 egg"]`.
  - `test_add_recipe_to_grocery_list` (items carry `recipe_uid`, one POST).
  - `test_list_pantry_items` (GET path).
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_ingredients.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat: pantry listing and add recipe to grocery list`.

### Task 7: stdio transport, docs, live E2E

**Files:**
- Modify: `paprika_mcp/server.py`, `paprika_mcp/cli.py`, `README.md`, `API_REFERENCE.md`

**Interfaces:**
- Produces: `server.main(stdio: bool = False)`; `paprika-mcp run --stdio`. In stdio mode nothing may print to stdout except protocol (CLI `_print` must go to stderr or be skipped).

- [ ] **Step 1:** Implement `--stdio` flag → `mcp.run(transport="stdio")`.
- [ ] **Step 2:** Verify: `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' | .venv/bin/paprika-mcp run --stdio` prints one JSON-RPC result line containing `"serverInfo"`.
- [ ] **Step 3:** Run full suite `.venv/bin/pytest -v`. Expected: all PASS.
- [ ] **Step 4:** Update README tool table and Claude Desktop / Claude Code config snippets (`claude mcp add paprika -- <repo>/.venv/bin/paprika-mcp run --stdio`); document new write behaviour (hash refresh, notify, soft deletes) in `API_REFERENCE.md`.
- [ ] **Step 5: Supervised live E2E** (user present; needs `paprika-mcp setup` done by the user). Run the AGENTS.md status check, then via `ops`: create recipe `"ZZ MCP Test Recipe"`, update its rating, add it to tomorrow's dinner, add its ingredients to the default list, then remove the meal, remove the grocery items, trash the recipe. Ask the user to confirm in the Paprika app at each step, specifically whether removed grocery items disappear (if they only show as checked, note that in `API_REFERENCE.md`).
- [ ] **Step 6:** Commit `feat: stdio transport and docs for write tools`.
