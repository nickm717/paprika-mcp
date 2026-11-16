# Paprika MCP — write tools (design)

Status: approved 2026-11-15

## Intent

A personal MCP server that lets Claude both read and change Paprika data
(recipes, grocery lists, meal plans, pantry) through Paprika's unofficial
cloud sync API. Used by one person, locally, from Claude Desktop and Claude
Code on a Mac.

## Approaches considered

1. **Fork `aarons22/paprika-tools` and extend it** — chosen. Auth, token
   caching, 401 refresh, read tools and detailed API notes
   (`API_REFERENCE.md`, `openapi.yaml`) already exist; the server is ~700
   lines of Python. Trade-off: inherit its structure; upstream looks
   unmaintained so the fork is ours to own.
2. Build from scratch in TypeScript — full control, but redoes solved
   API reverse-engineering.
3. Hosted remote server — phone/claude.ai access, but needs hosting, auth,
   and storing the Paprika password server-side. Not worth it for one user.

`briantkatch/paprika-mcp` was rejected: recipes only, no create.

License note: upstream has no LICENSE file (pyproject says MIT). Fine for a
personal fork; ask upstream to add one before publishing anything derived.

## Goals

Keep everything upstream has. Add:

- **Recipes:** search (name / ingredient / category), create, update, trash.
  Search uses a local cache keyed by `{uid, hash}`, refetching only changed
  recipes (the API only serves full recipes one at a time).
- **Groceries:** add multiple items, update an item, check / uncheck,
  remove (soft delete — Paprika has no true delete for groceries).
- **Meal plan:** add a meal on a date, update/move it, remove
  (`deleted: true`).
- **Pantry:** list items.
- **Convenience:** add a recipe's ingredients to a grocery list.
- **stdio transport** so Claude Desktop / Claude Code can launch the server
  directly, alongside upstream's HTTP + LaunchAgent mode.

## Safety

- Every update re-fetches the current object and merges changes onto it, so
  edits made in the Paprika app aren't clobbered.
- Destructive tools (trash/remove) say so plainly in their descriptions so
  Claude confirms with the user first.

## Non-goals

- Photo uploads (known broken endpoint).
- Hosted/remote deployment.
- The Go CLI in `paprika/` — left as-is.

## Constraints (from API_REFERENCE.md)

- Writes are gzip-compressed JSON posted as multipart field `data`.
- Recipes: POST to `/v2/sync/recipe/{uid}/` individually; the bulk
  `/v2/sync/recipes/` POST returns 500.
- Meals: no per-uid endpoint; POST the array to `/v2/sync/meals/`.
- Rate limits unknown; avoid hammering (cache, no polling).
- Follow `AGENTS.md`: update README and `API_REFERENCE.md` with tool
  changes; run the E2E check after auth/network/runtime changes.

## Testing

- Unit tests with mocked HTTP verifying payload shape (gzip, fields, uids).
- One supervised live run against the real account using a throwaway test
  recipe, grocery item and meal, cleaned up afterwards.

## Left to the builder

Tool naming and parameter shapes, cache location/format, how ingredient
text is split into grocery items, test framework choice (pytest + respx
suggested).
