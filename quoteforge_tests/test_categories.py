from quoteforge.quotes.categories import CATEGORIES, get_mood, get_unsplash_keyword

def test_categories_not_empty():
    assert len(CATEGORIES) >= 9

def test_each_category_has_subcategories():
    for cat, data in CATEGORIES.items():
        assert "subcategories" in data, f"{cat} missing subcategories"
        assert len(data["subcategories"]) >= 2

def test_get_mood_returns_string():
    mood = get_mood("Faith & Spiritual", "Christian encouragement")
    assert isinstance(mood, str)
    assert len(mood) > 0

def test_get_unsplash_keyword_returns_string():
    keyword = get_unsplash_keyword("peace")
    assert isinstance(keyword, str)
