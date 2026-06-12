"""UX requirements for the personalization editor (generated storefront page):
progress stepper, client-side upload size cap, duplicate-photo notice,
loading spinner, and screen-reader affordances (aria-live + labels)."""
from pathlib import Path

from PIL import Image


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


def test_editor_has_progress_stepper(tmp_path):
    """Customers always know where they are: Customize -> Review -> Approve
    -> Checkout, with the current step marked for assistive tech."""
    h = _page(tmp_path)
    assert 'id="mstepper"' in h
    for label in ("Customize", "Review", "Approve", "Checkout"):
        assert label in h
    assert "function setStep" in h
    assert 'aria-current' in h


def test_upload_enforces_client_side_size_cap(tmp_path):
    """Oversized files are caught instantly in the browser with a friendly
    message (the server enforces the same 25 MB cap)."""
    h = _page(tmp_path)
    assert "MAX_UPLOAD_MB" in h
    assert "too large" in h.lower()


def test_duplicate_photo_notice(tmp_path):
    """Re-using the same photo in another basket item gets a gentle heads-up
    (catches accidental duplicate uploads without blocking intentional ones)."""
    h = _page(tmp_path)
    assert "function dupPhotoNote" in h
    assert "same photo" in h.lower()


def test_ai_check_shows_animated_spinner(tmp_path):
    h = _page(tmp_path)
    assert ".spin" in h and "@keyframes" in h
    assert 'class="spin"' in h or "spin'" in h


def test_status_regions_are_aria_live(tmp_path):
    """Upload errors, AI feedback, and proof status are announced to screen
    readers the moment they change."""
    h = _page(tmp_path)
    assert h.count('aria-live="polite"') >= 3


def test_editor_controls_have_aria_labels(tmp_path):
    h = _page(tmp_path)
    assert 'aria-label="Move the wording"' in h
    assert 'aria-label="Move the photo"' in h
    assert 'aria-label="See final preview"' in h


def test_basket_explains_how_payment_works(tmp_path):
    """Customers must never wonder 'where do I put my credit card?' - the
    basket says payment is completed securely on Etsy, with the methods."""
    h = _page(tmp_path)
    assert "never enter card details" in h.lower()
    assert "PayPal" in h
    assert 'id="paynote"' in h


def test_checkout_has_no_dead_end_without_shop_url(tmp_path):
    """When the Etsy shop isn't live yet (preview/UAT), accepting the basket
    must show a clear numbered 'What happens next' path + email capture -
    never a bare 'Done' that strands the customer."""
    h = _page(tmp_path)
    assert "What happens next" in h
    assert "function saveProofEmail" in h
