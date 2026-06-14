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


def test_titles_and_key_inputs_are_bold(tmp_path):
    """All headings are bold (700) and important labels/inputs carry weight
    so the hierarchy reads instantly."""
    h = _page(tmp_path)
    assert "h1,h2,h3,.serif{font-family:'Cormorant Garamond',Georgia,serif;font-weight:700" in h
    assert ".perso input,.perso textarea" in h and "font-weight:600" in h
    assert ".swrow{font-size" in h          # label rule exists...
    sw = h.split(".perso .swrow{", 1)[1].split("}", 1)[0]
    assert "font-weight:700" in sw          # ...and is bold


def test_brand_serif_font_is_global(tmp_path):
    """The Cormorant Garamond brand font applies to the WHOLE page (body
    root + inheritance), not just headings."""
    h = _page(tmp_path)
    assert "body{font-family:'Cormorant Garamond'" in h


def test_no_native_alerts_in_purchase_flow(tmp_path):
    """Browser alert() popups are banned from the buying flow: an empty
    basket disables Checkout (no alert), and a missing size highlights the
    size picker inline instead of interrupting."""
    h = _page(tmp_path)
    assert "alert('Your basket is empty" not in h
    assert "alert('Please choose a size" not in h
    assert 'id="bpcobtn"' in h
    assert "bpcobtn').disabled" in h or "co.disabled" in h


def test_move_toggle_is_a_clean_segmented_control(tmp_path):
    """The drag toggle reads as one component: bold heading, a full-width
    50/50 segmented control, and a quiet one-line hint - no mid-sentence
    wrapping."""
    h = _page(tmp_path)
    assert "Reposition the wording or photo" in h
    assert 'class="dbhint"' in h
    assert "Select one, then drag it on the preview." in h


def test_editor_controls_have_aria_labels(tmp_path):
    h = _page(tmp_path)
    assert 'aria-label="Move the wording"' in h
    assert 'aria-label="Move the photo"' in h
    assert 'aria-label="See final preview"' in h


def test_synthesized_occasion_cards_offer_frame_choice(tmp_path):
    """Synthesized one-per-occasion designs must offer the SAME frame &
    material choices as real designs (UAT: second order had no frame
    picker). They get the format list with real prices - only the heavy
    per-frame preview thumbnails are skipped."""
    import json as _json
    import re
    h = _page(tmp_path)
    data = _json.loads(re.search(r"const DATA = (\[.*?\]);", h, re.S).group(1))
    syn = [d for d in data if d.get("n") == 0]
    assert syn, "expected synthesized occasion cards in the build"
    for d in syn:
        assert d.get("formats"), f"synthesized card {d.get('occ')} has no formats"
        names = [f["name"] for f in d["formats"]]
        assert any(n.startswith("Framed - ") for n in names)
        assert all(f.get("price") for f in d["formats"])


def test_frame_picker_always_available(tmp_path):
    """Every design is orderable in every frame/material: the page emits a
    global ALL_FORMATS list and the frame picker falls back to it when a card
    has no per-card formats (so a render hiccup can never hide the picker or
    show the stale default price)."""
    h = _page(tmp_path)
    assert "const ALL_FORMATS =" in h
    assert "Poster (unframed)" in h.split("const ALL_FORMATS =", 1)[1].split(";", 1)[0]
    assert "function fmtsFor" in h
    # openM and pickFmt both consume the fallback, not DATA[i].formats raw.
    assert "fmtsFor(i)" in h
    assert "DATA[i].formats[j]" not in h          # raw access removed
    # The picker is shown unconditionally now (fallback guarantees formats).
    assert "fp.style.display='none'" not in h


def test_every_built_card_has_formats(tmp_path):
    """Build-time guarantee: no card ships without formats (the root cause of
    the missing frame picker / $36.99 default)."""
    import json
    import re
    h = _page(tmp_path)
    data = json.loads(re.search(r"const DATA = (\[.*?\]);", h, re.S).group(1))
    for d in data:
        assert d.get("formats"), f"card {d.get('occ')} has no formats"


def test_basket_offers_add_another_design(tmp_path):
    """A filled basket offers a way back to the shop to order MORE items -
    not just Empty/Checkout."""
    h = _page(tmp_path)
    assert 'id="bpmorebtn"' in h
    assert "Add another design" in h
    assert "bpmorebtn" in h.split("function renderBasket", 1)[1] \
        .split("function checkout", 1)[0]      # shown/hidden with contents


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


def test_service_request_form_collects_required_fields(tmp_path):
    """The customer service form collects name, order number, email, optional
    phone, issue type, description, photos, delivery date, and an accuracy
    consent - and shows the individual-review acknowledgement. Order field is
    labelled generically (never names the marketplace)."""
    h = _page(tmp_path)
    for fid in ("sr_name", "sr_order", "sr_email", "sr_phone", "sr_issue",
                "sr_desc", "sr_delivery", "sr_resolution", "sr_consent"):
        assert f'id="{fid}"' in h, f"missing service-request field {fid}"
    for t in ("Damaged item", "Printing defect", "Wrong item received",
              "Missing item", "Lost package", "Other"):
        assert f"<option>{t}</option>" in h
    assert "Order number" in h and "Etsy order" not in h
    assert "reviewed individually" in h          # ack message
    assert "function _srSubmit" in h or "window._srSubmit" in h


def test_storefront_return_policy_is_gelato_accurate(tmp_path):
    """The customer-facing returns/promise section reflects the real policy:
    7-day reporting window, NO need to return (keep it - we replace), free
    replacement for transit damage/defects, reship for wrong-address returns,
    and made-to-order = final sale for approved content. Never names the
    marketplace."""
    h = _page(tmp_path)
    low = h.lower()
    assert "7 days" in low
    assert "no need to return" in low or ("keep" in low and "replace" in low)
    assert "free replacement" in low
    assert "made to order" in low
    # Customer copy must never mention the marketplace by name.
    import re
    assert not re.search(r"\betsy\b", low)


def test_final_confirm_requires_image_quality_text_verification(tmp_path):
    """Step 3 makes the buyer ACTIVELY confirm the photo/quality, the spelling
    & wording, and made-to-order before Complete order enables - the final
    confirmation that protects against 'wrong text/photo' disputes."""
    h = _page(tmp_path)
    assert 'id="vchk_img"' in h          # photo correct + good quality
    assert 'id="vchk_text"' in h         # spelling & wording correct
    assert 'id="vchk_made"' in h         # made to order, prints as shown
    assert "function _confirmChecklistHTML" in h
    assert "function _syncConfirmGate" in h


def test_transit_damage_reassurance_at_confirm(tmp_path):
    """The confirm step reassures the buyer that transit damage is on us (free
    replacement) - the correct, Gelato-backed promise that pairs with the
    customer's own content confirmation."""
    h = _page(tmp_path).lower()
    assert "damaged in transit" in h
    assert "free replacement" in h


def test_contact_and_shipping_collected_before_completion(tmp_path):
    """Name, email, phone, and shipping address are collected on their own
    step BEFORE final approval (previously only email was captured)."""
    h = _page(tmp_path)
    for fid in ("fc_name", "fc_email", "fc_phone", "fc_addr", "fc_city",
                "fc_state", "fc_zip", "fc_country"):
        assert f'id="{fid}"' in h, f"missing contact field {fid}"
    assert "jf_contact" in h          # persisted across refreshes


def test_offline_completion_has_working_email_fallback(tmp_path):
    """With no payment link and no backend, Complete order must still have a
    WORKING channel (prefilled mailto with the order) - never a false
    'saved, watch your inbox' promise."""
    h = _page(tmp_path)
    assert "function _orderMailto" in h
    assert "Email us your order now" in h


def test_single_approval_model_everywhere(tmp_path):
    """One approval story on the whole page: acceptance is final, the proof
    shows what prints (reply fast to fix) - no 'approve before we print'
    gate language anywhere."""
    h = _page(tmp_path)
    assert "approve before we print" not in h
    assert "once approved" not in h
    assert "nothing prints until you approve" not in h
    assert "still send a" not in h          # "we'll still send a free proof"


def test_placeholder_wording_blocked_from_ordering(tmp_path):
    """Default quotes contain literal [Name] tokens - adding to basket with
    one still present asks the buyer to confirm or fix it."""
    h = _page(tmp_path)
    assert "function _placeholderOk" in h
    assert h.count("_placeholderOk(") >= 3   # defined + wired into both adds


def test_exit_popup_never_covers_active_purchase(tmp_path):
    """The 40s exit-intent popup must not interrupt someone mid-purchase
    (editor/proof/basket open, or items in the cart)."""
    h = _page(tmp_path)
    assert "function _overlayOpen" in h
    assert "_overlayOpen()" in h


def test_step2_is_shipping_address_verification(tmp_path):
    h = _page(tmp_path)
    assert "Shipping address verification" in h


def test_no_proof_promises_in_checkout_copy(tmp_path):
    """Acceptance is final - the accepted screen and next-steps no longer
    promise a proof-approval round."""
    h = _page(tmp_path)
    assert "Spot anything wrong on the proof" not in h
    assert "We prepare a <b>free digital proof</b>" not in h


def test_modal_trust_line_removed(tmp_path):
    """The 'Happiness guarantee / Free digital proof' chip line is gone from
    the editor modal (it crowded the title; trust copy lives elsewhere)."""
    h = _page(tmp_path)
    assert 'class="mtrust"' not in h


def test_section_tabs_are_bold_icon_cards(tmp_path):
    """The section chips are big visual cards: an icon over a bold label,
    not faint text pills."""
    h = _page(tmp_path)
    assert h.count('class="eicon"') >= 3      # one icon per section card
    assert h.count('class="elbl"') >= 3
    assert "#esectabs .eicon" in h            # dedicated icon styling


def test_section_tabs_show_completion(tmp_path):
    """Finished sections get a visible done state so the chips read as
    progress, and the styling is prominent (not faint gray pills)."""
    h = _page(tmp_path)
    assert "#esectabs button.done" in h           # completion styling exists
    assert "classList.toggle('done'" in h         # JS marks finished tabs


def test_guidance_engine_one_beacon_to_checkout(tmp_path):
    """A single guidance engine walks the customer through the whole order:
    Design Next -> Photo Next -> pick size -> Review -> Add to basket ->
    Go to checkout. Exactly ONE beacon blinks at a time (infinite, until
    that task completes), and going Back re-lights that step's beacon."""
    h = _page(tmp_path)
    assert "infinite" in h.split(".pulseon{", 1)[1].split("}", 1)[0]
    assert "function guide" in h
    assert "querySelectorAll('.pulseon')" in h     # engine clears, then lights
    for el in ('id="esec1next"', 'id="esec2next"', 'id="mreviewbtn"',
               'id="seefinalbtn"', 'id="maddbtn"'):
        assert el in h, f"beacon target {el} missing"
    engine = h.split("function guide", 1)[1].split("function promptSizeQty", 1)[0]
    assert "pacheckout" in engine                  # final beacon: checkout
    assert "tabglow" in h                          # active tab breathes


def test_description_fills_left_column_and_is_formatted(tmp_path):
    """The product description lives in the left column (the blank space
    under the preview) as a styled card with bold section headers and
    bullets - not a wall of plain text at the bottom right."""
    h = _page(tmp_path)
    mleft = h.split('class="mleft"', 1)[1].split('class="mright"', 1)[0]
    assert 'id="mdesc"' in mleft
    assert "About this piece" in mleft
    assert "function fmtDesc" in h
    assert 'class="dsh"' in h               # section-header styling applied


def test_no_approval_gate_in_listing_descriptions(tmp_path):
    """The HOW IT WORKS steps no longer ask for a reply-to-approve round."""
    h = _page(tmp_path)
    assert "Reply APPROVED" not in h
    assert "for your approval" not in h


def test_wording_box_blinks_until_typing_starts(tmp_path):
    """The first beacon is the wording box itself - it blinks until the
    customer starts typing (or deliberately moves on, which counts as
    keeping the shown quote)."""
    h = _page(tmp_path)
    assert 'id="mwordbox"' in h
    assert "WORD_DONE" in h


def test_wording_input_itself_glows_and_gets_focus(tmp_path):
    """Attention lands ON the input: while the wording beacon is active the
    textarea border glow-pulses, and on desktop the cursor is already in
    the field ready to type."""
    h = _page(tmp_path)
    assert ".wordbox.pulseon textarea" in h
    assert "inputglow" in h
    assert "preventScroll" in h


def test_guidance_resumes_after_going_back(tmp_path):
    """The engine recomputes on every section change (editStep -> guide), so
    hitting Back re-lights that earlier step's beacon until it is finished."""
    h = _page(tmp_path)
    assert "REVIEWED" in h and "ADDED" in h        # completion state tracked
    assert h.count("guide()") >= 4                 # wired into every hook


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


def test_photo_fit_controls_are_a_vibrant_card(tmp_path):
    """The photo-fit controls read as a polished tool card: gold-cream panel,
    bold green title, round tactile nudge buttons, and -/+ cues on the zoom
    slider - matching the wordbox/dragbar design system."""
    h = _page(tmp_path)
    assert "#mphotoctl{" in h                 # dedicated card styling
    assert 'class="pctitle"' in h
    assert h.count('class="zico"') >= 2       # -/+ ends on the zoom slider
    photorow_btn = h.split(".photorow button{", 1)[1].split("}", 1)[0]
    assert "999px" in photorow_btn            # round tactile buttons


def test_design_tips_are_benefit_chips_not_text_walls(tmp_path):
    """The two dense 11px tip paragraphs are replaced by large, scannable
    benefit chips (free personalization / instant preview / emailed proof);
    the move-toggle explainer is gone - the control explains itself."""
    h = _page(tmp_path)
    assert 'class="freebar"' in h
    assert h.count('class="fchk"') >= 2
    assert "Free emailed proof - exactly what prints" not in h
    assert "Use the <b>Move: Text / Photo</b> toggle" not in h


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
