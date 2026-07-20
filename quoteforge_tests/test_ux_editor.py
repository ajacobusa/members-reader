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


def test_editor_shows_no_hard_delivery_date(tmp_path):
    # REGRESSION: a made-to-order delivery date is an over-promise we can't control
    # (production + carrier variance), so the editor must NOT show "arrives by <date>".
    h = _page(tmp_path)
    assert "arrives by" not in h
    assert "_arriveBy" not in h
    assert "typically ships in a few business days" in h   # soft estimate, no hard date


def test_express_option_off_by_default(tmp_path):
    # OFF by default: the gate const is false, so the express line never renders live
    # (the JS for it ships in source, but EXPRESS_ENABLED=false suppresses it), and
    # the shop is unchanged until the owner sets EXPRESS_SHIPPING_ENABLED.
    h = _page(tmp_path)
    assert "const EXPRESS_ENABLED = false" in h


def test_express_option_renders_when_enabled(tmp_path, monkeypatch):
    # When the owner enables it, the editor surfaces the express upgrade line + price.
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "EXPRESS_SHIPPING_ENABLED", True)
    h = _page(tmp_path)
    assert "const EXPRESS_ENABLED = true" in h
    assert "Express delivery</b> at checkout" in h
    assert "9.95" in h


def test_mug_prints_full_360_wrap_band(tmp_path):
    # REGRESSION: a mug prints the full 360-degree WRAP, so its print area must be a
    # WIDE band (_placeMugBound), not the near-square apparel front panel.
    js = _page(tmp_path)
    assert "_placeMugBound" in js                       # dedicated wide wrap bound
    assert "const b=_placeMugBound(W,H)" in js          # the mug uses it, not _placeBoundMock
    assert "W*0.78*BOX.s" in js                         # wide band (vs the 0.42 front panel)


def test_mug_spin_shows_full_wrap_front_and_back(tmp_path):
    # REGRESSION: a WRAP mug spins the design ~300 degrees (front AND back). The arc is
    # now per-mug (#mugwrap): 5.3 for a wrap mug, 1.9 for a single-panel mug that only
    # prints one panel - so the proof matches what prints. Full-wrap behaviour preserved.
    js = _page(tmp_path)
    assert "arc:(handle?(_mw?5.3:1.9):5.6)" in js       # wrap mug 5.3; single-panel 1.9
    assert "rot+=0.010" in js                           # full 360 auto-spin (wrap mugs)


def test_proof_reviews_every_designed_area(tmp_path):
    # REGRESSION: the buyer must SEE every area they designed (front/back/sleeves) before
    # the single affirmative approval - the proof flip cycles ALL designed areas, and the
    # consent line covers exactly what is shown. This is the no-return policy's record.
    js = _page(tmp_path)
    assert "function _designedAreas()" in js
    assert "views[(i+1)%views.length]" in js                    # flips between front (with sleeves) & back
    assert 'id="proofAreas"' in js                              # lists what they designed
    # the front view shows front + sleeves, so every designed area is still reviewed
    assert "You designed: <b>" in js
    assert "I approve this print exactly as shown and authorize it to proceed" in js


def test_spin_is_a_start_stop_toggle(tmp_path):
    # REGRESSION: ONE button toggles the 360 spin - play it, then FREEZE it at any
    # angle to review (and back). So the buyer controls the spin and gets clarity.
    js = _page(tmp_path)
    assert 'onclick="toggleSpin()"' in js               # the button drives the toggle
    assert "function toggleSpin()" in js
    assert "if(!drag && _SPIN_PLAY)" in js              # auto-spin gated on the toggle (freezes)
    assert "Stop spinning" in js                        # the playing-state label


def test_wording_clamped_inside_print_area(tmp_path):
    # REGRESSION: the draggable wording must be clamped by its OWN block half-size so
    # it can never be dragged outside the dashed print area (which would print
    # clipped). The TPOS clamp alone bounds the CENTRE, not the block's edges.
    js = _page(tmp_path)                               # editor JS is inline in the page
    assert "_ehw" in js and "_ehh" in js               # rotation-aware block half-size
    assert "Math.max(ax, x+_ehw)" in js                # anchor bounded by the block edge
    assert "Math.max(ay, y+_ehh)" in js


def test_calendar_photos_queue_until_email(tmp_path):
    # REGRESSION: a buyer who designs a calendar BEFORE entering their email lost
    # every month photo - the old _calUpload returned early with no email, so the
    # bytes were never uploaded and the order got empty URLs. They must now queue and
    # flush the moment the email is known (at checkout / the proof-email step).
    h = _page(tmp_path)
    assert "let CAL_QUEUE=" in h
    assert "CAL_QUEUE.push({i:i,f:f})" in h                 # queued while no email
    assert "function _flushCalQueue()" in h
    assert h.count("_flushCalQueue==='function'") >= 2      # wired at both email points


def test_confirm_step_shows_proof_thumbnail(tmp_path):
    """REGRESSION: the buyer authorizes 'I approve this print exactly as shown', so
    the actual artwork must be SHOWN at review + confirm - not just a text line. A
    proof thumbnail is captured at add-to-basket and rendered per row in the visual
    basket used by both the review (step 1) and confirm (step 3) checkout steps."""
    h = _page(tmp_path)
    # The thumbnail is captured when the item is added to the basket...
    assert "function _proofThumb()" in h
    assert "thumb:_proofThumb()" in h
    # ...and rendered as an <img> in the visual basket used at review + confirm.
    assert "function _basketVisualHTML()" in h
    assert "_basketVisualHTML()" in h
    # The confirm step no longer uses the text-only summary at those points.
    assert "_basketSummary().replace" not in h
    # The affirmative authorization still gates checkout.
    assert "I approve this print exactly as shown" in h


def test_order_card_becomes_active_next_step(tmp_path):
    """After frame/design selection, the whole 'Build your order' card lights up
    as the active next step (gold ring + lift + 'Next step' badge) and is
    scrolled into view, so the buyer can't miss what to do next."""
    h = _page(tmp_path)
    assert ".orderbox.stepnow" in h          # active-step card styling
    assert "stepbadge" in h and "Next step" in h
    assert "classList.add('stepnow')" in h   # wired into the guide() lifecycle
    assert "scrollIntoView" in h             # brought into view on activation


def test_size_qty_dropdowns_pulse_until_selected(tmp_path):
    """The Size/Qty dropdowns glow-pulse to grab attention until the buyer
    picks a size, then the pulse clears (no forever-blink). Reduced-motion
    users get a static highlight instead of animation."""
    h = _page(tmp_path)
    assert "@keyframes selattn" in h
    assert ".orow select.attn" in h
    assert ".sizeprompt.attn" in h           # the prompt box pulses too
    # The prompt reuses the .pulseon ctapulse ring + an animated border-glow.
    assert "ctapulse" in h and "@keyframes promptborder" in h
    assert "prefers-reduced-motion" in h
    # Wired into the guidance lifecycle: added when no size, cleared otherwise.
    assert "s.classList.add('attn')" in h
    assert "'sizeprompt'" in h and "classList.remove('attn')" in h


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
    # Headings/titles stay in the Cormorant serif and are bold (700).
    assert "font-family:'Cormorant Garamond',Georgia,serif" in h
    assert "h1,h2,h3,.serif{font-weight:700" in h
    assert ".perso input,.perso textarea" in h and "font-weight:600" in h
    assert ".swrow{font-size" in h          # label rule exists...
    sw = h.split(".perso .swrow{", 1)[1].split("}", 1)[0]
    assert "font-weight:700" in sw          # ...and is bold


def test_readable_sans_body_with_serif_headings(tmp_path):
    """Readability pairing (REGRESSION): body + UI text uses a legible sans
    (Montserrat); the Cormorant Garamond serif is reserved for headings/titles
    - the display serif was hard to read as body copy."""
    h = _page(tmp_path)
    assert "body{font-family:'Montserrat'" in h            # readable sans body
    assert "h1,h2,h3,h4,.serif" in h                        # serif heading rule
    assert "font-family:'Cormorant Garamond',Georgia,serif" in h


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
    """The drag toggle reads as one component: bold heading, a segmented control
    (Wording / Photo / Reset), and a quiet one-line how-to hint."""
    h = _page(tmp_path)
    assert "Reposition the wording or photo" in h
    assert 'class="dbhint"' in h
    # the hint now tells the buyer HOW to move each element (per-element drag)
    assert "Drag any word or the photo on the preview to move it" in h
    assert 'aria-label="Reset placement"' in h


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
    assert 'id="esectabs"' in h           # step progress tracker (non-clickable)


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
    # File pickers + form are styled (bigger, branded), not bare native controls.
    assert "::file-selector-button" in h and ".srform" in h


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


def test_checkout_has_trust_strip(tmp_path):
    """The address + confirm checkout steps carry a trust strip (security +
    free-proof + payment methods) - the highest-anxiety part of the funnel."""
    h = _page(tmp_path)
    assert "trustband" in h                                  # CSS + element
    assert "_trustStripHTML" in h                            # helper defined
    assert "_trustStripHTML()+_contactFormHTML()" in h       # wired into step 2
    assert "card details never touch this site" in h
    assert "Free proof before we print" in h
    assert "Apple" in h and "Google" in h                    # payment methods


def test_mobile_tap_targets_are_comfortable(tmp_path):
    """Dense controls meet ~44px touch targets on phones."""
    h = _page(tmp_path)
    assert "#mfchips .fchip{min-height:44px}" in h
    assert "#mphotoctl button{min-width:44px;min-height:44px" in h


def test_frame_pills_have_colour_swatch(tmp_path):
    """Each frame/material pill shows a colour-cue dot (visual, keeps the pill
    layout) - NOT the reverted heavy image tiles."""
    h = _page(tmp_path)
    assert "function swatchDot(" in h
    assert "swatchDot(f.name)" in h        # wired into the pill template
    assert "#mfchips .fdot" in h           # dot styling


def test_editor_pick_badge_is_curated_not_fabricated(tmp_path):
    """An honest, owner-curated 'Editor's pick' ribbon (no fabricated sales)."""
    h = _page(tmp_path)
    assert "EDITOR_PICKS" in h             # owner-editable curation list
    assert ".epick" in h                   # ribbon styling
    assert "Editor&#39;s pick" in h        # the ribbon label


def test_final_approval_authorizes_production(tmp_path):
    """The final approval step must be an AFFIRMATIVE authorization: the buyer
    approves the print exactly as shown AND authorizes it to proceed to
    production (the record the made-to-order, all-sales-final policy rests on),
    gated behind the three confirmation checkboxes."""
    h = _page(tmp_path)
    assert "Final approval" in h
    assert "approve this print exactly as shown" in h
    assert "authorize it to proceed to production" in h
    for cid in ("vchk_img", "vchk_text", "vchk_made"):
        assert f'id="{cid}"' in h          # all three gates still required


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


def test_section_progress_is_a_nonclickable_tracker(tmp_path):
    """REGRESSION (#173): the top step row is a NON-clickable progress tracker
    (numbered dots 1-2-3 with labels), not a second set of clickable tabs. The
    big Next/Back buttons are the only navigation - the dual nav felt redundant."""
    h = _page(tmp_path)
    assert 'id="esectabs"' in h and 'role="list"' in h
    assert h.count('class="estep') >= 3           # three progress steps (divs)
    assert h.count('class="edot"') >= 3           # numbered dots
    assert h.count('class="elbl"') >= 3           # step labels
    # the tracker itself carries no click handler (Next/Back navigate instead)
    tracker = h.split('id="esectabs"', 1)[1].split('id="esec1"', 1)[0]
    assert "onclick" not in tracker, "progress steps must not be clickable"
    assert "function editStep" in h               # Next/Back still call editStep


def test_section_tabs_show_completion(tmp_path):
    """Finished steps get a visible done state so the tracker reads as progress."""
    h = _page(tmp_path)
    assert "#esectabs .estep.done" in h           # completion styling exists
    assert "classList.toggle('done'" in h         # JS marks finished steps


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
    # The card title is now the collapsible section's <summary> header (#170).
    assert "Resize &amp; place your photo" in h
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


def test_layout_gallery_has_descriptions_and_product_filtering(tmp_path):
    # UX: each template carries a plain-English description, and apparel-only styles
    # (Back Print / Left-Chest / Streetwear) are filtered out for non-apparel products.
    h = _page(tmp_path)
    assert "const LAYOUT_META" in h
    assert "Name curved around a round photo" in h        # a real description
    assert "only styles that suit this product" in h       # the per-product filter
    assert "f:['apparel']" in h                            # apparel-only tagging
    assert ".layoutthumb small" in h                        # description caption style


def test_edit_controls_sit_above_the_layout_picker(tmp_path):
    # REGRESSION (#169): the frequently-used manipulation controls (Move & resize,
    # Reposition the wording/photo, photo controls) must appear BEFORE the one-time
    # layout-picker grid in the editor's left column. Previously the big layout grid
    # sat between the placement tabs and the controls, burying them ~2 screens below
    # the fold on mobile ("customer won't even know it exists"). Order must be:
    # placement tabs -> Move & resize -> Wording/Photo -> layout grid.
    h = _page(tmp_path)
    i_place = h.find('id="mplacement"')
    i_frame = h.find('id="mframebar"')
    i_wording = h.find("Reposition the wording or photo")
    i_layout = h.find('id="mlayoutbar"')
    assert i_place != -1 and i_frame != -1 and i_wording != -1 and i_layout != -1
    assert i_place < i_frame, "Move & resize must come after the placement tabs"
    assert i_frame < i_layout, "Move & resize must come BEFORE the layout picker grid"
    assert i_wording < i_layout, "Wording/Photo controls must come BEFORE the layout picker grid"


def test_control_panels_are_collapsible_sections(tmp_path):
    # REGRESSION (#170): each control panel is a native <details>/<summary> accordion
    # so all section headers stay visible (compact) while keeping 100% functionality.
    # Move & resize is expanded by default; the big layout-picker grid is collapsed so
    # it can't bury the controls again. Every panel keeps its id (JS still shows/hides
    # per product via display:none, independent of the open/closed state).
    h = _page(tmp_path)
    # The move/resize panel is a <details ... open> (expanded by default).
    assert '<details class="dragbar mcsec" id="mframebar"' in h
    assert 'id="mframebar" style="display:none" open>' in h
    # The layout picker is a <details> WITHOUT `open` -> collapsed by default.
    lay = h.split('id="mlayoutbar"', 1)[1].split(">", 1)[0]
    assert "open" not in lay, "layout picker must be collapsed by default"
    # Each collapsible carries a <summary> header + the accordion marker styling.
    assert ".mcsec>summary" in h
    # Each section has a <summary> header ending in its label (an emoji prefixes it).
    for label in ("Move &amp; resize your design", "Reposition the wording or photo",
                  "Resize &amp; place your photo", "Pick a layout"):
        assert f"{label}</summary>" in h, label
    # Functionality preserved: the same handlers are still wired inside the sections.
    for handler in ("setFrameSize(", "moveFrame(", "resetFrame(", "setDragMode(",
                    "setPhotoZoom(", "autoCenterPhoto(", "toggleTextOrientation("):
        assert handler in h, handler


def test_photo_and_design_panels_are_mutually_exclusive(tmp_path):
    # REGRESSION (#171): the whole-design "Move & resize" card (mframebar) and the
    # "Resize & place your photo" card (mphotoctl) used to show at the same time once a
    # photo was uploaded - two look-alike Size/Move/Reset cards = a "duplicate". Now a
    # single contextual panel shows at a time, driven by the Wording|Photo selector via
    # _syncCtlPanels: photo panel in Photo mode, whole-design panel (PRINT products)
    # otherwise. mframebar is the sleeve/whole-design positioner, so it is hidden in
    # Photo mode - never removed (sleeves still need it).
    h = _page(tmp_path)
    assert "function _syncCtlPanels(" in h
    # setDragMode swaps the panels
    after = h.split("function setDragMode(m)", 1)[1][:220]
    assert "_syncCtlPanels()" in after, "setDragMode must re-sync the contextual panels"
    # the helper gates BOTH panels on photo mode (mutually exclusive)
    assert "DRAGMODE==='photo'" in h
    assert "getElementById('mphotoctl')" in h and "getElementById('mframebar')" in h
    # both photo-specific and whole-design handlers remain wired (nothing lost)
    for handler in ("setPhotoZoom(", "nudgePhoto(", "autoCenterPhoto(", "removeBg(",
                    "setFrameSize(", "moveFrame(", "resetFrame("):
        assert handler in h, handler


def test_next_button_sits_right_under_the_wording(tmp_path):
    # REGRESSION (#174 + owner request 2026-07-18): the "Next: add your photo" button
    # sits RIGHT under the wording box; the Step-1 text styling (font, size, move,
    # rotate) lives BELOW the Next button and is ALWAYS visible - a plain card, not a
    # collapsed <details>, and its header carries no "(optional)" hedge.
    h = _page(tmp_path)
    assert '<div class="mcsec mtextfx">' in h           # always-visible styling card
    assert '<details class="mcsec mtextfx"' not in h    # never a collapsible again
    assert "Style your text" in h                       # its header label
    hdr = h.split("Style your text", 1)[1].split("</div>", 1)[0]
    assert "optional" not in hdr.lower(), "styling header must not say (optional)"
    # ORDER: wording box -> Next button -> styling card (font/rotate inside it)
    i_word = h.find('id="mwordbox"')
    i_next = h.find('id="esec1next"')
    i_fx = h.find('class="mcsec mtextfx"')
    i_fonts = h.find('id="mfonts"')
    i_rot = h.find('class="rotrow"')
    assert i_word < i_next < i_fx, "Next must sit right under the wording, above styling"
    assert i_fx < i_fonts and i_fx < i_rot, "styling controls live inside the card"
    # nothing lost - the styling handlers are still wired
    for handler in ("setTextSize(", "setTextRot(", "nudgeText(", "setRot("):
        assert handler in h, handler


def test_inspect_mode_pan_zoom_on_live_preview(tmp_path):
    # REGRESSION (owner request 2026-07-19): the LIVE editor preview has an Inspect
    # (pan & zoom) mode so a customer can examine their design in detail - the same
    # gesture language as the final-proof viewer (scroll/pinch to zoom, drag to look
    # around, Reset). While Inspect is ON, the design-editing gestures are PAUSED via
    # guards at the top of _startDrag/_moveDrag, so zooming can never nudge the
    # design; toggling it off resets the view and restores editing exactly.
    h = _page(tmp_path)
    # the transformed view layer wraps BOTH the garment photo and the canvas
    i_layer = h.find('id="mzoomlayer"')
    i_garment = h.find('id="mgarment"')
    i_canvas = h.find('id="mcanvas"')
    assert -1 < i_layer < i_garment < i_canvas, "mzoomlayer must wrap garment + canvas"
    # the bottom control bar: [-] [Zoom toggle] [+], overlaid at the FOOT of the
    # picture (owner request 2026-07-19), plus the hint's Reset
    assert 'class="inspectbar"' in h and "bottom:8px" in h
    i_out, i_btn, i_in = (h.find('id="vzout"'), h.find('id="inspectbtn"'),
                          h.find('id="vzin"'))
    assert -1 < i_out < i_btn < i_in, "bar order must be - / Zoom / +"
    assert 'onclick="vzStep(-1)"' in h and 'onclick="vzStep(1)"' in h
    assert 'toggleInspect()' in h
    assert 'id="inspecthint"' in h and 'vzReset()' in h
    # + auto-enters Inspect; - auto-exits at 100% (editing never left paused)
    assert "if(d>0 && !INSPECT) toggleInspect();" in h
    assert "if(d<0 && INSPECT && VZ<=1) toggleInspect();" in h
    # vertical pan slider (owner request 2026-07-19): slide to move up/down the
    # picture while zoomed; hidden at 100%; two-way synced with drag-panning
    assert 'id="vpanslider"' in h and 'oninput="vzPan(this.value)"' in h
    assert "function vzPan" in h
    assert "(INSPECT&&VZ>1)?'block':'none'" in h   # only visible while zoomed
    assert "Math.round(-(VPY/lim)*100)" in h       # drag-pan keeps the slider in sync
    # editing gestures are paused while inspecting (the anti-nudge guards)
    assert "if(INSPECT){ _vDown(ev); return; }" in h
    assert "if(INSPECT){ _vMove(ev); return; }" in h
    # zoom inputs: wheel + double-click + pinch (reuses the proof viewer's _pinchDist)
    assert "addEventListener('wheel',_vWheel" in h
    assert "addEventListener('dblclick',_vDbl" in h
    assert "_VPINCH=_pinchDist(ev)" in h
    # zoom is clamped and pan can't leave the frame (proof-viewer pattern)
    assert "Math.max(1,Math.min(4,z))" in h
    assert "(VZ-1)*50" in h


def test_flip_review_watchers_cannot_leak_or_starve(tmp_path):
    # REGRESSION (#stale-flip, owner report 2026-07-19): with the flip review open,
    # changing the colour or the front/back area stopped re-rendering the overlay
    # (Navy picked, the old Red photo still shown). Root cause: every overlay opener
    # REPLACES _3d synchronously (false -> true in one call), so a prior watcher
    # never observed the off state and leaked; being registered earlier it consumed
    # _SPIN_DIRTY first and STARVED the live overlay's watcher. Every watcher must
    # therefore hold an IDENTITY reference to its own _3d and die when replaced -
    # and the static-image watchers poll via setInterval (rAF is throttled when the
    # view is backgrounded/obscured, freezing updates entirely).
    h = _page(tmp_path)
    # no watcher may guard on the SHARED _3d.on alone (the leak pattern)
    assert "if(!_3d.on) return;" not in h, "bare _3d.on watcher guard leaks on reopen"
    # every loop/watcher checks identity: its own captured object vs the current _3d
    assert h.count("_3d!==_my") >= 2       # flip review + flat photo interval watchers
    assert "_3d!==_my3" in h               # mug canvas spin loop
    assert "_3d!==_myg" in h               # WebGL spin loop
    # the overlay watchers are interval-based (rAF-throttle immune) and self-clear
    assert h.count("clearInterval(_ti)") >= 2
    # the dirty flag remains the signal drawArt raises for live re-render
    assert "_SPIN_DIRTY=true" in h and "_SPIN_DIRTY){" in h


def test_trust_badges_sit_above_the_preview_not_on_it(tmp_path):
    # REGRESSION (owner report 2026-07-19): the "Made to order" / "You approve
    # before print" pills were absolutely overlaid on the preview's top-left - on
    # wall art the customer's own photo fills the whole frame, making the pills
    # unreadable AND covering the picture. They must render as a normal row ABOVE
    # the preview wrap, never positioned over the artwork.
    h = _page(tmp_path)
    i_badges = h.find('class="pdpbadges"')
    i_wrap = h.find('class="mcanvaswrap"')
    assert -1 < i_badges < i_wrap, "badge row must come BEFORE the preview wrap"
    seg = h.split('class="pdpbadges"', 1)[1]
    assert seg.split('class="mcanvaswrap"', 1)[0].count("pdpbadge") >= 2
    css = h.split(".pdpbadges{", 1)[1].split("}", 1)[0]
    assert "position:absolute" not in css, "badges may not overlay the artwork"
    assert "Made to order" in h and "You approve before print" in h


def test_preview_wrap_has_studio_backing_for_letterboxed_photos(tmp_path):
    # REGRESSION (owner report 2026-07-19, tote): a real product photo squarer than
    # the 520:650 preview box letterboxes under object-fit:contain, and on a WHITE
    # wrap the top band read as a BLANK/broken preview ("not clear"). The wrap must
    # carry the studio tone (drawArt's drawn-field fill) so letterbox bands read as
    # intentional set, never empty page.
    h = _page(tmp_path)
    seg = h.split(".mcanvaswrap{", 1)[1].split("}", 1)[0]
    assert "background:#e9e6df" in seg, "preview wrap lost its studio backing"


def test_background_removal_available_on_every_product(tmp_path):
    # Client-side, free, private background removal on the shared photo controls -
    # so every product that takes a photo/logo gets it. 3D stays cylindrical-only.
    h = _page(tmp_path)
    assert "function removeBg" in h and "Remove background" in h
    assert "getImageData" in h                       # client-side pixel op (no upload)
    assert "function _is3D" in h and "bottle|tumbler" in h   # 3D for mugs + bottles/tumblers


def test_sleeves_have_their_own_editable_print_area(tmp_path):
    # REGRESSION: selecting a sleeve tab must show a distinct SLEEVE print area + label
    # (not the front chest box), so the buyer can actually design each sleeve.
    js = _page(tmp_path)
    assert "function _apparelBound" in js                       # per-area print frame
    assert "APPLACEMENT==='sleeve-left'" in js               # sleeve gets its own bound
    assert "'sleeve-left':'Left sleeve'" in js           # per-area drag label
    assert "_apparelBound(W,H)" in js                           # drawArt uses it for apparel


def test_sleeve_frame_resizes_width_and_length_independently(tmp_path):
    # REGRESSION: a sleeve is a long, narrow strip - the buyer must be able to stretch
    # WIDTH and LENGTH independently, not just scale uniformly. Width is driven by BOX.s
    # and length by an INDEPENDENT BOX.sy (corner: sideways=width, up/down=length).
    js = _page(tmp_path)
    # A second, independent length scale exists and drives the sleeve bound's height.
    assert "sy:1.0" in js or "sy:1.5" in js                     # BOX carries an sy dimension
    assert "H*0.20*(BOX.sy" in js                               # sleeve LENGTH uses BOX.sy, not BOX.s
    # The corner-resize gesture sets width and length on separate axes for a sleeve
    # (anchored at the opposite corner - see the anchor test for the down-the-arm feel).
    assert "BOX.s=wpx/(0.16*W); BOX.sy=hpx/(0.20*H)" in js      # width from X, length from Y
    assert "wpx=Math.max(0.048*W, ax-px.x)" in js               # width tracks the handle
    assert "hpx=Math.max(0.06*H, px.y-ay)" in js                # length tracks the handle
    # The clamp keeps the independent length in range so it can't invert or run away.
    assert "BOX.sy=Math.min(3.0,Math.max(0.30,BOX.sy))" in js


def test_sleeve_text_defaults_to_vertical(tmp_path):
    # REGRESSION: a sleeve is long + narrow, so wording reads best VERTICALLY down the
    # arm. Opening a fresh sleeve must seed the text rotation to sideways (mirrored per
    # arm), while the existing Upright/Sideways buttons still let the buyer switch.
    js = _page(tmp_path)
    assert "TROT=(p==='sleeve-left'?-90:90)" in js               # new sleeve -> vertical text
    assert "if(_tr)_tr.value=TROT" in js                         # slider reflects the default
    # The horizontal/vertical switch controls still exist so it's not locked vertical.
    assert "setRot(0)" in js and "setRot(-90)" in js and "setRot(90)" in js


def test_sideways_text_grows_to_fill_narrow_frame(tmp_path):
    # REGRESSION: vertical text in a NARROW sleeve frame must GROW to fill the box, not
    # collapse to a few px. The old auto-fit started at 10% of the (narrow) width and
    # only shrank, so sideways sleeve wording looked absent ("can't add text"). The
    # sideways branch now starts large and shrinks to fit both thickness AND length.
    js = _page(tmp_path)
    assert "else if(sideways)" in js                             # dedicated vertical-fit path
    assert "Math.round(stackDim*0.62)" in js                    # starts LARGE (was 0.10)
    assert "<=stackDim*0.92 && _ml<=maxW) break" in js          # shrinks to fit thickness + length


def test_quick_design_front_and_back_file_dropzones(tmp_path):
    # REGRESSION: buyers expected a quick way to drop a ready-made file for the FRONT
    # and a separate file for the BACK. Two drop-zones must exist, each routed to its
    # side, and each side keeps its OWN uploaded design (per-side capture).
    js = _page(tmp_path)
    assert 'id="quickdesign"' in js                              # the quick-design panel
    assert "Front picture" in js and "Back picture" in js       # front + back drop-zones
    # sleeves get their OWN optional picture drop-zones too (photo on a sleeve, not just text)
    assert "Left sleeve picture" in js and "Right sleeve picture" in js
    assert "quickSideUpload('sleeve-left',this)" in js and "quickSideUpload('sleeve-right',this)" in js
    assert "'sleeve-left':{t:'qsleeveLthumb'" in js              # sleeve upload maps to its own thumb
    # explicit, exact instruction: click the + and upload from your computer
    assert "Click ＋ to upload from your computer" in js
    assert "choose a picture from your computer" in js
    # the drop-zones REPLACE the single uploader for apparel (no duplicate picker)
    assert 'id="singlepick"' in js
    assert "sp.style.display = (IS_APPAREL && MULTI_AREA) ? 'none' : 'block'" in js
    assert "quickSideUpload('front',this)" in js                # front input -> front side
    assert "quickSideUpload('back',this)" in js                 # back input -> back side
    assert "function quickSideUpload" in js
    assert "setPlacement(side)" in js                           # activates the target side
    assert "SIDES[side]=_captureSide()" in js                   # persists that side's own design
    # apparel-only (needs two sides); gated with the front/back placement bar.
    assert "qd.style.display = (IS_APPAREL && MULTI_AREA)" in js


def test_sleeve_resize_anchors_opposite_corner_extends_down_arm(tmp_path):
    # REGRESSION: the green resize handle grew the sleeve frame from its CENTRE, so
    # lengthening pushed it UP off the shoulder ("moves little up or down"). The sleeve
    # resize now anchors the OPPOSITE (top-right) corner so the handle tracks the finger
    # and dragging DOWN extends the length down the arm, with a wider vertical range.
    js = _page(tmp_path)
    assert "let RESIZE_ANCHOR=null" in js                        # anchor state exists
    assert "x:APPAREL_BOUND.x+APPAREL_BOUND.w, y:APPAREL_BOUND.y" in js  # top-right corner captured
    assert "RESIZE_ANCHOR?RESIZE_ANCHOR.x:cx" in js             # move uses the anchor
    assert "BOX.x=((ax+px.x)/2)/W; BOX.y=((ay+px.y)/2)/H" in js # recentre keeps anchor fixed
    assert "H*0.94-bh" in js                                     # wider downward range (was 0.82)


def test_front_back_text_has_a_visible_drag_handle(tmp_path):
    # REGRESSION (expert-designer request): text on front/back must be visibly grabbable
    # and draggable ANYWHERE, including OVER the photo. A gold move-handle sits on the
    # wording, and grabbing it ALWAYS moves the text - never the photo underneath.
    # Sleeves move as a unit, so there is no separate text handle there.
    js = _page(tmp_path)
    assert "let TEXT_HANDLE=null" in js
    assert "WORDING drag handle" in js                                # the visible handle is drawn
    assert "if(TEXT_HANDLE && Math.abs(px.x-TEXT_HANDLE.x)<22" in js   # grabbing it always moves text
    assert "TEXT_HANDLE={x:ax+_off*Math.sin(_th)" in js               # handle sits on the wording


def test_front_back_picture_is_its_own_box_text_is_free(tmp_path):
    # REGRESSION (independent-layers request): when a PICTURE is present on front/back it
    # gets its OWN blue box (move/resize it), the print-area frame fades to a faint
    # boundary, and the wording is a separate free layer dragged anywhere in the print
    # area - "move the text out of the box, box = just the picture".
    js = _page(tmp_path)
    assert "var _hasPic=!!(PHOTO && PHOTO_RECT && (IS_APPAREL||IS_BRANDED))" in js
    assert "ctx.strokeRect(_pr.x,_pr.y,_pr.w,_pr.h)" in js       # the picture's own box outline
    assert "rgba(0,0,0,.16)" in js                              # print area faded when a picture is present
    assert "blue box = your picture" in js                      # layers caption


def test_sleeve_default_runs_down_the_outer_arm(tmp_path):
    # REGRESSION: sleeve wording must sit on the OUTER side of the sleeve, running DOWN the
    # arm (shoulder->cuff) like a real sleeve print - not clustered on the inner/body edge
    # by the shoulder. The default is garment-aware: a LONG sleeve opens on the outer edge
    # (x 0.13/0.87) running the arm length (sy 2.4); a short sleeve gets a small patch.
    js = _page(tmp_path)
    assert "function _sleeveDefaultBox(p)" in js
    assert "_long ? {x:(_l?0.13:0.87), y:0.52, s:0.72, sy:2.4}" in js   # down the outer long sleeve
    assert "BOX=_sleeveDefaultBox(p)" in js                             # seeded on open
    assert "BOX=_sleeveDefaultBox(APPLACEMENT)" in js                   # and on reset


def test_final_proof_has_pan_and_zoom(tmp_path):
    # REGRESSION (premium product-page feel): on the final preview the buyer can ZOOM into
    # every corner of the finished design on the garment and PAN around - scroll/pinch to
    # zoom (clamped 1..4x), drag to look around when zoomed, double-click toggles, and it
    # resets on flip/open. It's a VIEW transform on the proof image only - never the design.
    js = _page(tmp_path)
    assert 'id="proofZoomWrap"' in js and "overflow:hidden" in js       # clipped zoom container
    assert "function _proofApplyZoom" in js and "function _proofSetZoom" in js
    assert 'onwheel="_proofWheel(event)"' in js and 'ondblclick="_proofDbl(event)"' in js
    assert "Math.max(1,Math.min(4,z))" in js                            # zoom clamped 1..4x
    assert "if(PROOF_ZOOM>1){" in js                                    # zoomed -> pan; at fit -> spin
    assert "Scroll or pinch to zoom" in js                             # discoverable hint
    assert "function _proofResetZoom" in js                             # resets on flip/open


def test_sleeve_editing_contract(tmp_path):
    # REGRESSION (from the full sleeve-subsystem audit): these are the load-bearing
    # invariants that kept regressing at the SEAMS. Pin them so a future edit can't
    # silently drop a sleeve from the order, the thumbnail, or the submitted proof.
    js = _page(tmp_path)
    # ORDER INTEGRITY: the per-item design payload carries ALL FOUR areas - a designed
    # sleeve is previewed AND priced, so dropping its content would ship a paid sleeve blank.
    assert "'sleeve-left':_stripPhoto(SIDES['sleeve-left'])" in js
    assert "'sleeve-right':_stripPhoto(SIDES['sleeve-right'])" in js
    # SINGLE-SOURCE COMPOSITING: the basket thumbnail + the submitted checkout proof use the
    # SAME front-with-sleeves compositor as the live proof/spin, so they can't drift apart.
    assert "function _composedFrontURL(maxDim)" in js                       # one compositor, sized
    assert "if(IS_APPAREL){ var _u=_composedFrontURL(240)" in js            # thumbnail path
    assert "proof:(IS_APPAREL?_composedFrontURL():_composedProofURL())" in js  # checkout proof
    # LAYOUTS: sleeves are freeform-only (Layout Studio hidden + CURLAYOUT forced freeform).
    assert "if(_sleeveNow){ CURLAYOUT='freeform'; if(_lb)_lb.style.display='none'; }" in js
    # TEXT FIT: horizontal sleeve text shrinks to the narrow WIDTH, not just the height.
    assert "_wideAt()) && fs>9" in js
    # RESET: the placement reset restores a sleeve's FRAME (BOX), not just TPOS.
    assert "if(APPLACEMENT==='sleeve-left'||APPLACEMENT==='sleeve-right') resetFrame();" in js
    # the contract spec itself ships as a durable in-code guard for future changes.
    assert "SLEEVE EDITING CONTRACT" in js


def test_sleeve_design_moves_as_a_unit(tmp_path):
    # REGRESSION: on a small sleeve, grabbing the design returned 'text' (nudge the
    # wording WITHIN the frame), so the whole design felt stuck - the buyer "couldn't
    # move the left/right sleeve design". Any grab inside a SLEEVE frame (past the resize
    # corner) must move the WHOLE frame as a unit onto the arm.
    js = _page(tmp_path)
    assert "if(APPLACEMENT==='sleeve-left'||APPLACEMENT==='sleeve-right') return 'frame';" in js
    assert "moves as a UNIT" in js


def test_sleeve_grab_moves_frame_not_flips_garment(tmp_path):
    # REGRESSION: the sleeve frame is small, so a near-miss grab hit 'rotate' and FLIPPED
    # the shirt front/back - the sleeve felt un-editable ("cannot edit sleeve"). A grab
    # outside a SLEEVE frame must MOVE it, not flip; front/back keep the spin gesture.
    js = _page(tmp_path)
    assert "'sleeve-left'||APPLACEMENT==='sleeve-right') ? 'frame' : 'rotate'" in js


def test_text_orientation_toggle_on_the_fly(tmp_path):
    # REGRESSION: buyers wanted to switch wording between vertical and horizontal ON THE
    # FLY, right by the preview - not buried in the Text step. A one-tap toggle in the
    # move/resize bar flips TROT between vertical and 0 and labels the current state.
    js = _page(tmp_path)
    assert 'id="mtdirbtn"' in js                                 # the on-the-fly toggle button
    assert "toggleTextOrientation()" in js
    assert "function toggleTextOrientation" in js
    assert "function _textIsVertical" in js                      # decides vertical vs horizontal
    assert "setRot(_textIsVertical()?0:vert)" in js             # flips to the opposite orientation


def test_final_proof_front_shows_sleeves_back_is_back_only(tmp_path):
    # REGRESSION: the final-design proof must show the FRONT view = front design PLUS
    # both sleeve designs on the arms (a shirt shows its sleeves from the front), and
    # the BACK view = ONLY the back design (there are no sleeves on the back side).
    js = _page(tmp_path)
    assert "function _composedFrontURL" in js                    # front = front + sleeves composite
    assert "['sleeve-left','sleeve-right'].forEach" in js        # both sleeves overlaid on the front view
    assert "function _proofViews" in js
    assert "_sideHas(SIDES['back'])) v.push('back')" in js       # back is its OWN view (no sleeves)
    assert "_proofRenderView('front')" in js                     # proof opens on the front composite
    assert "the front view shows your sleeves on the arms" in js


def test_apparel_faithful_print_files_render_wired(tmp_path):
    # REGRESSION (#167 Phase 2b): apparel produces faithful per-side DTG PRINT FILES -
    # the design ONLY, on a transparent canvas, at PRINT resolution (not the screen
    # canvas upscaled). drawArt suppresses the garment mockup/silhouette/shadow in
    # _PRINTMODE. Structural (canvas pixels need a browser; the owner's physical test
    # print is the visual gate, held behind APPAREL_PRINT_CALIBRATED).
    js = _page(tmp_path)
    assert "function _printFiles()" in js
    assert "if(IS_APPAREL) _uploadPrintFiles();" in js           # #Phase2c: uploaded to backend
    assert "function _uploadPrintFiles()" in js
    assert "let _PRINTMODE=false" in js
    assert "else if(_PRINTMODE)" in js                            # transparent, no studio fill
    assert "!_mock && !_PRINTMODE" in js                          # no shadow in print mode
    assert "if(_mock||_PRINTMODE)" in js                          # no drawn garment in print mode
    assert "K=3000/Math.max(ow,oh)" in js                         # rendered at PRINT resolution


def test_sleeveless_garment_gates_sleeve_areas(tmp_path):
    # REGRESSION (#tank): a Tank Top is sleeveless. The editor must gate sleeve
    # placements, tabs, upload zones, the upcharge, and the compositor on
    # _garmentSleeves() (backed by the catalog's has_sleeves) so no customer can
    # design or be billed for a sleeve that doesn't exist (unfulfillable order).
    import json, re
    js = _page(tmp_path)
    assert "function _garmentSleeves()" in js                    # the predicate exists
    assert "MULTI_AREA && _garmentSleeves()" in js               # gates the valid placements
    assert "_sl && _sides['sleeve-left']" in js                  # gates the sleeve upcharge
    assert "if(_garmentSleeves()) ['sleeve-left','sleeve-right'].forEach" in js  # compositor
    m = re.search(r"const APPHASSLEEVES = (\{[^}]*\});", js)      # per-garment sleeve map emitted
    assert m, "APPHASSLEEVES not emitted"
    hs = json.loads(m.group(1))
    assert hs.get("Men's Tank Top") is False                     # tank = sleeveless
    assert hs.get("Men's T-Shirt") is True                       # tee has sleeves


def test_spin_review_shows_sleeves_and_hides_duplicate_button(tmp_path):
    # REGRESSION: (1) the inline spin/flip review must show the FRONT with both sleeve
    # designs so the buyer can SEE the sleeve wording (not a bare front); (2) while it is
    # open, its own "See the back" is the spin control, so the editor's "Spin your
    # product" button is hidden - no two spin controls on screen at once.
    js = _page(tmp_path)
    assert "_composedFrontURL():_composedProofURL()" in js       # front view composites the sleeves
    # "(with sleeves)" is now garment-aware (#tank): sleeveless garments drop it. The
    # label is built as 'Front'+(_garmentSleeves()?' (with sleeves)':'').
    assert "(with sleeves)" in js and "_garmentSleeves()?' (with sleeves)'" in js
    assert "_spinBtn.style.display='none'" in js                 # hide the duplicate spin button while open
