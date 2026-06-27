"""Production-readiness hardening B (from the 18-point audit):
- #9  AI personalization safety: profanity filter, min-length/empty drop, API fallback
- #15 1099-K reconciliation (gross processed incl. refunded)
- #17 international-address happy-path + storefront personalization length caps
All network/IO mocked or tmp.
"""
import sqlite3

from PIL import Image


# ---------------------------------------------------------------- #9 AI safety
def test_moderation_filters_profanity_and_short():
    from quoteforge.quotes.moderation import is_clean, acceptable, filter_variations
    assert is_clean("Be brave and kind always") is True
    assert is_clean("this is shit") is False
    assert acceptable("too short") is False                  # < 15 chars
    assert acceptable("A heartfelt message of love") is True
    kept = filter_variations(
        ["A heartfelt message of hope and love", "tiny", "what the fuck"])
    assert kept == ["A heartfelt message of hope and love"]


def test_clean_lines_drops_profane_quotes():
    from quoteforge.quotes.generator import _clean_lines
    out = _clean_lines("Be brave\nThis is shit\nStay strong always", 5)
    assert "Be brave" in out and "Stay strong always" in out
    assert not any("shit" in q for q in out)


def test_personal_message_falls_back_on_api_error(monkeypatch):
    # #9 REGRESSION: a live API error must degrade to the mock, never hard-crash.
    import quoteforge.quotes.generator as gen
    monkeypatch.setattr(gen, "_client", lambda: object())

    def _boom(*a, **k):
        raise RuntimeError("429 rate limit")
    monkeypatch.setattr(gen, "_invoke", _boom)
    res = gen.generate_personal_message(
        "friend", "Alice", "Bob", "Birthday", "a memory", "calm",
        "Personal Letter", count=3, force_real=True)
    assert res and all(isinstance(v, str) and v.strip() for v in res)


def test_personal_message_all_filtered_falls_back(monkeypatch):
    # #9 REGRESSION: if every variation is profane/too-short, fall back to the safe
    # mock instead of handing the customer unusable text.
    import quoteforge.quotes.generator as gen
    monkeypatch.setattr(gen, "_client", lambda: object())

    class _M:
        content = [type("X", (), {"text": "fuck\n---\nshit\n---\ntiny"})()]
    monkeypatch.setattr(gen, "_invoke", lambda *a, **k: _M())
    res = gen.generate_personal_message(
        "friend", "Alice", "Bob", "Birthday", "mem", "calm",
        "Custom Quote", count=2, force_real=True)
    assert res and all("fuck" not in v and "shit" not in v for v in res)


# -------------------------------------------------------------- #15 1099-K recon
def test_year_gross_1099k_includes_refunded(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    rows = [("O1", "delivered", 50.0, "2026-03-01T00:00:00"),
            ("O2", "refunded", 30.0, "2026-04-01T00:00:00"),
            ("O3", "received", 99.0, "2026-05-01T00:00:00"),    # not processed yet
            ("O4", "delivered", 20.0, "2025-12-31T00:00:00")]   # prior year
    for oid, st, sp, ca in rows:
        conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,status,"
                     "sale_price,created_at) VALUES (?,?,?,?,?,?)",
                     (oid, "R", "B", st, sp, ca))
    conn.commit()
    conn.close()
    from quoteforge.etsy.financials import year_gross_1099k
    r = year_gross_1099k(2026)
    assert r["transactions"] == 2          # delivered + refunded (gross was processed)
    assert r["gross_1099k"] == 80.0        # 50 + 30; excludes received + prior year


# ------------------------------------------------------------ #17 scenario gaps
def test_international_address_routes_once(tmp_path, monkeypatch):
    # #17 REGRESSION: a complete non-US address (GB, no state) is fulfillable.
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(cfg, "GELATO_FULFILLMENT_MODE", "quoteforge")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,"
                 "gelato_product_uid) VALUES (?,?,?,?)", ("O1", "R", "B", "uid-1"))
    conn.commit()
    conn.close()
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(ga, "create_gelato_order", lambda *a, **k: {"id": "GLT-9"})
    from quoteforge.fulfillment.router import route_order
    res = route_order(
        {"order_id": "O1", "gelato_product_uid": "uid-1"},
        recipient={"name": "Oliver", "addressLine1": "10 Downing St",
                   "city": "London", "postCode": "SW1A 2AA", "country": "GB"},
        artwork_url="http://x/a.png")
    assert res["status"] == "submitted" and res["id"] == "GLT-9"


def _page(tmp_path) -> str:
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    return out.read_text(encoding="utf-8")


def test_personalization_length_is_capped(tmp_path):
    # #17 REGRESSION: storefront caps personalization so an unbounded string can't
    # reach intake/render (message 250 chars, name slot 40).
    html = _page(tmp_path)
    assert 'id="mtext" maxlength="250"' in html
    assert 'maxlength="40"' in html
