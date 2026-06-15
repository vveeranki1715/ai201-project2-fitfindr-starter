# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the local mock listings dataset (`data/listings.json`, 40 items) for secondhand
pieces that match the user's keywords, optional size, and optional price ceiling. Returns the
matches ranked by how well they overlap the user's description.

**Input parameters:**
- `description` (str): Free-text keywords describing the desired item, e.g. `"vintage graphic tee"`.
  Tokenized and matched against each listing's `title`, `description`, `style_tags`, `category`,
  `colors`, and `brand`.
- `size` (str | None): Size string to filter on (e.g. `"M"`). Case-insensitive substring match
  against the listing's `size` field so `"M"` matches `"S/M"`. `None` skips the size filter.
- `max_price` (float | None): Inclusive price ceiling. A listing passes only if
  `listing["price"] <= max_price`. `None` skips the price filter.

**What it returns:**
A `list[dict]` of full listing dicts, highest keyword-overlap score first. Each dict contains:
`id, title, description, category, style_tags (list), size, condition, price (float),
colors (list), brand, platform`. Listings scoring 0 (no keyword overlap) are dropped. Returns an
empty list `[]` when nothing matches — never raises.

**What happens if it fails or returns nothing:**
Returns `[]`. The planning loop detects the empty list, writes a helpful error into
`session["error"]` telling the user what to try differently (loosen size, raise the budget, use
broader keywords), and returns early **without** calling `suggest_outfit`.

---

### Tool 2: suggest_outfit

**What it does:**
Uses the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfits pairing the chosen
thrifted item with pieces the user already owns.

**Input parameters:**
- `new_item` (dict): The selected listing dict (the item being considered).
- `wardrobe` (dict): A wardrobe dict with an `items` key — a list of wardrobe item dicts
  (`name, category, colors, style_tags, notes`). May have an empty `items` list.

**What it returns:**
A non-empty `str` of styling advice. When the wardrobe has items, it names specific owned pieces
to pair with the new item. When the wardrobe is empty, it returns general styling advice (what
kinds of pieces and vibe suit the item) instead of failing.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty it switches to the general-advice prompt rather than crashing.
If the LLM call itself raises, it returns a plain-string fallback styling message so the loop can
still continue. It never returns an empty string or raises.

---

### Tool 3: create_fit_card

**What it does:**
Uses the Groq LLM (higher temperature for variety) to turn the outfit suggestion into a short,
casual, shareable OOTD-style caption for the thrifted find.

**Input parameters:**
- `outfit` (str): The outfit-suggestion string returned by `suggest_outfit()`.
- `new_item` (dict): The selected listing dict — used for the item name, price, and platform.

**What it returns:**
A 2–4 sentence `str` caption that sounds like a real social post, mentions the item name, price,
and platform naturally (once each), and varies between runs (temperature ≈ 0.9).

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only it returns a descriptive error string
(`"Can't make a fit card without an outfit suggestion..."`) instead of raising. If the LLM call
raises, it returns a string fallback caption.

---

### Additional Tools (if any)

None — three required tools only.

---

## Planning Loop

**How does your agent decide which tool to call next?**
The loop is a fixed sequence guarded by conditional early-exits; it is not the same every run
because branches depend on tool output.

1. `_new_session(query, wardrobe)` builds the session dict (single source of truth).
2. **Parse** the query into `description`, `size`, `max_price` with regex/string rules:
   - `max_price` ← number following `under`/`$`/`below`/`<`.
   - `size` ← token after `size`, or a standalone size token (`XS/S/M/L/XL` or a number for shoes).
   - `description` ← the query with the price/size phrases stripped out.
   Stored in `session["parsed"]`.
3. Call `search_listings(description, size, max_price)` → `session["search_results"]`.
   - **Branch A — empty list:** set `session["error"]` to an actionable message and `return session`
     immediately. `suggest_outfit` and `create_fit_card` are never called; `fit_card` stays `None`.
   - **Branch B — non-empty:** `session["selected_item"] = search_results[0]` (top-ranked) and continue.
4. Call `suggest_outfit(selected_item, wardrobe)` → `session["outfit_suggestion"]`.
5. Call `create_fit_card(outfit_suggestion, selected_item)` → `session["fit_card"]`.
6. `return session`. Done when `fit_card` is set (success) or `error` is set (early exit).

---

## State Management

**How does information from one tool get passed to the next?**
A single `session` dict created by `_new_session()` is threaded through the whole run and returned
at the end. Each step reads its inputs from earlier session fields and writes its output back:
`parsed` → feeds `search_listings`; `search_results[0]` → `selected_item` → input to
`suggest_outfit`; `outfit_suggestion` → input to `create_fit_card` → `fit_card`. No globals, no
re-prompting the user mid-run, no hardcoded values between steps. `error` is the early-exit flag;
callers check `session["error"]` first, and on success it is `None`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]`: "No listings matched 'X'. Try loosening the size filter, raising your max price, or using broader keywords (e.g. 'tee' instead of 'vintage band tee')." Returns early; never calls the next tools. |
| suggest_outfit | Wardrobe is empty | Detects empty `items`; sends a general-styling-advice prompt instead, returning useful generic advice rather than naming owned pieces. Never raises. |
| create_fit_card | Outfit input is missing or incomplete | Guards empty/whitespace `outfit`; returns a descriptive error string ("Can't make a fit card without an outfit suggestion — try a different search.") instead of raising. |

---

## Architecture

```
User query + wardrobe choice
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  Planning Loop  (run_agent in agent.py)                      │
│                                                             │
│  parse query ──► session["parsed"] = {description,size,max} │
│        │                                                    │
│        ▼                                                    │
│  search_listings(description, size, max_price)              │
│        │ results == []                                      │
│        ├──► session["error"] = "No listings found..." ──► return session  (fit_card = None)
│        │                                                    │
│        │ results == [item, ...]                             │
│        ▼                                                    │
│  session["selected_item"] = results[0]                      │
│        │                                                    │
│        ▼                                                    │
│  suggest_outfit(selected_item, wardrobe)                    │
│        │   (empty wardrobe ► general advice branch)         │
│        ▼                                                    │
│  session["outfit_suggestion"] = "..."                       │
│        │                                                    │
│        ▼                                                    │
│  create_fit_card(outfit_suggestion, selected_item)          │
│        │   (empty outfit ► error-string branch)             │
│        ▼                                                    │
│  session["fit_card"] = "..."                                │
│        │                                                    │
│        ▼                                                    │
│  return session  ◄──────────────── error path returns here │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
  app.py handle_query maps session → 3 Gradio panels
        (listing text | outfit idea | fit card)

State: the single `session` dict is read/written at every step and is the
only thing passed between tools — see State Management above.
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**
I'll use **Claude (Claude Code)**, one tool at a time.
- `search_listings`: give Claude the Tool 1 block (inputs, return value, failure mode) and tell it
  to use `load_listings()` from `utils/data_loader.py` rather than re-reading the file. Verify
  before trusting: (a) it filters by all three params, (b) size match is case-insensitive substring,
  (c) it scores by keyword overlap and drops score-0 items, (d) empty input → `[]`. Test with the
  three pytest cases (results / empty / price filter).
- `suggest_outfit`: give Claude the Tool 2 block; require an empty-wardrobe branch and a
  try/except fallback. Verify it never returns `""` by calling it with both example and empty
  wardrobes.
- `create_fit_card`: give Claude the Tool 3 block; require the empty-outfit guard and
  `temperature≈0.9`. Verify variety by running it 3× on the same input and confirming outputs differ.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the **Architecture diagram** plus the **Planning Loop** and **State Management**
sections and ask it to implement `run_agent()`. Before trusting it I'll confirm: (a) it branches on
the `search_listings` result and returns early on `[]`, (b) it does NOT call all three tools
unconditionally, (c) every value is read from / written to the `session` dict (no globals, no
re-prompting). I'll verify by running `python agent.py` (happy path + no-results path) and printing
`session["selected_item"]` / `session["outfit_suggestion"]` to confirm state flows unchanged.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse + Search:**
The loop parses the query → `description="vintage graphic tee"`, `size=None`, `max_price=30.0`,
then calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. It returns the
matching tee listings ranked by keyword overlap; the loop stores them in `session["search_results"]`
and sets `session["selected_item"]` to the top one (e.g. *"Faded Band Tee — $22, Depop, good condition"*).
Because the list is non-empty, it does **not** error out.

**Step 2 — Suggest outfit:**
The loop calls `suggest_outfit(selected_item, wardrobe)` with the example wardrobe (baggy jeans,
chunky sneakers, etc.). The LLM returns something like *"Pair the faded band tee with your baggy
straight-leg jeans and chunky sneakers for a 90s grunge look — half-tuck the front for shape."*
Stored in `session["outfit_suggestion"]`.

**Step 3 — Fit card:**
The loop calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM returns a caption like
*"thrifted this faded band tee off depop for $22 and it was made for my baggy jeans 🖤 full look in
my stories"*. Stored in `session["fit_card"]`. The loop returns the session.

**Final output to user:**
Three panels: (1) the top listing (title, price, platform, condition), (2) the outfit idea,
(3) the shareable fit card. If Step 1 had returned no matches, the user would instead see only the
error message ("No listings matched… try loosening size / raising price / broader keywords") and the
other two panels would be empty.
