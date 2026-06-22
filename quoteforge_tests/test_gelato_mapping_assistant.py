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


def test_family_covered_reads_the_family_map(monkeypatch):
    from quoteforge.automation import gelato_variant_resolver as r
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", "{}")
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_FILE", "")
    assert r.family_covered("tote") is False                       # unmapped
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP",
                       '{"branded:tote": "tote-bag_pf_real_ver_1"}')
    assert r.family_covered("tote") is True                        # real UID
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", '{"branded:tote": "GEL-PLACEHOLDER"}')
    assert r.family_covered("tote") is False                       # GEL-* = placeholder


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


def test_mapping_a_department_marks_it_ready(monkeypatch):
    # REGRESSION: mapping a new department's families to real UIDs flips its guard
    # to all_real - proving the family path now works end to end for new depts.
    import json
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP", "{}")
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_FILE", "")
    from quoteforge.automation.go_live_readiness import unmapped_families
    branded = [f for f in unmapped_families()["unmapped_families"] if f.startswith("branded:")]
    assert branded
    monkeypatch.setenv("GELATO_PRODUCT_FAMILY_MAP",
                       json.dumps({f: f"prod-{i}_ver_1" for i, f in enumerate(branded)}))
    from quoteforge.etsy.branded_catalog import verify_branded_mappings
    assert verify_branded_mappings()["all_real"] is True


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
