"""Customer proof-approval workflow.

When an order reaches the proof stage, this prepares everything you need to
get the BUYER's approval before printing:
  1. a ready-to-send proof message (personalized)
  2. the proof image path to attach in the Etsy conversation

Printing is blocked until you record the customer's approval. Etsy has no API
to auto-send a proof and auto-detect the reply, so the send/receive happens in
Etsy's normal messaging — this module does everything around that.
"""
from pathlib import Path
from typing import Optional

from quoteforge.db.database import (
    get_order, update_order, log_pipeline_stage, save_customer_message,
)


def prepare_customer_proof(order_id: str, artwork_path: Optional[str] = None) -> dict:
    """Build + persist the proof message for the buyer and mark the order as
    awaiting customer approval. Returns the proof package for you to send.
    """
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found")

    recipient = order.get("recipient_name", "your recipient")
    occasion = order.get("occasion", "your order")
    from quoteforge.config import SHOP_NAME

    message = (
        f"Hi! Thank you so much for your order from {SHOP_NAME}. Here's the "
        f"proof of your personalized {occasion} print for {recipient} — this "
        f"is exactly what will print.\n\n"
        f"Please check the name, spelling, wording, and overall design. Spot "
        f"anything you'd like changed? Just reply within 24 hours and I'll fix "
        f"it free before printing. If it's perfect, you don't need to do a "
        f"thing — it heads to print right away.\n\n"
        f"With gratitude,\nThe {SHOP_NAME} team"
    )

    # Optional production preview: a real mockup of the design ON the garment, as
    # a VISUAL AID for the buyer. Additive + guarded - never blocks the proof, and
    # it does NOT change the print file (the parity-gate hash + proof approval are
    # unchanged). None in TEST_MODE / no key / non-apparel / on any failure.
    product_mockup = None
    try:
        from quoteforge.images.supplier_mockup import design_mockup_for_order
        product_mockup = design_mockup_for_order(order, artwork_path)
    except Exception:  # noqa: BLE001
        product_mockup = None
    if product_mockup:
        message += ("\n\nP.S. I've also attached a preview of how your design looks "
                    "on the garment itself - the wording/photo is what you confirm "
                    "above.")

    # Persist the proof message (so it's logged against the order)
    save_customer_message(order_id, "Proof Ready", message, sent=False)

    # Mark the order as waiting on the customer (printing is blocked here)
    update_order(order_id, status="awaiting_customer_approval", proof_sent=1)
    log_pipeline_stage(order_id, "proof", "awaiting_customer",
                       "Proof prepared — awaiting customer approval via Etsy")

    return {
        "order_id": order_id,
        "recipient": recipient,
        "proof_message": message,
        "artwork_path": artwork_path or order.get("artwork_url", ""),
        "product_mockup": product_mockup,   # visual aid only; None when unavailable
        "instructions": (
            "Send the proof_message to the buyer in the Etsy order conversation "
            "and attach the artwork image. If no change request arrives within "
            "the 24h window (or they confirm it's perfect), run: "
            f"python -m quoteforge.admin customer-approved {order_id}"
        ),
    }


def record_customer_approval(order_id: str,
                             gelato_product_uid: str = "",
                             recipient_address: Optional[dict] = None) -> dict:
    """Record that the customer approved the proof and release the order to
    printing (resumes the pipeline from the Gelato stage).
    """
    from datetime import datetime
    from quoteforge.automation.pipeline_orchestrator import resume_after_proof_approval
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found")
    # Record an immutable approval audit trail. This is the evidence that lets
    # you fairly deny "I changed my mind" / "I don't like it" after approval,
    # while still honouring genuine defects/damage (see resolution engine).
    approved_at = datetime.now().isoformat(timespec="seconds")
    # Parity gate: fingerprint the exact file being approved so the pre-Gelato
    # validation can prove the production file is the one the customer saw.
    from quoteforge.automation.print_quality import (file_sha256,
                                                     hashable_print_file)
    proof_hash = file_sha256(hashable_print_file(order)) if \
        hashable_print_file(order) else ""
    update_order(order_id, proof_approved=1, proof_approved_at=approved_at,
                 proof_file_hash=proof_hash)
    log_pipeline_stage(
        order_id, "proof", "customer_approved",
        f"Customer approved the proof at {approved_at}; "
        f"approved quote+artwork on record"
        + (f"; file sha256={proof_hash[:12]}..." if proof_hash else ""))
    return resume_after_proof_approval(
        order_id,
        gelato_product_uid=gelato_product_uid,
        recipient_address=recipient_address,
    )
