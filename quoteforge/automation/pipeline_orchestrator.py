"""7-Stage Pipeline Orchestrator.

Stage 1: Order Intake      — receive + store in SQLite
Stage 2: AI Quote          — generate personalized message
Stage 3: Artwork           — render PNG (Canva → Bannerbear → local fallback)
Stage 4: Drive Upload      — save PNG to Google Drive
Stage 5: Proof (optional)  — send preview to customer for approval
Stage 6: Gelato Order      — create production order via Gelato API
Stage 7: Follow-up         — upsell + review request messages

Each stage updates the order status in SQLite and Airtable.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from quoteforge.config import (
    OUTPUT_DIR, BANNERBEAR_TEMPLATE_UID,
    PIPELINE_AUTO_APPROVE_PROOF, TEST_MODE, RENDERER, CUSTOMER_PROOF_APPROVAL,
    GENERATE_ROOM_MOCKUP, PREFLIGHT_ENABLED,
)
from quoteforge.db.database import (
    create_order, update_order, get_order, log_pipeline_stage,
)
from quoteforge.quotes.generator import generate_personal_message
from quoteforge.images.renderer import render_poster
from quoteforge.images.backgrounds import fetch_background_url
from quoteforge.images.downloader import download_png
from quoteforge.quotes.categories import get_mood, get_unsplash_keyword
from quoteforge.automation.canva_api import create_design_from_template, export_design_as_png
from quoteforge.automation.google_drive_client import upload_png_to_drive
from quoteforge.etsy.order_processor import _log_order

logger = logging.getLogger(__name__)

# Pipeline stage names
STAGES = [
    "order_intake",
    "quote_generation",
    "artwork_generation",
    "drive_upload",
    "proof",
    "gelato_order",
    "followup",
]

STATUS_MAP = {
    "order_intake":      "received",
    "quote_generation":  "quote_generated",
    "artwork_generation": "artwork_done",
    "drive_upload":      "artwork_stored",
    "proof":             "proof_sent",
    "gelato_order":      "in_production",
    "followup":          "shipped",
}


def _auto_email_customer(order_data: dict, message: str) -> None:
    """Auto-reply to the buyer (e.g. a photo-quality request), best-effort."""
    from quoteforge.config import AUTO_EMAIL_CUSTOMER
    email = order_data.get("customer_email", "")
    if not (AUTO_EMAIL_CUSTOMER and email):
        return
    try:
        from quoteforge.automation.emailer import _send_email
        _send_email("A quick note about your Joffiels order",
                    f"<html><body style='font-family:Arial'><pre>{message}</pre>"
                    f"</body></html>", to=email)
    except Exception:  # noqa: BLE001 - never fail the pipeline on an email
        pass


def _render_test_artwork(order_id: str, quote: str, recipient: str) -> Optional[Path]:
    """Render a simple placeholder poster PNG locally for TEST_MODE runs.

    Uses Pillow (already a dependency). Produces a real on-disk file so the
    artwork stage is verifiable without paid rendering APIs.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    out_dir = OUTPUT_DIR / "pipeline" / order_id
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / "artwork.png"

    # 1800x2400 = 6x8 in @ 300 DPI placeholder
    img = Image.new("RGB", (1800, 2400), color=(34, 51, 68))
    draw = ImageDraw.Draw(img)
    draw.rectangle([60, 60, 1740, 2340], outline=(220, 220, 220), width=6)
    lines = ["[ TEST MODE ARTWORK ]", "", f"For: {recipient}", "", "Quote preview:"]
    wrapped = quote.replace("\n", " ")
    while wrapped:
        lines.append(wrapped[:46])
        wrapped = wrapped[46:]
    y = 300
    for line in lines[:24]:
        draw.text((120, y), line, fill=(240, 240, 240))
        y += 60
    img.save(png_path, "PNG")
    return png_path


def _create_followup_records(order_id: str, order_data: dict) -> None:
    """Persist customer lifecycle messages, an upsell offer, and a review request."""
    from datetime import datetime, timedelta
    from quoteforge.db.database import (
        save_customer_message, save_upsell, save_review,
    )
    from quoteforge.etsy.customer_messages import BASE_TEMPLATES
    from quoteforge.automation.upsell import (
        generate_upsell_message, generate_review_request,
    )
    from quoteforge.config import PIPELINE_REVIEW_DELAY_DAYS

    customer = order_data.get("customer_name", "")
    occasion = order_data.get("occasion", "")
    recipient = order_data.get("recipient_name", "")

    # Lifecycle customer messages (queued, not yet sent)
    for msg_type, body in BASE_TEMPLATES.items():
        save_customer_message(order_id, msg_type, body, sent=False)

    # Upsell offers
    upsell = generate_upsell_message(customer, occasion)
    save_upsell(order_id, "canvas", upsell["canvas_message"])
    save_upsell(order_id, "framed", upsell["framed_message"])
    save_upsell(order_id, "bundle", upsell["bundle_message"])

    # Review request scheduled for the future
    review_msg = generate_review_request(customer, occasion, recipient)
    scheduled = (datetime.now() + timedelta(days=PIPELINE_REVIEW_DELAY_DAYS)).isoformat()
    save_review(order_id, review_msg, scheduled_for=scheduled)


def run_full_pipeline(
    order_data: dict,
    on_stage: Optional[Callable[[str, str], None]] = None,
    canva_template_id: str = "",
    skip_proof: bool = False,
    recipient_address: Optional[dict] = None,
    gelato_product_uid: str = "",
) -> dict:
    """Run the complete 7-stage pipeline for one order.

    on_stage(stage_name, status): callback for progress updates
    Returns final order dict.
    """

    def _notify(stage: str, msg: str) -> None:
        """Log a stage update and forward it to the on_stage callback."""
        logger.info(f"[{stage}] {msg}")
        if on_stage:
            on_stage(stage, msg)

    def _log(order_id: str, stage: str, status: str, msg: str = "") -> None:
        """Record the stage result and advance the order's status."""
        log_pipeline_stage(order_id, stage, status, msg)
        update_order(order_id, status=STATUS_MAP.get(stage, stage))

    # ── Stage 1: Order Intake ────────────────────────────────────
    _notify("order_intake", "Storing order in database...")
    order_id = create_order(order_data)
    _log(order_id, "order_intake", "success", f"Order {order_id} created")

    try:
        # ── Stage 2: Quote (verbatim custom text OR AI-generated) ──
        # If the buyer supplied their OWN exact wording, use it verbatim and skip
        # AI generation entirely. Otherwise generate a personalized quote.
        custom_text = (order_data.get("custom_text")
                       or order_data.get("custom_quote") or "").strip()
        if custom_text:
            _notify("quote_generation", "Using buyer's custom text (verbatim)...")
            quote = custom_text
        else:
            _notify("quote_generation", "Generating personalized quote...")
            from quoteforge.automation.retry import retry_call
            variations = retry_call(
                generate_personal_message,
                relationship=order_data.get("relationship", "To My Friend"),
                recipient_name=order_data.get("recipient_name", ""),
                sender_name=order_data.get("sender_name", ""),
                occasion=order_data.get("occasion", ""),
                memory_or_story=order_data.get("memory", ""),
                scenery=order_data.get("scenery", "Mountains"),
                output_style=order_data.get("output_style", "Personal Letter"),
                count=1,
            )
            quote = variations[0] if variations else ""
        update_order(order_id, generated_quote=quote)
        _log(order_id, "quote_generation", "success", f"{len(quote)} chars generated")
        _notify("quote_generation", f"Quote generated: {quote[:60]}...")

        # ── Stage 3: Artwork Generation ──────────────────────────
        _notify("artwork_generation", "Generating artwork...")
        artwork_url: str = ""
        png_path: Optional[Path] = None

        # TEST_MODE → render a local placeholder PNG so the stage produces a
        # real file without calling paid rendering APIs.
        if TEST_MODE:
            png_path = _render_test_artwork(order_id, quote,
                                            order_data.get("recipient_name", ""))
            artwork_url = png_path.as_uri() if png_path else ""

        # Free local renderer (default) — composite quote over background with Pillow.
        if not artwork_url and RENDERER == "local":
            from quoteforge.images.local_renderer import render_local_poster
            out_dir = OUTPUT_DIR / "pipeline" / order_id
            # If the buyer supplied their OWN photo, use it as the background;
            # otherwise fetch a scenic Unsplash image for the chosen mood.
            custom_image = (order_data.get("custom_image")
                            or order_data.get("custom_photo") or "")
            from quoteforge.etsy.gelato_catalog import dimensions_for
            size_key = (order_data.get("product_size")
                        or order_data.get("size") or gelato_product_uid)
            bg_url = None
            bg_path = None
            if custom_image:
                # Resolve to a local file so we can verify print quality first.
                local = None
                if str(custom_image).startswith(("http://", "https://")):
                    local = download_png(custom_image, out_dir, "custom_photo")
                elif Path(str(custom_image)).exists():
                    local = Path(str(custom_image))
                # QUALITY GATE: a low-res buyer photo must NEVER reach print.
                if local:
                    from quoteforge.images.photo_check import (
                        check_customer_photo, photo_request_message)
                    chk = check_customer_photo(local, size_key)
                    if not chk["ok"]:
                        msg = photo_request_message(
                            chk, order_data.get("customer_name", "there"),
                            order_data.get("recipient_name", "your order"))
                        from quoteforge.db.database import (
                            save_customer_message, enqueue_approval)
                        save_customer_message(order_id, "photo_request", msg, sent=False)
                        _log(order_id, "photo_check", "fail", chk["reason"])
                        # set AFTER _log (which resets status to the stage name)
                        update_order(order_id, status="needs_better_photo")
                        _notify("artwork_generation",
                                f"Buyer photo too low quality: {chk['reason']}")
                        _auto_email_customer(order_data, msg)
                        try:
                            enqueue_approval(
                                kind="photo", ref=order_id,
                                summary=f"Buyer photo too low-res ({chk['reason']}) "
                                        f"- auto-reply sent asking for a better one",
                                proposed_action="await_better_photo", risk="medium",
                                status="pending")
                        except Exception:  # noqa: BLE001
                            pass
                        return get_order(order_id) or {}
                    bg_path = local
                    _notify("artwork_generation", "Buyer photo verified - using it.")
            else:
                category = order_data.get("category", "Motivation & Mindset")
                scenery = order_data.get("scenery", "Mountains")
                mood = get_mood(category, "")
                keyword = get_unsplash_keyword(mood)
                bg_url = fetch_background_url(keyword) or fetch_background_url(scenery)
            # Render at the ORDERED product's exact 300-DPI dimensions.
            render_size = dimensions_for(size_key)
            png_path = render_local_poster(
                quote=quote,
                output_path=out_dir / "artwork.png",
                background_url=bg_url,  # None → solid color fallback
                background_path=bg_path,
                size=render_size,
            )
            artwork_url = png_path.as_uri()

        # Canva API (if a template is configured)
        if not artwork_url and canva_template_id:
            canva_result = create_design_from_template(
                canva_template_id, quote,
                order_data.get("recipient_name", ""),
            )
            if canva_result.get("status") == "success":
                artwork_url = export_design_as_png(canva_result["design_id"]) or ""

        # Bannerbear (optional paid upgrade)
        if not artwork_url and BANNERBEAR_TEMPLATE_UID and BANNERBEAR_TEMPLATE_UID != "YOUR_BANNERBEAR_TEMPLATE_UID":
            category = order_data.get("category", "Motivation & Mindset")
            scenery = order_data.get("scenery", "Mountains")
            mood = get_mood(category, "")
            keyword = get_unsplash_keyword(mood)
            bg_url = fetch_background_url(keyword) or fetch_background_url(scenery)
            if bg_url:
                artwork_url = render_poster(BANNERBEAR_TEMPLATE_UID, quote, bg_url) or ""

        # Download remote artwork to local disk (skip if already local, e.g. TEST_MODE)
        if artwork_url and png_path is None and artwork_url.startswith(("http://", "https://")):
            out_dir = OUTPUT_DIR / "pipeline" / order_id
            png_path = download_png(artwork_url, out_dir, "artwork")

        update_order(order_id, artwork_url=artwork_url)
        _log(order_id, "artwork_generation", "success" if artwork_url else "skipped",
             f"Artwork URL: {artwork_url[:80] if artwork_url else 'none'}")

        # Emit a styled-room lifestyle mockup for the Etsy gallery whenever we
        # have a local print file. Context sells high-ticket wall art (a framed
        # print on a styled wall converts far better than a print on white).
        # Best-effort: a mockup failure must never block the print itself.
        if GENERATE_ROOM_MOCKUP and png_path and png_path.exists():
            try:
                from quoteforge.images.room_mockup import render_room_mockup
                mockup_path = render_room_mockup(
                    png_path, png_path.parent / "mockup_room.png")
                update_order(order_id, mockup_url=mockup_path.as_uri())
                _log(order_id, "artwork_generation", "success",
                     f"Room mockup: {mockup_path.name}")
            except Exception as exc:  # noqa: BLE001
                _log(order_id, "artwork_generation", "warn",
                     f"Room mockup skipped: {type(exc).__name__}: {exc}")

        # ── Stage 4: Google Drive Upload ─────────────────────────
        drive_url = ""
        if png_path and png_path.exists():
            _notify("drive_upload", "Uploading to Google Drive...")
            drive_url = upload_png_to_drive(png_path, f"{order_id}_artwork.png") or ""
            update_order(order_id, drive_file_id=drive_url)
        _log(order_id, "drive_upload", "success" if drive_url else "skipped",
             drive_url or "local only")

        # ── Stage 4.9: Final QC BEFORE the customer proof ────────
        # Quality must pass before anything reaches the customer. Combines the
        # deterministic print preflight with an optional Claude vision review.
        if PREFLIGHT_ENABLED and not TEST_MODE and png_path and png_path.exists():
            from quoteforge.images.final_qc import final_qc
            size_key = (order_data.get("product_size")
                        or order_data.get("size") or gelato_product_uid)
            qc = final_qc(png_path, size_key)
            if not qc["ok"]:
                fails = qc["fails"]
                _log(order_id, "preflight", "fail", "; ".join(fails))
                update_order(order_id, status="preflight_failed")
                _notify("proof", f"QC FAILED before proof: {', '.join(fails)}")
                try:
                    from quoteforge.db.database import enqueue_approval
                    enqueue_approval(
                        kind="preflight", ref=order_id,
                        summary=f"Final QC failed ({', '.join(fails)}) - fix before "
                                f"sending the customer proof",
                        proposed_action="fix_artwork", risk="high", status="pending")
                except Exception:  # noqa: BLE001
                    pass
                return get_order(order_id) or {}
            _log(order_id, "preflight", "pass",
                 "Final QC passed - safe to send proof")

        # ── Stage 5: Proof ───────────────────────────────────────
        if not skip_proof and not PIPELINE_AUTO_APPROVE_PROOF:
            if CUSTOMER_PROOF_APPROVAL:
                # Prepare a proof package for the BUYER to approve. Printing is
                # blocked until you record their approval.
                _notify("proof", "Proof prepared — awaiting CUSTOMER approval")
                from quoteforge.automation.customer_proof import prepare_customer_proof
                prepare_customer_proof(
                    order_id,
                    artwork_path=str(png_path) if png_path else artwork_url,
                )
            else:
                _notify("proof", "Proof stage — owner review required")
                update_order(order_id, proof_sent=1)
                _log(order_id, "proof", "pending",
                     "Awaiting owner approval before Gelato order")
            return get_order(order_id) or {}
        else:
            # Proof bypassed (auto-approve or skip) — still log for the audit trail
            _notify("proof", "Proof auto-approved (skip_proof / auto-approve)")
            update_order(order_id, proof_sent=1, proof_approved=1)
            log_pipeline_stage(order_id, "proof", "auto_approved",
                               "Proof skipped per configuration")

        # (QC now runs at Stage 4.9, before the proof is ever sent.)

        # ── Stage 6: Fulfillment (vendor-routed) ─────────────────
        gelato_order_id = ""
        _notify("gelato_order", "Routing to vendor fulfillment...")
        try:
            from quoteforge.fulfillment.router import route_order
            from quoteforge.automation.retry import retry_call
            try:
                vendor = (get_order(order_id) or {}).get("vendor", "gelato")
            except Exception:  # noqa: BLE001
                vendor = "gelato"
            resp = retry_call(
                route_order,
                {"order_id": order_id, "vendor": vendor,
                 "gelato_product_uid": gelato_product_uid},
                recipient=recipient_address, artwork_url=artwork_url,
            )
            status = resp.get("status")
            if status in ("submitted", "fulfilled"):
                gelato_order_id = resp.get("id", "")
                if gelato_order_id:
                    # vendor_order_id is the honest name; gelato_order_id kept
                    # in sync for legacy readers (reports, Airtable export).
                    update_order(order_id, gelato_order_id=gelato_order_id,
                                 vendor_order_id=gelato_order_id)
                _log(order_id, "gelato_order", "success",
                     f"{resp.get('vendor')}: {status} {gelato_order_id}")
                _notify("gelato_order", f"{resp.get('vendor')} {status}")
            else:   # manual / error -> flag for the operator
                _log(order_id, "gelato_order", "skipped", resp.get("detail", status))
                _notify("gelato_order", resp.get("detail", "manual fulfillment"))
        except Exception as exc:
            _log(order_id, "gelato_order", "error", str(exc))
            _notify("gelato_order", f"Fulfillment error: {exc}")

        # ── Stage 7: Follow-up (persist messages, upsell, review) ──
        _notify("followup", "Creating follow-up messages...")
        _create_followup_records(order_id, order_data)
        _log(order_id, "followup", "success",
             "Customer messages, upsell, and review records created")

        return get_order(order_id) or {}

    except Exception as exc:
        log_pipeline_stage(order_id, "error", "failed", str(exc))
        update_order(order_id, status="error")
        raise


def resume_after_proof_approval(order_id: str,
                                 gelato_product_uid: str = "",
                                 recipient_address: Optional[dict] = None) -> dict:
    """Resume pipeline from Stage 6 after customer approves the proof."""
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found")

    update_order(order_id, proof_approved=1)
    log_pipeline_stage(order_id, "proof", "approved", "Customer approved proof")

    gelato_order_id = ""
    artwork_url = order.get("artwork_url", "")

    if gelato_product_uid and recipient_address and artwork_url:
        # Final validation gate before we spend money at Gelato: address complete,
        # product set, print file attached, and the AI quality check not rejected.
        from quoteforge.automation.print_quality import validate_order_for_gelato
        _val = validate_order_for_gelato({
            "recipient_address": recipient_address,
            "gelato_product_uid": gelato_product_uid,
            "artwork_url": artwork_url,
            "print_quality": order.get("print_quality"),
        })
        if not _val["ok"]:
            update_order(order_id, status="hold_validation")
            log_pipeline_stage(order_id, "order_validation", "hold",
                               "; ".join(_val["issues"]))
            return get_order(order_id) or {}
        from quoteforge.automation.gelato_api import create_gelato_order
        gelato_resp = create_gelato_order(
            order_id=order_id,
            recipient=recipient_address,
            artwork_url=artwork_url,
            product_uid=gelato_product_uid,
        )
        gelato_order_id = gelato_resp.get("id", "")
        update_order(order_id, gelato_order_id=gelato_order_id, status="in_production")
        log_pipeline_stage(order_id, "gelato_order", "success", gelato_order_id)
    else:
        # Manual-Gelato flow: approval recorded but no automated order placed.
        # Move the order off "awaiting_customer_approval" so it's clearly past
        # the customer gate and ready for you to upload the artwork to Gelato.
        update_order(order_id, status="approved_ready_to_print")
        log_pipeline_stage(order_id, "gelato_order", "manual",
                           "Approved — upload artwork to Gelato to print")

    return get_order(order_id) or {}


def get_pipeline_summary() -> dict:
    """Return counts per pipeline stage for dashboard display."""
    from quoteforge.db.database import get_order_stats
    return get_order_stats()
