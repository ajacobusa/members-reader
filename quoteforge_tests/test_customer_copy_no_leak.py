"""Regression: customer-facing copy must never name the fulfilment supplier
(Gelato/Printify/Printful) or the marketplace (Etsy).

This guards the two surfaces that ship verbatim to buyers: the queued customer
message templates and the storefront page. A supplier/marketplace name leaking
into either is a hard brand/policy violation."""
from pathlib import Path

SUPPLIER_NAMES = ("gelato", "printify", "printful")


def test_customer_message_templates_have_no_supplier_or_marketplace_name():
    from quoteforge.etsy.customer_messages import BASE_TEMPLATES
    for name, body in BASE_TEMPLATES.items():
        low = body.lower()
        for banned in SUPPLIER_NAMES:
            assert banned not in low, f"'{banned}' leaked into '{name}' template"
        assert "etsy" not in low, f"'Etsy' leaked into '{name}' template"


def test_storefront_page_has_no_supplier_name():
    page = (Path(__file__).resolve().parent.parent / "docs" / "index.html")
    text = page.read_text(encoding="utf-8").lower()
    for banned in SUPPLIER_NAMES:
        assert banned not in text, f"supplier name '{banned}' leaked into storefront"
