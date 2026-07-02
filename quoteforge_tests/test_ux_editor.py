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
    # REGRESSION: the mug spin wraps the design ~300 degrees (not a 97-degree front
    # panel) and auto-spins a full turn, so the buyer sees front AND back.
    js = _page(tmp_path)
    assert "arc:(handle?5.3:5.6)" in js                 # full-circumference wrap (was arc:1.7)
    assert "rot+=0.010" in js                           # full 360 auto-spin (was a gentle rock)


def test_proof_reviews_every_designed_area(tmp_path):
    # REGRESSION: the buyer must SEE every area they designed (front/back/sleeves) before
    # the single affirmative approval - the proof flip cycles ALL designed areas, and the
    # consent line covers exactly what is shown. This is the no-return policy's record.
    js = _page(tmp_path)
    assert "function _designedAreas()" in js
    assert "areas[(i+1)%areas.length]" in js                    # cycles all designed areas
    assert 'id="proofAreas"' in js                              # lists what they designed
    assert "flip to review each area before you approve" in js
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


def test_layout_gallery_has_descriptions_and_product_filtering(tmp_path):
    # UX: each template carries a plain-English description, and apparel-only styles
    # (Back Print / Left-Chest / Streetwear) are filtered out for non-apparel products.
    h = _page(tmp_path)
    assert "const LAYOUT_META" in h
    assert "Name curved around a round photo" in h        # a real description
    assert "only styles that suit this product" in h       # the per-product filter
    assert "f:['apparel']" in h                            # apparel-only tagging
    assert ".layoutthumb small" in h                        # description caption style


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
    # The corner-resize gesture sets width and length on separate axes for a sleeve.
    assert "BOX.sy=2*Math.abs(px.y-cy)/(0.20*H)" in js          # vertical drag -> length
    assert "BOX.s=2*Math.abs(px.x-cx)/(0.16*W)" in js           # horizontal drag -> width
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
