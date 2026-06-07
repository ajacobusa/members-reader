"""Tests for the Ask Ange assistant (deterministic + grounded)."""


def test_answer_matches_frame_question():
    from quoteforge.ai.ange import answer
    r = answer("Is the frame included?")
    assert r["matched"] and "WITHOUT a frame" in r["answer"]


def test_answer_shipping_and_photo():
    from quoteforge.ai.ange import answer
    assert "proof" in answer("how long does shipping take").get("answer", "").lower() \
        or "ship" in answer("how long does shipping take")["answer"].lower()
    assert answer("can I upload my own photo")["matched"]


def test_unknown_defers_to_human():
    from quoteforge.ai.ange import answer
    r = answer("where is my order 12345 refund")
    # refund/order-specific should still match the returns KB OR fall back to human
    assert "team" in r["answer"].lower() or "make it right" in r["answer"].lower()


def test_ask_ange_uses_fallback_in_test_mode(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.ai.ange import ask_ange
    r = ask_ange("Do you do bulk corporate orders?")
    assert "wholesale" in r["answer"].lower()


def test_widget_embedded_in_site(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=False)
    h = out.read_text(encoding="utf-8")
    assert "Ask Ange" in h and "ANGE_KB" in h and "function angeSend" in h


def test_ask_command_registered():
    from quoteforge import admin
    assert "ask" in admin.COMMANDS
