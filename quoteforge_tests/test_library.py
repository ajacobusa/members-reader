from quoteforge.quotes.library import get_quotes, QUOTE_LIBRARY

def test_library_has_all_categories():
    from quoteforge.quotes.categories import CATEGORIES
    for cat in CATEGORIES:
        assert cat in QUOTE_LIBRARY, f"Missing category: {cat}"

def test_each_category_has_quotes():
    for cat, quotes in QUOTE_LIBRARY.items():
        assert len(quotes) >= 5, f"{cat} has fewer than 5 quotes"

def test_get_quotes_returns_list():
    result = get_quotes("Nature & Scenic", count=3)
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(q, str) for q in result)

def test_new_categories_have_quotes():
    for cat in ["Life Events", "Professional Niches", "Fitness & Sports",
                "Seasonal Collections", "Room Decor"]:
        result = get_quotes(cat, count=3)
        assert len(result) >= 3, f"{cat} returned fewer than 3 quotes"

def test_get_quotes_no_duplicates():
    result = get_quotes("Motivation & Mindset", count=5)
    assert len(result) == len(set(result))
