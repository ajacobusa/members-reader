"""Tests for the Etsy auto-publisher (draft listings + image upload)."""
from unittest.mock import patch, MagicMock

from quoteforge.automation import etsy_publisher as pub
from quoteforge import admin


def test_dry_run_creates_nothing():
    r = pub.publish_launch_kit(live=False)
    assert r["live"] is False
    assert r["count"] == 20
    assert all(x["status"] == "dry-run" for x in r["results"])


def test_prereqs_listed_when_unset():
    with patch.object(pub, "ETSY_OAUTH_TOKEN", ""), \
         patch.object(pub, "ETSY_SHOP_ID", ""):
        missing = pub.prerequisites()
    assert any("OAUTH" in m.upper() for m in missing)


def test_create_draft_is_mock_without_prereqs():
    class B:
        title = "T"; tags = ["a"]; materials = ["m"]; description = "d"
    with patch.object(pub, "TEST_MODE", True):
        out = pub.create_draft_listing(B(), 36.99)
    assert out["status"] == "dry-run"


def test_live_create_draft_calls_api_when_ready():
    class B:
        title = "Personalized Daughter Gift"; description = "desc"
        tags = ["t1", "t2"]; materials = ["Premium Matte Paper"]
    fake = MagicMock()
    fake.post.return_value.json.return_value = {"listing_id": 555}
    fake.post.return_value.raise_for_status.return_value = None
    with patch.object(pub, "TEST_MODE", False), \
         patch.object(pub, "ETSY_OAUTH_TOKEN", "tok"), \
         patch.object(pub, "ETSY_SHOP_ID", "9"), \
         patch.object(pub, "ETSY_API_KEY", "k"), \
         patch.object(pub, "ETSY_TAXONOMY_ID", "1"), \
         patch.object(pub, "ETSY_SHIPPING_PROFILE_ID", "2"):
        out = pub.create_draft_listing(B(), 36.99, runner=fake)
    assert out["status"] == "draft_created" and out["listing_id"] == 555
    # payload created a DRAFT with personalization on
    _, kwargs = fake.post.call_args
    assert kwargs["data"]["state"] == "draft"
    assert kwargs["data"]["is_personalizable"] == "true"


def test_create_draft_refreshes_on_401(monkeypatch):
    # REGRESSION (#182-P1): Etsy access tokens expire ~1h after issuance. A 401
    # mid-run must trigger a single refresh + retry, not a hard failure (which would
    # silently stall publishing). Grounded on etsy_auth.with_refresh.
    import requests as _rq
    from quoteforge.automation import etsy_auth

    class B:
        title = "Personalized Daughter Gift"; description = "desc"
        tags = ["t1"]; materials = ["Premium Matte Paper"]; category = "c"; n = 1

    calls = {"post": 0}
    ok = MagicMock()
    ok.json.return_value = {"listing_id": 777}
    ok.raise_for_status.return_value = None

    def _post(*a, **k):
        calls["post"] += 1
        if calls["post"] == 1:                       # first call: token expired -> 401
            err = _rq.HTTPError("401")
            err.response = MagicMock(status_code=401)
            r = MagicMock()
            r.raise_for_status.side_effect = err
            return r
        return ok                                    # retry after refresh: success

    fake = MagicMock()
    fake.post.side_effect = _post
    monkeypatch.setattr(etsy_auth, "refresh_access_token", lambda: "fresh-token")
    with patch.object(pub, "TEST_MODE", False), \
         patch.object(pub, "ETSY_OAUTH_TOKEN", "tok"), patch.object(pub, "ETSY_SHOP_ID", "9"), \
         patch.object(pub, "ETSY_API_KEY", "k"), patch.object(pub, "ETSY_TAXONOMY_ID", "1"), \
         patch.object(pub, "ETSY_SHIPPING_PROFILE_ID", "2"), \
         patch("quoteforge.db.database.existing_listing_id", return_value=""), \
         patch("quoteforge.db.database.upsert_product", lambda *a, **k: None):
        out = pub.create_draft_listing(B(), 36.99, runner=fake)
    assert out["status"] == "draft_created" and out["listing_id"] == 777
    assert calls["post"] == 2                          # refreshed once and retried


def test_format_text_shows_prereqs_when_missing():
    r = pub.publish_launch_kit(live=True)   # live but no creds -> mock + prereqs
    text = pub.format_publish_text(r)
    assert "Missing prerequisites" in text or r["missing_prereqs"] == []


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_publish_dry_run(capsys):
    rc = admin.main(["publish-listings"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out and "draft" in out.lower()
