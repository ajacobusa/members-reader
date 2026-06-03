from unittest.mock import patch, MagicMock
from quoteforge.quotes.generator import (
    generate_quotes,
    generate_life_chapter,
    generate_family_legacy,
    generate_letter_to_future_self,
)


def _mock_claude(text: str):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    return mock_client


def test_generate_quotes_returns_list():
    raw = "Rise above the storm.\nYour strength is greater than your fear.\nEvery day is a fresh start."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_quotes("Motivation & Mindset", "Growth mindset", count=3)
    assert isinstance(result, list)
    assert len(result) == 3


def test_generate_quotes_strips_numbering():
    raw = "1. Rise above.\n2. Keep going.\n3. Never quit."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_quotes("Motivation & Mindset", "Resilience", count=3)
    assert not any(q[0].isdigit() for q in result)


def test_generate_quotes_filters_empty_lines():
    raw = "Rise above.\n\nKeep going.\n\n"
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_quotes("Motivation & Mindset", "Resilience", count=2)
    assert all(len(q) > 0 for q in result)


def test_generate_life_chapter_returns_variations():
    raw = "Chapter 23: Becoming the Dentist\nEvery hour of study is building your future.\nYou were made for this.\n---\nChapter 23: The Dental Journey\nThe chair is waiting. Keep going.\nYour patients need who you are becoming."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_life_chapter("Sarah", 23, "Becoming a dentist", count=2)
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(v, str) for v in result)


def test_generate_family_legacy_returns_variations():
    raw = "The Johnson Family\nFaith. Service. Generosity.\nBuilt on love, rooted in purpose.\n---\nThe Johnson Family\nFaith. Love. Legacy.\nA name that stands for something greater."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_family_legacy("Johnson", "Faith, Service, Generosity", count=2)
    assert isinstance(result, list)
    assert len(result) == 2


def test_generate_letter_to_future_self_returns_variations():
    raw = "Dear Future Me,\nI hope you never forgot how hard you worked.\nYou earned every bit of this.\nWith love, the version of you who believed.\n---\nDear Future Me,\nYou made it. I always knew you would.\nNow go live the life you built.\nWith pride, your past self."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_letter_to_future_self("a dental student grinding through boards", count=2)
    assert isinstance(result, list)
    assert len(result) == 2
    assert all("Dear Future Me" in v or len(v) > 10 for v in result)
