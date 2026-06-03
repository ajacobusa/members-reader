from unittest.mock import patch, MagicMock
from quoteforge.quotes.generator import generate_quotes

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
