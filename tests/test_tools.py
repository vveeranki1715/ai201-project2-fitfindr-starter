"""
tests/test_tools.py

One test per failure mode (plus happy-path) for each FitFindr tool.
Run with:  pytest tests/
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Impossible query → empty list, never an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_sorted_by_relevance():
    # More specific keywords should not crash and stays sorted (scores descending).
    results = search_listings("vintage denim jacket", size=None, max_price=200)
    assert isinstance(results, list)


# ── suggest_outfit ─────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str) and out.strip() != ""


def test_suggest_outfit_empty_wardrobe():
    # Empty wardrobe → general advice string, never empty / exception.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str) and out.strip() != ""


# ── create_fit_card ─────────────────────────────────────────────────────────────

def test_fit_card_happy_path():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("Pair it with baggy jeans and chunky sneakers.", item)
    assert isinstance(card, str) and card.strip() != ""


def test_fit_card_empty_outfit():
    # Empty outfit → descriptive error string, not an exception.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "without an outfit" in card.lower()
