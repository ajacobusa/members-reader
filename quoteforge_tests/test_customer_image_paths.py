"""Customer-visualization image paths — #68 template previews + #69 pinned wiring.

The three documented ways the customer sees the REAL product must stay wired:
  1. final proof: customer_proof composites the buyer's design via design_mockup_for_order
  2. listing images: image_validation / gelato_live_ops read the Etsy listing-images API
  3. template previews (#68): the earliest real product image, live-gated + hermetic
All local; no network.
"""
import inspect

from quoteforge.automation import ecommerce_images as ei


# ── #68: template previews source ──────────────────────────────────────────────

def test_template_previews_noop_when_not_live():
    # TEST_MODE / no store id -> [] and the getter is NEVER consulted (hermetic gate).
    called = []
    out = ei.template_previews(getter=lambda p: (called.append(p), {"templates": []})[1])
    assert out == [] and called == []


def test_template_previews_parses_shapes(monkeypatch):
    monkeypatch.setattr(ei, "_gate", lambda: (True, "store-1"))
    payload = {"templates": [
        {"id": "T1", "title": "Classic Mug", "previewUrl": "https://s3/x.jpg"},
        {"templateId": "T2", "title": "Tee",                       # alt id + nested preview
         "variants": [{"imagePlaceholders": [{"previewUrl": "https://s3/y.jpg"}]}]},
        {"id": "T3", "title": "no preview at all"},                # dropped (no url)
        "garbage",                                                 # dropped (not a dict)
    ]}
    rows = ei.template_previews(getter=lambda p: payload)
    assert [r["template_id"] for r in rows] == ["T1", "T2"]
    assert rows[0]["preview_url"] == "https://s3/x.jpg"
    assert rows[1]["preview_url"] == "https://s3/y.jpg"


def test_template_previews_path_targets_store(monkeypatch):
    monkeypatch.setattr(ei, "_gate", lambda: (True, "store-9"))
    seen = []
    ei.template_previews(getter=lambda p: (seen.append(p), {"templates": []})[1])
    assert seen == ["/stores/store-9/templates"]


def test_template_previews_command_registered():
    from quoteforge.admin import COMMANDS
    assert "template-previews" in COMMANDS


# ── #69: proof + listing-image wiring pinned ───────────────────────────────────

def test_proof_composites_design_on_real_product():
    # REGRESSION: the final proof must keep calling design_mockup_for_order (buyer's
    # design on the REAL garment) - unwiring it silently downgrades the proof.
    from quoteforge.automation import customer_proof
    assert "design_mockup_for_order" in inspect.getsource(customer_proof)


def test_listing_images_consumed_by_validation_and_live_ops():
    from quoteforge.automation import image_validation, gelato_live_ops
    assert "get_listing_images" in inspect.getsource(image_validation)
    assert "official_listing_images" in inspect.getsource(gelato_live_ops)


def test_infra_invariant_customer_image_paths():
    from quoteforge.automation.infra_check import check_infrastructure
    hit = [c for c in check_infrastructure()["checks"]
           if c["name"] == "customer_image_paths_wired"]
    assert hit and hit[0]["ok"] is True
