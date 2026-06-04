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

    message = (
        f"Hi! Thank you so much for your order. I've created the proof for your "
        f"personalized {occasion} print for {recipient} — please review it.\n\n"
        f"Take a look at the attached image and check the name, spelling, "
        f"wording, and overall design. If everything looks perfect, just reply "
        f"\"APPROVED\" and I'll send it to print right away. If you'd like any "
        f"changes, tell me and I'll update it — no rush, and no extra charge."
    )

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
        "instructions": (
            "Send the proof_message to the buyer in the Etsy order conversation "
            "and attach the artwork image. When they reply APPROVED, run: "
            f"python -m quoteforge.admin customer-approved {order_id}"
        ),
    }


def record_customer_approval(order_id: str,
                             gelato_product_uid: str = "",
                             recipient_address: Optional[dict] = None) -> dict:
    """Record that the customer approved the proof and release the order to
    printing (resumes the pipeline from the Gelato stage).
    """
    from quoteforge.automation.pipeline_orchestrator import resume_after_proof_approval
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found")
    log_pipeline_stage(order_id, "proof", "customer_approved",
                       "Customer approved the proof")
    return resume_after_proof_approval(
        order_id,
        gelato_product_uid=gelato_product_uid,
        recipient_address=recipient_address,
    )
