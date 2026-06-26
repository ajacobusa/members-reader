"""Go-live Gelato mapping assistant: family resolution across all departments,
the readiness aggregator, the preflight gate, and the admin helpers."""
from __future__ import annotations


# ── Resolver family keys now span every department ──────────────────

def test_family_key_resolves_all_departments():
    from quoteforge.automation import gelato_variant_resolver as r
    assert r.family_key("m_tshirt") == "tshirt:Classic"   # apparel unchanged
    assert r.family_key("tote") == "branded:tote"          # branded namespaced
    assert r.family_key("classic_mug") == "mug:classic_mug"
    assert r.family_key("wall_cal") == "calendar:wall_cal"
    assert r.family_key("not-a-real-id") is None


def test_family_covered_is_apparel_only(monkeypatch):
    # REGRESSION: family coverage means a family mapping alone resolves every variant
    # at order time - which is APPAREL-ONLY (dynamic GarmentColor/GarmentSize search).
    # mug/branded/calendar use different Gelato attributes, so a family mapping does
    # NOT cover them (they need a static per-SKU UID); family_covered must report that
    # honestly, or the readiness report shows them ready while orders route to manual.
    from quoteforge.automation import gelato_variant_resolver as r
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", "{}")
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_FILE", "")
    assert r.family_covered("m_tshirt") is False                   # unmapped apparel
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP",
                       '{"tshirt:Classic": "tshirt_pf_real_ver_1"}')
    assert r.family_covered("m_tshirt") is True                    # apparel: real UID
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", '{"tshirt:Classic": "GEL-PLACEHOLDER"}')
    assert r.family_covered("m_tshirt") is False                   # GEL-* = placeholder
    # Non-apparel is NEVER family-covered, even when its family maps to a real UID:
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP",
                       '{"branded:tote": "tote-bag_pf_real_ver_1"}')
    assert r.family_covered("tote") is False                       # needs a static UID


# ── Readiness aggregator + mapping template ─────────────────────────

def test_mapping_readiness_covers_all_departments():
    from quoteforge.automation.go_live_readiness import mapping_readiness
    r = mapping_readiness()
    names = {d["name"] for d in r["departments"]}
    assert {"Apparel", "Branded Products", "Custom Mugs", "Custom Calendars"} <= names
    assert r["total"] > 0
    assert {"departments", "total", "configured", "placeholder_count",
            "overall_ready"} <= set(r)


def test_unmapped_families_lists_new_departments_and_template(monkeypatch):
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", "{}")
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_FILE", "")
    from quoteforge.automation.go_live_readiness import unmapped_families
    u = unmapped_families()
    for fk in ("branded:tote", "mug:classic_mug", "calendar:wall_cal"):
        assert fk in u["unmapped_families"], fk
    assert u["template"]["branded:tote"] == "REPLACE_WITH_GELATO_PRODUCT_UID"


def test_nonapparel_family_mapping_does_not_mark_ready(monkeypatch):
    # REGRESSION: mapping a mug/branded/calendar FAMILY must NOT mark its variants
    # go-live-ready. The dynamic resolver is apparel-only, so those orders would
    # silently route to manual; they are ready only with a static per-SKU UID.
    # (The readiness report previously showed them ready - the false positive.)
    import json
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", "{}")
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_FILE", "")
    from quoteforge.automation.go_live_readiness import unmapped_families
    branded = [f for f in unmapped_families()["unmapped_families"] if f.startswith("branded:")]
    assert branded
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP",
                       json.dumps({f: f"prod-{i}_ver_1" for i, f in enumerate(branded)}))
    from quoteforge.etsy.branded_catalog import verify_branded_mappings
    rep = verify_branded_mappings()
    # Family mapping did NOT clear the placeholders - branded needs static per-SKU UIDs.
    assert rep["placeholders"] and not rep["all_real"]


# ── Preflight go-live gate ──────────────────────────────────────────

def test_preflight_blocks_go_live_until_mapped(monkeypatch):
    # REGRESSION: in live mode an unmapped department is a hard FAIL (cannot go
    # live with placeholders); in TEST_MODE it is informational, never a blocker.
    from quoteforge import preflight, config
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", "{}")
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_FILE", "")
    monkeypatch.setattr(config, "TEST_MODE", False, raising=False)
    assert any(r.status == "FAIL" for r in preflight.check_product_mappings())
    monkeypatch.setattr(config, "TEST_MODE", True, raising=False)
    assert all(r.status != "FAIL" for r in preflight.check_product_mappings())


def test_preflight_software_includes_mapping_gate(monkeypatch):
    from quoteforge import preflight, config
    monkeypatch.setattr(config, "TEST_MODE", True, raising=False)
    names = {r.name for r in preflight.check_software()}
    assert any("Product mappings" in n for n in names)


def test_admin_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "go-live-readiness" in COMMANDS and "map-gelato" in COMMANDS
