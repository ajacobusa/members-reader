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
    # The production build externalizes the main JS into docs/app.js, so scan BOTH
    # the page and the script bundle - a supplier name could otherwise hide in JS.
    root = Path(__file__).resolve().parent.parent / "docs"
    text = ""
    for fn in ("index.html", "app.js"):
        p = root / fn
        if p.exists():
            text += p.read_text(encoding="utf-8").lower()
    for banned in SUPPLIER_NAMES:
        assert banned not in text, f"supplier name '{banned}' leaked into storefront"


# Purely customer-facing modules: a supplier name in the SOURCE would regenerate
# into the page on the next rebuild, so guard the generators directly too.
_CUSTOMER_FACING_SOURCES = [
    "quoteforge/etsy/listing_preview.py",   # generates docs/index.html
    "quoteforge/ai/ange.py",                # the storefront assistant
    "quoteforge/etsy/customer_messages.py",  # messages sent to buyers
]


def test_customer_facing_source_has_no_supplier_name():
    root = Path(__file__).resolve().parent.parent
    for rel in _CUSTOMER_FACING_SOURCES:
        text = (root / rel).read_text(encoding="utf-8").lower()
        for banned in SUPPLIER_NAMES:
            assert banned not in text, f"supplier name '{banned}' in {rel}"


def test_returns_policy_is_legally_protective_not_overpromising():
    """The storefront returns/FAQ copy must scope coverage (our-fault only),
    state made-to-order finality, and the 7-day window - never a blanket remake."""
    from quoteforge.etsy.listing_preview import _competitive_sections
    html = _competitive_sections().lower()
    assert "fix or remake it" not in html          # old blanket overpromise gone
    assert "all sales are final" in html           # finality stated
    assert "made to order" in html
    assert "7 days" in html                        # claim window stated
    assert "damaged or defective" in html          # coverage scoped to our fault
