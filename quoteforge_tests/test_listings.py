from unittest.mock import patch, MagicMock
from quoteforge.etsy.listings import generate_listing

def _mock_claude(text: str):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    return mock_client

def test_generate_listing_returns_dict():
    fake_text = """TITLE: Inspirational Mountain Quote Wall Art
TAGS: motivational poster,wall art print,mountain decor,office art,inspirational quote,nature print,gift for him,positive mindset,entrepreneur gift,home decor,wall decor,quote print,modern art
DESCRIPTION: Bring the power of the mountains into your space with this stunning motivational wall art print."""

    with patch("quoteforge.etsy.listings.anthropic.Anthropic", return_value=_mock_claude(fake_text)):
        listing = generate_listing(
            quote="Rise above the storm.",
            category="Motivation & Mindset",
            subcategory="Growth mindset",
        )
    assert "title" in listing
    assert "tags" in listing
    assert "description" in listing
    assert isinstance(listing["tags"], list)
    assert len(listing["tags"]) <= 13
