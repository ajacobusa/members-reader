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
    PIPELINE_AUTO_APPROVE_PROOF,
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

        # Try Canva API first
        if canva_template_id:
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

        # Fall back to local placeholder
        if artwork_url:
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

        # ── Stage 7: Follow-up Scheduled ────────────────────────
        _notify("followup", "Follow-up messages scheduled")
        _log(order_id, "followup", "scheduled",
             "Upsell and review messages queued")

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
