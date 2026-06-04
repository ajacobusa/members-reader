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
    PIPELINE_AUTO_APPROVE_PROOF, TEST_MODE,
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
        logger.info(f"[{stage}] {msg}")
        if on_stage:
            on_stage(stage, msg)

    def _log(order_id: str, stage: str, status: str, msg: str = "") -> None:
        log_pipeline_stage(order_id, stage, status, msg)
        update_order(order_id, status=STATUS_MAP.get(stage, stage))

    # ── Stage 1: Order Intake ────────────────────────────────────
    _notify("order_intake", "Storing order in database...")
    order_id = create_order(order_data)
    _log(order_id, "order_intake", "success", f"Order {order_id} created")

    try:
        # ── Stage 2: AI Quote Generation ────────────────────────
        _notify("quote_generation", "Generating personalized quote...")
        variations = generate_personal_message(
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

        # Try Canva API first
        if not artwork_url and canva_template_id:
            canva_result = create_design_from_template(
                canva_template_id, quote,
                order_data.get("recipient_name", ""),
            )
            if canva_result.get("status") == "success":
                artwork_url = export_design_as_png(canva_result["design_id"]) or ""

        # Fall back to Bannerbear
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

        # ── Stage 4: Google Drive Upload ─────────────────────────
        drive_url = ""
        if png_path and png_path.exists():
            _notify("drive_upload", "Uploading to Google Drive...")
            drive_url = upload_png_to_drive(png_path, f"{order_id}_artwork.png") or ""
            update_order(order_id, drive_file_id=drive_url)
        _log(order_id, "drive_upload", "success" if drive_url else "skipped",
             drive_url or "local only")

        # ── Stage 5: Proof ───────────────────────────────────────
        if not skip_proof and not PIPELINE_AUTO_APPROVE_PROOF:
            _notify("proof", "Proof stage — manual review required")
            update_order(order_id, proof_sent=1)
            _log(order_id, "proof", "pending",
                 "Awaiting manual approval before Gelato order")
            # In production: send proof URL to customer via Etsy message
            # For now: mark as pending and return — resume when approved
            return get_order(order_id) or {}
        else:
            # Proof bypassed (auto-approve or skip) — still log for the audit trail
            _notify("proof", "Proof auto-approved (skip_proof / auto-approve)")
            update_order(order_id, proof_sent=1, proof_approved=1)
            log_pipeline_stage(order_id, "proof", "auto_approved",
                               "Proof skipped per configuration")

        # ── Stage 6: Gelato Order ────────────────────────────────
        gelato_order_id = ""
        if gelato_product_uid and recipient_address and artwork_url:
            _notify("gelato_order", "Creating Gelato production order...")
            try:
                from quoteforge.automation.gelato_api import create_gelato_order
                gelato_resp = create_gelato_order(
                    order_id=order_id,
                    recipient=recipient_address,
                    artwork_url=artwork_url,
                    product_uid=gelato_product_uid,
                )
                gelato_order_id = gelato_resp.get("id", "")
                update_order(order_id, gelato_order_id=gelato_order_id)
                _log(order_id, "gelato_order", "success", gelato_order_id)
            except Exception as exc:
                _log(order_id, "gelato_order", "error", str(exc))
                _notify("gelato_order", f"Gelato error: {exc}")
        else:
            _log(order_id, "gelato_order", "skipped",
                 "No product UID or address — manual Gelato upload required")
            _notify("gelato_order", "Gelato skipped — upload artwork manually")

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

    return get_order(order_id) or {}


def get_pipeline_summary() -> dict:
    """Return counts per pipeline stage for dashboard display."""
    from quoteforge.db.database import get_order_stats
    return get_order_stats()
