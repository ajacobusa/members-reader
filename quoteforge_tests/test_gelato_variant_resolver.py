"""Dynamic colour/size -> Gelato variant UID resolution.

The whole point: the owner maps ~21 product FAMILIES (garment_type:tier) instead
of ~3,120 per-variant SKUs, and the resolver produces each variant's UID at order
time. The go-live guard must clear once the families are mapped. Like every Gelato
seam, it's a no-op until genuinely live (TEST_MODE / no key / no family -> None).
"""
import json

from quoteforge.automation import gelato_variant_resolver as R
from quoteforge.etsy.apparel_catalog import (
    APPAREL_CATALOG, apparel_sku_for, verify_apparel_mappings)


def _all_families() -> dict:
    return {f"{g.garment_type}:{g.tier}": f"gca_{g.garment_type}_{g.tier}".lower()
            for g in APPAREL_CATALOG}


def _go_live(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "k_live")


# ── No-op until live ─────────────────────────────────────────────

def test_test_mode_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    sku = apparel_sku_for("m_tshirt", "M", "White")
    assert R.resolve_variant_uid(sku) is None        # TEST_MODE, no static, no family


def test_none_sku_never_raises():
    assert R.resolve_variant_uid(None) is None


# ── Static map still wins (back-compat) ──────────────────────────

def test_static_uid_wins(monkeypatch):
    sku = apparel_sku_for("m_tshirt", "M", "Black")
    monkeypatch.setattr("quoteforge.automation.gelato_sync._uid_map",
                        lambda: {sku: "pinned_real_uid"})
    assert R.resolve_variant_uid(sku) == "pinned_real_uid"


# ── Dynamic family resolution (live) ─────────────────────────────

def test_family_resolution_when_live(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    _go_live(monkeypatch)
    monkeypatch.setattr("quoteforge.automation.gelato_sync._uid_map", lambda: {})
    monkeypatch.setattr(R, "_family_map", lambda: {"tshirt:Classic": "gca_tee"})
    calls = []
    def search(family, color, size):
        calls.append((family, color, size))
        return f"variant_{family}_{color}_{size}".lower()
    monkeypatch.setattr(R, "_gelato_search_variant", search)
    sku = apparel_sku_for("m_tshirt", "L", "Royal Blue")
    uid = R.resolve_variant_uid(sku)
    assert uid == "variant_gca_tee_royal blue_l"
    assert calls == [("gca_tee", "Royal Blue", "L")]     # family + chosen colour/size
    # cached: a second call doesn't re-hit the API
    monkeypatch.setattr(R, "_gelato_search_variant",
                        lambda *a: "SHOULD_NOT_BE_CALLED")
    assert R.resolve_variant_uid(sku) == "variant_gca_tee_royal blue_l"
    assert json.loads((tmp_path / "gelato_variant_uids.json").read_text())[sku].startswith("variant_")


def test_family_value_placeholder_not_covered(monkeypatch):
    monkeypatch.setattr(R, "_family_map", lambda: {"tshirt:Classic": "GEL-SEED"})
    assert R.family_covered("m_tshirt") is False         # GEL-* family = unmapped


def test_family_covered_true_when_mapped(monkeypatch):
    monkeypatch.setattr(R, "_family_map", lambda: {"tshirt:Classic": "gca_tee"})
    assert R.family_covered("m_tshirt") is True


# ── The payoff: ~21 families clear the go-live guard for ~3,120 SKUs ──

def test_guard_clears_when_all_families_mapped(monkeypatch):
    # REGRESSION: mapping the (garment_type, tier) families - NOT every variant -
    # makes verify_apparel_mappings report all_real, so go-live needs ~21 entries.
    fams = _all_families()
    assert len(fams) <= 25                               # ~21, not thousands
    monkeypatch.setattr(R, "_family_map", lambda: fams)
    monkeypatch.setattr("quoteforge.automation.gelato_sync._uid_map", lambda: {})
    m = verify_apparel_mappings()
    assert m["total"] > 2000                             # ~3,120 SKUs
    assert m["all_real"] is True and m["placeholder_count"] == 0


def test_guard_flags_unmapped_family(monkeypatch):
    # One family left unmapped -> all its variants are placeholders (not all_real).
    fams = _all_families(); fams.pop("hoodie:Classic")
    monkeypatch.setattr(R, "_family_map", lambda: fams)
    monkeypatch.setattr("quoteforge.automation.gelato_sync._uid_map", lambda: {})
    m = verify_apparel_mappings()
    assert m["all_real"] is False and m["placeholder_count"] > 0


def test_admin_gelato_families(capsys):
    from quoteforge import admin
    rc = admin.main(["gelato-families"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Product families mapped" in out and "SKU coverage" in out
