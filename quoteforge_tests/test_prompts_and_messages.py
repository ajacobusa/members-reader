from unittest.mock import patch, MagicMock

from quoteforge.quotes.generator import (
    generate_heartfelt_message,
    generate_christian_encouragement,
    generate_graduation_message,
)
from quoteforge.etsy.customer_messages import (
    BASE_TEMPLATES,
    MESSAGE_TYPES,
    MESSAGE_TONES,
    get_base_template,
    get_all_base_templates_formatted,
    generate_personalized_customer_message,
)


def _mock_claude(text: str):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    return mock_client


# ── Base template tests ──────────────────────────────────────────

def test_base_templates_has_all_types():
    # Five types: includes "In Production" (added for full lifecycle coverage)
    assert len(BASE_TEMPLATES) == 5


def test_all_message_types_present():
    for t in ["Order Received", "Proof Ready", "In Production",
              "Order Shipped", "Review Request"]:
        assert t in BASE_TEMPLATES
        assert len(BASE_TEMPLATES[t]) > 20


def test_get_base_template_returns_text():
    text = get_base_template("Order Received")
    assert "order" in text.lower()


def test_get_base_template_unknown_returns_empty():
    assert get_base_template("Unknown Type") == ""


def test_get_all_templates_formatted_contains_all_types():
    result = get_all_base_templates_formatted()
    for t in MESSAGE_TYPES:
        assert t in result


def test_message_tones_populated():
    assert len(MESSAGE_TONES) >= 4


# ── Prompt template generator tests ─────────────────────────────

def test_generate_heartfelt_message_returns_variations():
    raw = "Dear Emma,\nYou have worked so hard for this moment.\nWe are so proud of you.\n---\nEmma,\nToday marks the beginning of everything you dreamed of.\nYou deserve every bit of it."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_heartfelt_message(
            recipient="Emma",
            occasion="Graduation",
            relationship="Daughter",
            tone="Warm & Heartfelt",
            word_count=120,
            count=2,
        )
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(len(v) > 10 for v in result)


def test_generate_christian_encouragement_returns_variations():
    raw = "Dear Sarah,\nGod sees your struggle and holds you through it.\nYour faith is your anchor.\n---\nSarah,\nIn this season of challenge, remember that strength comes from above.\nYou are not alone."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_christian_encouragement(
            recipient="Sarah",
            challenge="Dental school boards exam",
            bible_theme="Strength & courage",
            count=2,
        )
    assert isinstance(result, list)
    assert len(result) == 2


def test_generate_graduation_message_returns_variations():
    raw = "Michael,\nDoctor of Dental Surgery — you earned every letter.\nGo change smiles and lives.\n---\nMichael,\nThe chair is waiting. The patients are ready.\nYou spent years becoming the dentist only you can be."
    with patch("quoteforge.quotes.generator.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_graduation_message(
            name="Michael",
            degree="Doctor of Dental Surgery (DDS)",
            career_goal="Open a dental practice",
            count=2,
        )
    assert isinstance(result, list)
    assert len(result) == 2


# ── Personalized customer message tests ─────────────────────────

def test_generate_personalized_customer_message_returns_string():
    raw = "Hi Jennifer! I am so excited to be creating your daughter Emma's graduation print. I will have your proof ready within 24 hours. Thank you for choosing ScenicSoulPrints!"
    with patch("quoteforge.etsy.customer_messages.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.etsy.customer_messages.anthropic.Anthropic",
               return_value=_mock_claude(raw)):
        result = generate_personalized_customer_message(
            message_type="Order Received",
            customer_name="Jennifer",
            occasion="Graduation",
            recipient_name="Emma",
            shop_name="ScenicSoulPrints",
            tone="Warm & Professional",
        )
    assert isinstance(result, str)
    assert len(result) > 10


def test_all_message_types_accepted():
    raw = "Test message response."
    for msg_type in MESSAGE_TYPES:
        with patch("quoteforge.etsy.customer_messages.ANTHROPIC_API_KEY", "test-key"), \
             patch("quoteforge.etsy.customer_messages.anthropic.Anthropic",
                   return_value=_mock_claude(raw)):
            result = generate_personalized_customer_message(
                message_type=msg_type,
                customer_name="Alice",
                occasion="Birthday",
                recipient_name="Bob",
            )
        assert isinstance(result, str)
