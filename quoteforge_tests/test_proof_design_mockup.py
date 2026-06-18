"""Proof-stage personalized product mockup - guardrails + customer confirmation.

The mockup (the buyer's design rendered ON the garment) is a VISUAL AID in the
proof. The invariants that protect production: it is key-gated (no-op until live),
it NEVER blocks the proof (any failure -> proof still goes out with the flat
artwork), and it does NOT bypass the customer's proof approval - printing stays
blocked at `awaiting_customer_approval` until the buyer confirms, and the parity-
gate hash still fingerprints the real artwork, not the mockup.
"""
from unittest.mock import patch

import quoteforge.images.supplier_mockup as sm
from quoteforge.automation.customer_proof import prepare_customer_proof


def _go_live(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "k_live")


# ── design_mockup_for_order: key-gated + guarded ─────────────────

def test_mockup_none_in_test_mode():
    order = {"product_type": "apparel", "gelato_product_uid": "u",
             "artwork_url": "https://h/a.png"}
    assert sm.design_mockup_for_order(order) is None        # TEST_MODE -> no-op


def test_mockup_none_for_non_apparel(monkeypatch):
    _go_live(monkeypatch)
    order = {"product_type": "wall_art", "gelato_product_uid": "u",
             "artwork_url": "https://h/a.png"}
    assert sm.design_mockup_for_order(order) is None


def test_mockup_requires_fetchable_design(monkeypatch):
    # A LOCAL path can't be rendered by Gelato - must be an http(s) URL it can fetch.
    _go_live(monkeypatch)
    monkeypatch.setattr(sm, "_gelato_create_design_mockup",
                        lambda uid, d: "http://should/not/matter.png")
    order = {"product_type": "apparel", "gelato_product_uid": "u",
             "artwork_url": "/local/art.png"}
    assert sm.design_mockup_for_order(order) is None


def test_mockup_resolves_when_live(monkeypatch):
    _go_live(monkeypatch)
    monkeypatch.setattr(sm, "_gelato_create_design_mockup",
                        lambda uid, d: f"http://cdn/mock_{uid}.png")
    order = {"product_type": "apparel", "gelato_product_uid": "uid_123",
             "artwork_url": "https://host/art.png"}
    assert sm.design_mockup_for_order(order) == "http://cdn/mock_uid_123.png"


def test_mockup_never_raises():
    assert sm.design_mockup_for_order(None) is None
    assert sm.design_mockup_for_order("not a dict") is None


# ── prepare_customer_proof: additive + confirmation intact ───────

def _order(db, oid):
    db.create_order({"order_id": oid, "recipient_name": "Lee",
                     "occasion": "Birthday", "product_type": "apparel"})


def test_proof_includes_mockup_but_still_requires_confirmation(tmp_path, monkeypatch):
    # REGRESSION: when a mockup is available it's added as a visual aid - but the
    # customer must STILL confirm; printing stays blocked.
    import quoteforge.db.database as db
    monkeypatch.setattr(sm, "design_mockup_for_order",
                        lambda order, design=None: "http://cdn/mockup.png")
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db(); _order(db, "PM1")
        pkg = prepare_customer_proof("PM1", artwork_path="https://host/art.png")
        order = db.get_order("PM1")
    assert pkg["product_mockup"] == "http://cdn/mockup.png"
    assert "on the garment" in pkg["proof_message"]
    # GUARDRAIL: the mockup does NOT auto-approve - confirmation still required
    assert order["status"] == "awaiting_customer_approval"
    assert not order.get("proof_approved")
    # the authoritative print file is still the artwork, not the mockup
    assert pkg["artwork_path"] == "https://host/art.png"


def test_proof_falls_back_without_mockup(tmp_path):
    # TEST_MODE: no mockup -> proof still prepared with the flat artwork, blocked.
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db(); _order(db, "PM2")
        pkg = prepare_customer_proof("PM2", artwork_path="https://h/a.png")
        order = db.get_order("PM2")
    assert pkg["product_mockup"] is None
    assert "on the garment" not in pkg["proof_message"]
    assert order["status"] == "awaiting_customer_approval"


def test_proof_survives_mockup_error(tmp_path, monkeypatch):
    # GUARDRAIL: a mockup error must NEVER block the proof.
    import quoteforge.db.database as db
    def boom(order, design=None):
        raise RuntimeError("gelato mockup down")
    monkeypatch.setattr(sm, "design_mockup_for_order", boom)
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db(); _order(db, "PM3")
        pkg = prepare_customer_proof("PM3", artwork_path="https://h/a.png")
        order = db.get_order("PM3")
    assert pkg["product_mockup"] is None                    # error swallowed
    assert order["status"] == "awaiting_customer_approval"  # proof still went out
