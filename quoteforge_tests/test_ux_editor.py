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


def test_editor_is_sectioned_with_next_buttons(tmp_path):
    """The customize panel is a one-section-at-a-time wizard: 1 Design ->
    2 Photo -> 3 Frame & size + add, each finished with a Next button -
    no scrolling hunt for the photo upload."""
    h = _page(tmp_path)
    for sec in ("esec1", "esec2", "esec3"):
        assert f'id="{sec}"' in h, f"missing editor section {sec}"
    assert "function editStep" in h
    assert "Next: add your photo" in h
    assert "Next: frame &amp; size" in h or "Next: frame & size" in h
    assert 'id="esectabs"' in h           # clickable section chips


def test_photo_upload_is_its_own_section(tmp_path):
    """The photo upload lives in section 2, not buried at the bottom of the
    order box."""
    h = _page(tmp_path)
    sec2 = h.split('id="esec2"', 1)[1].split('id="esec3"', 1)[0]
    assert 'id="mupload"' in sec2


def test_checkout_has_no_dead_end_without_shop_url(tmp_path):
    """When the shop isn't live yet (preview/UAT), accepting the basket
    must show a clear numbered 'What happens next' path + email capture -
    never a bare 'Done' that strands the customer."""
    h = _page(tmp_path)
    assert "What happens next" in h
    assert "function saveProofEmail" in h


def test_final_review_is_a_three_step_wizard(tmp_path):
    """The accept screen is broken into sections: review basket -> your
    details -> confirm & complete, each with its own Next action."""
    h = _page(tmp_path)
    assert "function finalStep" in h
    assert "Next: your details" in h
    assert "Next: confirm" in h
    assert "Complete order" in h
    assert "Step 1 of 3" in h and "Step 3 of 3" in h


def test_contact_and_shipping_collected_before_completion(tmp_path):
    """Name, email, phone, and shipping address are collected on their own
    step BEFORE final approval (previously only email was captured)."""
    h = _page(tmp_path)
    for fid in ("fc_name", "fc_email", "fc_phone", "fc_addr", "fc_city",
                "fc_state", "fc_zip", "fc_country"):
        assert f'id="{fid}"' in h, f"missing contact field {fid}"
    assert "jf_contact" in h          # persisted across refreshes


def test_step2_is_shipping_address_verification(tmp_path):
    h = _page(tmp_path)
    assert "Shipping address verification" in h


def test_no_proof_promises_in_checkout_copy(tmp_path):
    """Acceptance is final - the accepted screen and next-steps no longer
    promise a proof email round."""
    h = _page(tmp_path)
    assert "see exactly what prints" not in h
    assert "Spot anything wrong on the proof" not in h
    assert "We prepare a <b>free digital proof</b>" not in h


def test_modal_trust_line_removed(tmp_path):
    """The 'Happiness guarantee / Free digital proof' chip line is gone from
    the editor modal (it crowded the title; trust copy lives elsewhere)."""
    h = _page(tmp_path)
    assert 'class="mtrust"' not in h


def test_section_tabs_show_completion(tmp_path):
    """Finished sections get a visible done state so the chips read as
    progress, and the styling is prominent (not faint gray pills)."""
    h = _page(tmp_path)
    assert "#esectabs button.done" in h           # completion styling exists
    assert "classList.toggle('done'" in h         # JS marks finished tabs


def test_customer_is_moved_forward_automatically(tmp_path):
    """No waiting around: arriving at Frame & size auto-prompts the size &
    quantity pickers, and a successful photo upload turns the Next button
    into a pulsing 'Photo added - Next' call to action."""
    h = _page(tmp_path)
    assert 'id="sizeprompt"' in h
    assert "function promptSizeQty" in h
    assert h.count("promptSizeQty(") >= 2         # wired, not just defined
    assert 'id="esec2next"' in h
    assert "Photo added" in h
    assert "pulseanim" in h


def test_wording_field_is_prominent(tmp_path):
    """The wording input is the heart of personalization - it sits in a
    highlighted box with a bold label, not a thin gray line."""
    h = _page(tmp_path)
    assert 'class="wordbox"' in h
    assert "Your wording - make it yours" in h
    assert ".wordbox" in h            # dedicated styling exists


def test_ship_to_heading_is_plain(tmp_path):
    """The step-3 recap card is headed 'Ship to' (not 'Send proof & ship to')."""
    h = _page(tmp_path)
    assert "<b>Ship to</b>" in h
    assert "Send proof &amp; ship to" not in h


def test_same_page_payment_when_payment_link_configured(tmp_path, monkeypatch):
    """With PAYMENT_LINK_URL set, completing the order pays NOW in the same
    flow (hosted secure checkout opens immediately) - no 'we'll email you a
    payment link later'."""
    monkeypatch.setattr("quoteforge.config.PAYMENT_LINK_URL",
                        "https://buy.stripe.com/test_abc", raising=False)
    h = _page(tmp_path)
    assert 'const PAY_LINK = "https://buy.stripe.com/test_abc"' in h
    assert "Pay now" in h


def test_acceptance_is_final_approval_with_start_over(tmp_path):
    """The accepted screen says plainly that acceptance IS the final
    approval, and offers a Start over control to go back and change
    anything before production."""
    h = _page(tmp_path)
    assert "final approval" in h
    assert "function restartCheckout" in h
    assert "Start over" in h


def test_no_customer_facing_etsy_in_page_copy(tmp_path):
    """The marketplace behind the payment link is an implementation detail -
    customer copy says 'secure checkout / payment link', never 'Etsy'."""
    h = _page(tmp_path)
    assert "Etsy's secure checkout" not in h
    assert "secure Etsy" not in h
    assert "Etsy checkout" not in h
    assert "live Etsy page" not in h
