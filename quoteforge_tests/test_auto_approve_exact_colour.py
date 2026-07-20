"""Guardrailed auto-approval of exact colour-sibling UID drafts (owner policy
2026-07-20). A draft goes live WITHOUT manual approval ONLY when it extends an
owner-approved pattern by pure colour: colour-only UID diff (material preserved),
no translation/substitution marker, 1:1 UID, and a POSITIVE live existence check.
Everything else must stay in the owner queue. Isolated DB per test."""
import pytest

from quoteforge.automation import gelato_readiness as gr


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    monkeypatch.setenv("GELATO_UID_MAP_FILE", str(tmp_path / "uidmap.json"))
    db.init_db()
    return tmp_path


OWNER_MUG = "mug_product_msz_11-oz_mmat_ceramic-white_cl_4-0"
BLUE_MUG = "mug_product_msz_11-oz_mmat_ceramic-blue_cl_4-0"
MAGIC_MUG = "mug_product_msz_11-oz_mmat_heat-transfer-black_cl_4-0"
BIG_MUG = "mug_product_msz_15-oz_mmat_ceramic-blue_cl_4-0"
OWNER_TEE = "apparel_product_gca_t-shirt_gsc_crewneck_gcu_unisex_gqa_prm_gsi_l_gco_white_gpr_0-4"
BROWN_TEE = "apparel_product_gca_t-shirt_gsc_crewneck_gcu_unisex_gqa_prm_gsi_l_gco_brown_gpr_0-4"
XL_TEE = "apparel_product_gca_t-shirt_gsc_crewneck_gcu_unisex_gqa_prm_gsi_4xl_gco_white_gpr_0-4"
HEAVY_TEE = "apparel_product_gca_t-shirt_gsc_crewneck_gcu_unisex_gqa_heavy-weight_gsi_l_gco_white_gpr_0-4"


def test_colour_sibling_predicate_grammar():
    # pure-colour key (gco): any colour swap is a sibling
    assert gr._colour_sibling_of(BROWN_TEE, OWNER_TEE)
    # material+colour key (mmat): material must be preserved
    assert gr._colour_sibling_of(BLUE_MUG, OWNER_MUG)
    assert not gr._colour_sibling_of(MAGIC_MUG, OWNER_MUG)   # ceramic != heat-transfer
    # size / tier changes are NEVER colour siblings
    assert not gr._colour_sibling_of(XL_TEE, OWNER_TEE)      # gsi size change
    assert not gr._colour_sibling_of(HEAVY_TEE, OWNER_TEE)   # gqa tier change
    assert not gr._colour_sibling_of(BIG_MUG, BLUE_MUG)      # msz size change


def test_auto_approves_exact_colour_sibling(iso_db):
    gr.map_real_gelato_uid("mug", "GEL-M-WHITE", OWNER_MUG, source="owner")
    gr.draft_uid("mug", "GEL-M-BLUE", BLUE_MUG, score=0.9, reason="exact colour slug")
    acts = gr.auto_approve_exact_colour_siblings(checker=lambda uid: True)
    assert [a for a in acts if a["action"] == "approved"][0]["sku"] == "GEL-M-BLUE"
    assert gr.registry_uid_map()["GEL-M-BLUE"] == BLUE_MUG   # live now
    row = next(r for r in gr.registry_rows() if r["sku"] == "GEL-M-BLUE")
    assert row["source"] == gr.AUTO_APPROVE_SOURCE           # audited stamp
    assert "AUTO-APPROVED" in row["match_reason"]


def test_never_approves_without_owner_rooted_sibling(iso_db):
    # An auto-approved row must NOT seed further auto-approvals (no bootstrapping).
    gr.draft_uid("mug", "GEL-M-BLUE", BLUE_MUG, score=0.9, reason="exact colour slug")
    acts = gr.auto_approve_exact_colour_siblings(checker=lambda uid: True)
    assert all(a["action"] == "skipped" for a in acts)
    assert gr.registry_uid_map() == {}


def test_size_and_tier_changes_stay_owner_gated(iso_db):
    gr.map_real_gelato_uid("apparel", "GEL-T-L-WHITE", OWNER_TEE, source="owner")
    gr.draft_uid("apparel", "GEL-T-4XL-WHITE", XL_TEE, score=0.9, reason="exact")
    gr.draft_uid("apparel", "GEL-T-L-HEAVY", HEAVY_TEE, score=0.9, reason="exact")
    acts = gr.auto_approve_exact_colour_siblings(checker=lambda uid: True)
    assert all(a["action"] == "skipped" for a in acts)
    assert "GEL-T-4XL-WHITE" not in gr.registry_uid_map()


def test_translated_colours_stay_owner_gated(iso_db):
    gr.map_real_gelato_uid("apparel", "GEL-T-L-WHITE", OWNER_TEE, source="owner")
    gr.draft_uid("apparel", "GEL-T-L-BROWN", BROWN_TEE, score=0.9,
                 reason="COLOUR TRANSLATED our 'chocolate' -> 'brown' (needs visual judgement)")
    acts = gr.auto_approve_exact_colour_siblings(checker=lambda uid: True)
    assert all(a["action"] == "skipped" for a in acts)


def test_negative_or_failing_live_check_never_approves(iso_db):
    gr.map_real_gelato_uid("mug", "GEL-M-WHITE", OWNER_MUG, source="owner")
    gr.draft_uid("mug", "GEL-M-BLUE", BLUE_MUG, score=0.9, reason="exact colour slug")
    acts = gr.auto_approve_exact_colour_siblings(checker=lambda uid: False)
    assert all(a["action"] == "skipped" for a in acts)

    def boom(uid):
        raise RuntimeError("api down")
    acts = gr.auto_approve_exact_colour_siblings(checker=boom)
    assert all(a["action"] == "skipped" for a in acts)
    assert gr.registry_uid_map() == {"GEL-M-WHITE": OWNER_MUG}


def test_duplicate_uid_claim_stays_owner_gated(iso_db):
    gr.map_real_gelato_uid("mug", "GEL-M-WHITE", OWNER_MUG, source="owner")
    gr.map_real_gelato_uid("mug", "GEL-M-BLUE1", BLUE_MUG, source="owner")
    gr.draft_uid("mug", "GEL-M-BLUE2", BLUE_MUG, score=0.9, reason="exact colour slug")
    acts = gr.auto_approve_exact_colour_siblings(checker=lambda uid: True)
    assert all(a["action"] == "skipped" for a in acts)          # 1:1 violated


def test_infra_invariant_92_flags_a_bypassed_guardrail(iso_db):
    # REGRESSION: the daily sweep re-audits every auto-approved row. Simulate a
    # bypass: an auto-stamped row whose owner-approved sibling was later removed.
    gr.map_real_gelato_uid("mug", "GEL-M-WHITE", OWNER_MUG, source="owner")
    gr.draft_uid("mug", "GEL-M-BLUE", BLUE_MUG, score=0.9, reason="exact colour slug")
    gr.auto_approve_exact_colour_siblings(checker=lambda uid: True)
    from quoteforge.automation.infra_check import check_infrastructure
    c = next(x for x in check_infrastructure()["checks"]
             if x["name"] == "auto_approved_mappings_guardrailed")
    assert c["ok"], c["detail"]                                 # healthy while rooted
    gr.reject_uid("GEL-M-WHITE")                                # owner root vanishes
    c = next(x for x in check_infrastructure()["checks"]
             if x["name"] == "auto_approved_mappings_guardrailed")
    assert not c["ok"] and "no owner-approved colour sibling" in c["detail"]
