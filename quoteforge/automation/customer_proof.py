"""Owner proof-review / release helper (manual fail-safe).

The customer approves their design on screen at checkout - that on-screen
approval is the final, binding sign-off and is recorded as ``proof_approved``
when the order is created. There is NO emailed proof round.

This module is the manual fail-safe: for any order that reaches the proof stage
WITHOUT an on-screen approval on record, the owner reviews the proof here and
releases it to print (recording the approval via ``record_customer_approval``).
Printing stays blocked until that approval is recorded.
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
        f"Owner proof review - order {order_id}: {occasion} for {recipient}.\n\n"
        f"Check the name, spelling, wording, and overall design against the "
        f"order. If everything is correct, release it to print; if not, fix the "
        f"design before releasing. (Customers approve their design on screen at "
        f"checkout - this manual review is the fail-safe for any order that has "
        f"no on-screen approval on record.)"
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
        message += ("\n\nA preview of how the design looks on the garment is "
                    "attached as a visual aid for the review.")

    # Mark the order as held pending approval (printing is blocked here). The
    # status token is legacy; with the emailed proof round retired it now means
    # "held for owner review" - released via record_customer_approval.
    update_order(order_id, status="awaiting_customer_approval", proof_sent=1)
    log_pipeline_stage(order_id, "proof", "awaiting_customer",
                       "Proof prepared - held for owner review")

    return {
        "order_id": order_id,
        "recipient": recipient,
        "proof_message": message,
        "artwork_path": artwork_path or order.get("artwork_url", ""),
        "product_mockup": product_mockup,   # visual aid only; None when unavailable
        "instructions": (
            "Review the proof against the order. If it's correct, release it to "
            f"print with: python -m quoteforge.admin customer-approved {order_id}"
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
    # AUDIT M10: this path is the OWNER'S release command (admin customer-approved)
    # - the customer's approval was relayed off-channel, not captured on screen.
    # The log must say so: citing an owner-asserted release as on-screen customer
    # consent would be indefensible in a dispute. (The genuine on-screen consent
    # record is design_confirm: checklist + timestamp + stored proof PDF.)
    log_pipeline_stage(
        order_id, "proof", "customer_approved",
        f"Owner released to print at {approved_at} (customer approval relayed "
        f"off-channel via admin customer-approved; no on-screen record)"
        + (f"; file sha256={proof_hash[:12]}..." if proof_hash else ""))
    return resume_after_proof_approval(
        order_id,
        gelato_product_uid=gelato_product_uid,
        recipient_address=recipient_address,
    )
