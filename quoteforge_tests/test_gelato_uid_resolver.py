"""Gelato UID Resolver - auto-discover real productUids, BLOCKED-not-guessed.

The safety invariant: the resolver can only ever make the registry MORE correct. It writes
ONLY unambiguous, high-confidence 1:1 matches; an over-match (one UID claimed by many SKUs)
or a low-confidence match is BLOCKED, never written; and every write still passes through
map_real_gelato_uid, which refuses a GEL-* value. Live-gated. Isolated DB per test.
"""
import pytest

from quoteforge.automation import gelato_uid_resolver as R


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    monkeypatch.setenv("GELATO_UID_MAP_FILE", str(tmp_path / "uidmap.json"))
    db.init_db()
    return tmp_path


def _prod(uid, title, **attrs):
    return R._normalise_product({"productUid": uid, "title": title, "attributes": attrs})


# ── Matching / scoring ───────────────────────────────────────────

def test_score_is_anchored_no_coincidental_match():
    toks = R._norm_tokens("GEL-M-TSHIRT-M-WHITE") | R._norm_tokens("apparel")
    good = _prod("apparel_tshirt_white_m", "Crew T-Shirt White M tshirt",
                 GarmentColor="white", GarmentSize="m")
    assert R.score_match(toks, good) >= 0.72
    decoy = _prod("mug_11oz_black", "Ceramic Mug Black", MugColor="black")
    assert R.score_match(toks, decoy) == 0.0        # zero overlap -> zero, never partial


def test_normalise_rejects_placeholder_and_missing_uid():
    assert R._normalise_product({"productUid": "GEL-STILL-SEED", "title": "x"}) is None
    assert R._normalise_product({"title": "no uid"}) is None
    assert R._normalise_product("not a dict") is None


# ── Ambiguity guard (the wrong-product protection) ───────────────

def test_over_match_is_blocked_not_written(iso_db):
    # one catalog product that many SKUs partially match -> the UID is claimed by >1 SKU
    # -> ALL claimants are blocked as ambiguous, zero written.
    cat = [_prod("apparel_tshirt_white_m", "Crew T-Shirt White M tshirt",
                 GarmentColor="white", GarmentSize="m")]
    s = R.resolve_all(apply=True, min_confidence=0.5, catalog=cat)
    assert s["written"] == 0 and s["resolved"] == 0 and s["blocked"] == s["candidates"]
    from quoteforge.automation.gelato_readiness import registry_uid_map
    assert registry_uid_map() == {}


def test_clean_one_to_one_matches_are_drafted_not_live(iso_db, monkeypatch):
    # The resolver DRAFTS matches (approved_for_go_live=0). They must NOT reach the runtime
    # map until an admin verifies + approves them - the staged go-live safety.
    monkeypatch.setattr(R, "_our_unmapped_items", lambda: [
        {"family": "apparel", "sku": "GEL-UNIQ-ALPHA", "tokens": R._norm_tokens("uniqalpha zzq")},
        {"family": "apparel", "sku": "GEL-UNIQ-BETA", "tokens": R._norm_tokens("uniqbeta yyw")}])
    cat = [_prod("real_alpha", "uniqalpha zzq"), _prod("real_beta", "uniqbeta yyw")]
    s = R.resolve_all(apply=True, min_confidence=0.5, catalog=cat)
    assert s["resolved"] == 2 and s["written"] == 2
    from quoteforge.automation.gelato_readiness import (
        registry_uid_map, pending_review, verify_uid, approve_uid)
    assert registry_uid_map() == {}                     # drafts are NOT live
    assert {r["sku"] for r in pending_review()} == {"GEL-UNIQ-ALPHA", "GEL-UNIQ-BETA"}
    # verify + approve one -> only that one goes live
    verify_uid("GEL-UNIQ-ALPHA", checker=lambda uid: True)
    approve_uid("GEL-UNIQ-ALPHA")
    assert registry_uid_map() == {"GEL-UNIQ-ALPHA": "real_alpha"}


def test_dry_run_writes_nothing(iso_db, monkeypatch):
    monkeypatch.setattr(R, "_our_unmapped_items", lambda: [
        {"family": "apparel", "sku": "GEL-UNIQ-ALPHA", "tokens": R._norm_tokens("uniqalpha zzq")}])
    cat = [_prod("real_alpha", "uniqalpha zzq")]
    s = R.resolve_all(apply=False, min_confidence=0.5, catalog=cat)
    assert s["resolved"] == 1 and s["written"] == 0
    from quoteforge.automation.gelato_readiness import registry_uid_map
    assert registry_uid_map() == {}


def test_write_rejects_placeholder_uid(iso_db, monkeypatch):
    # even a "confident" match to a GEL-* value must never be written (map_real refuses it)
    monkeypatch.setattr(R, "_our_unmapped_items", lambda: [
        {"family": "apparel", "sku": "GEL-UNIQ-ALPHA", "tokens": R._norm_tokens("uniqalpha")}])
    # a normalised product can't hold a GEL-* uid, so force a raw candidate through resolve
    cat = [{"uid": "GEL-LEFTOVER", "text": "uniqalpha", "attrs": {}}]
    s = R.resolve_all(apply=True, min_confidence=0.4, catalog=cat)
    from quoteforge.automation.gelato_readiness import registry_uid_map
    assert registry_uid_map() == {}      # placeholder value never laundered in


# ── Dimension anchor (the wrong-SIZE protection, Critical) ───────

def test_size_agnostic_product_is_disqualified(iso_db):
    # REGRESSION (Critical): a Gelato product that names NO size once scored 0.75 against
    # GEL-M-TSHIRT-M-WHITE (the men's-code 'm' collapsed with size 'm') and, as the lone
    # unmapped size, would auto-write -> a Medium order could ship as any size. The size
    # dimension must be positively confirmed, so a size-agnostic product is disqualified.
    item = {"family": "apparel", "sku": "GEL-M-TSHIRT-M-WHITE",
            "tokens": R._sku_tokens("apparel", "GEL-M-TSHIRT-M-WHITE")}
    agnostic = {"uid": "gel-size-agnostic", "text": "apparel tshirt white", "attrs": {}}
    assert R.resolve_sku(item, [agnostic])["uid"] is None       # blocked
    real_m = _prod("real_m", "Crew T-Shirt White M tshirt", GarmentColor="white", GarmentSize="m")
    assert R.resolve_sku(item, [real_m])["uid"] == "real_m"     # confirmed size resolves


def test_single_claimant_wrong_size_is_blocked_end_to_end(iso_db, monkeypatch):
    # The whole pipeline: a lone M-size SKU + a size-agnostic catalog must write NOTHING.
    monkeypatch.setattr(R, "_our_unmapped_items", lambda: [
        {"family": "apparel", "sku": "GEL-M-TSHIRT-M-WHITE",
         "tokens": R._sku_tokens("apparel", "GEL-M-TSHIRT-M-WHITE")}])
    cat = [{"uid": "gel-size-agnostic", "text": "apparel tshirt white", "attrs": {}}]
    s = R.resolve_all(apply=True, catalog=cat)
    assert s["written"] == 0 and s["resolved"] == 0
    from quoteforge.automation.gelato_readiness import registry_uid_map
    assert registry_uid_map() == {}


def test_mug_capacity_dimension_anchored(iso_db):
    # R7: a mug SKU must confirm its capacity (11oz), not match on {mug,white} alone.
    item = {"family": "mug", "sku": "GEL-MUG-11OZ-WHITE",
            "tokens": R._sku_tokens("mug", "GEL-MUG-11OZ-WHITE")}
    assert R.resolve_sku(item, [{"uid": "gel-mug", "text": "mug white ceramic", "attrs": {}}])["uid"] is None
    ok = {"uid": "real_mug", "text": "mug white 11oz ceramic", "attrs": {}}
    assert R.resolve_sku(item, [ok])["uid"] == "real_mug"


def test_infra_check_resolver_size_anchored(iso_db):
    from quoteforge.automation.infra_check import check_infrastructure
    got = next(c for c in check_infrastructure()["checks"]
               if c["name"] == "resolver_size_anchored")
    assert got["ok"] is True


# ── Live-gating + CLI ────────────────────────────────────────────

def test_no_op_without_key(iso_db):
    # TEST_MODE (default in tests): _fetch_catalog returns [] -> nothing resolved
    s = R.resolve_all(apply=True)
    assert s["live"] is False and s["catalog_size"] == 0 and s["written"] == 0


def test_cli_status_and_dry_run(iso_db, capsys):
    from quoteforge import admin
    assert admin.main(["gelato-resolve", "status"]) == 0
    assert "resolver" in capsys.readouterr().out.lower()
    assert admin.main(["gelato-resolve", "dry-run"]) == 0
    assert "DRY-RUN" in capsys.readouterr().out
