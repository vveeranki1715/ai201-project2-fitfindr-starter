# FitFindr 🛍️

FitFindr is an agent that finds secondhand clothing and styles it for you. You describe what
you want ("vintage graphic tee under $30"), and the agent searches a mock marketplace, picks the
best match, suggests an outfit using your existing wardrobe, and writes a shareable OOTD-style
caption — stopping early with a helpful message if nothing matches.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

Create a `.env` file in the repo root (it's gitignored — never commit it). Get a free key at
[console.groq.com](https://console.groq.com):

```
GROQ_API_KEY=your_key_here
```

## Running

```bash
python app.py            # launches the Gradio UI (URL printed in terminal, usually :7860)
python agent.py          # runs the happy-path + no-results paths in the terminal
pytest tests/            # runs the tool test suite
```

## Architecture

```
User query + wardrobe choice
        │
        ▼
  run_agent()  (agent.py planning loop)
   parse query → search_listings ──(empty)──► session["error"], return early
        │                                       (suggest_outfit / create_fit_card never run)
        │ (matches)
        ▼
   selected_item = results[0]
        │
        ▼
   suggest_outfit ──► outfit_suggestion
        │
        ▼
   create_fit_card ──► fit_card
        │
        ▼
   session  ──►  app.py maps to 3 panels
```

The single `session` dict is the source of truth, threaded through every step. See
[planning.md](planning.md) for the full spec and a larger diagram.

## Tool Inventory

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| `search_listings` | `description: str`, `size: str \| None`, `max_price: float \| None` | `list[dict]` of listing dicts (`id, title, description, category, style_tags, size, condition, price, colors, brand, platform`), ranked by keyword overlap; `[]` if no match | Filter the 40-item mock dataset by price + size, score by keyword overlap, drop score-0 results |
| `suggest_outfit` | `new_item: dict`, `wardrobe: dict` | `str` — 2–4 sentence styling advice | Use Groq `llama-3.3-70b-versatile` to pair the item with owned pieces (or give general advice if the wardrobe is empty) |
| `create_fit_card` | `outfit: str`, `new_item: dict` | `str` — short shareable caption | Use Groq (temp 0.9) to write a casual OOTD caption mentioning item name, price, platform |

## Planning Loop

`run_agent(query, wardrobe)` is a fixed sequence with a real decision point, so behavior differs by
input rather than blindly calling all three tools:

1. Build a fresh `session` dict.
2. `_parse_query()` extracts `description`, `size`, `max_price` from the text via regex (no LLM —
   deterministic and fast).
3. Call `search_listings`. **This is the branch:** if it returns `[]`, write an actionable message
   to `session["error"]` and **return immediately** — the LLM tools are never called. Otherwise set
   `selected_item = results[0]` and continue.
4. `suggest_outfit(selected_item, wardrobe)` → `session["outfit_suggestion"]`.
5. `create_fit_card(outfit_suggestion, selected_item)` → `session["fit_card"]`.
6. Return `session`.

## State Management

A single `session` dict (created by `_new_session`) holds `query, parsed, search_results,
selected_item, wardrobe, outfit_suggestion, fit_card, error`. Each step reads its inputs from
earlier fields and writes its result back; the same `selected_item` dict that comes out of search
is the exact object passed into `suggest_outfit`, and that suggestion string is exactly what's
passed into `create_fit_card`. No globals, no re-prompting mid-run, no hardcoded values between
steps. Callers check `session["error"]` first; it's `None` on success.

## Error Handling (per tool, with examples from testing)

- **`search_listings` — no matches:** returns `[]` (never raises). The loop sets
  `session["error"]` and stops.
  Tested: `search_listings('designer ballgown', size='XXS', max_price=5)` → `[]`, and the full
  agent returns:
  *"No listings matched "designer ballgown". Try loosening the size filter (XXS), or raising your
  max price ($5), or using broader keywords…"* — `fit_card` stays `None`.
- **`suggest_outfit` — empty wardrobe:** switches to a general-advice prompt.
  Tested with `get_empty_wardrobe()` → returned a useful paragraph of generic styling advice (no
  invented owned items, no exception).
- **`create_fit_card` — empty outfit:** guards before the LLM call.
  Tested: `create_fit_card('', item)` → *"Can't make a fit card without an outfit suggestion — try
  a different search…"* (a string, not an exception).

Both LLM tools also wrap the Groq call in `try/except` and return a string fallback if the API
fails, so the loop never crashes.

## AI Usage

1. **`search_listings` implementation.** I gave Claude the Tool 1 block from `planning.md` (inputs,
   ranked-list return value, empty-list failure mode) and asked it to implement the function using
   `load_listings()`. I verified it filtered by all three parameters, used case-insensitive
   substring matching for size (so `"M"` matches `"S/M"`), scored by keyword overlap, and dropped
   score-0 listings. I kept the design but confirmed the empty-keywords edge case (keep all
   filtered items rather than dropping everything) myself via the test suite.
2. **The planning loop (`run_agent`).** I gave Claude the Architecture diagram plus the Planning
   Loop and State Management sections and asked it to wire the tools together. I specifically
   checked — and required — that it branches on the empty `search_listings` result and returns
   early instead of calling all three tools unconditionally, and that every value flows through the
   `session` dict. I verified by running `python agent.py` and confirming the no-results path leaves
   `fit_card` as `None`.

## Spec Reflection

Writing `planning.md` first made the branch logic obvious before any code existed — the early-exit
on empty search results and the empty-wardrobe / empty-outfit guards were all designed in the spec,
so implementation was mostly translation. The biggest adjustment from spec to code was query
parsing: the spec said "regex/string rules," and in practice I had to strip filler words from the
description so keyword scoring stayed accurate.

## Project Files

- `planning.md` — full spec, diagram, AI plan, interaction walkthrough
- `tools.py` — the three tools
- `agent.py` — query parsing + planning loop + state
- `app.py` — Gradio UI (`handle_query` maps session → panels)
- `tests/test_tools.py` — pytest suite (happy path + each failure mode)
- `data/`, `utils/` — provided dataset and loaders
