"""Autopilot — autonomous decision bots with a human-approval safety gate.

Philosophy: automate every decision the business makes, and pull a human in ONLY
when it genuinely matters. A decision is auto-executed when ALL of these hold:

  * the classifier is confident       (>= AUTOPILOT_CONFIDENCE_THRESHOLD)
  * no money leaves the business       (<= AUTOPILOT_MAX_AUTO_REFUND, default $0)
  * the risk is not 'high'
  * the order isn't high-value         (<= AUTOPILOT_HIGH_VALUE_ORDER)

Otherwise the bot stages the decision in the human-approval queue with its full
rationale, so the owner just clicks approve/reject. This keeps refunds, spends,
disputes, and ambiguous cases under human control while everything routine —
free defect/damage replacements, clear policy denials, lost-package reprints —
happens automatically.

What is NEVER automated (by design, regardless of settings):
  * issuing refunds / spending money beyond the cap
  * approving the customer's proof (that's the BUYER's decision)
  * flipping TEST_MODE / going live and physical sample sign-off
"""
import json
import logging
from dataclasses import dataclass, asdict, field

from quoteforge.config import (
    AUTOPILOT_ENABLED, AUTOPILOT_CONFIDENCE_THRESHOLD,
    AUTOPILOT_MAX_AUTO_REFUND, AUTOPILOT_HIGH_VALUE_ORDER, AUTOPILOT_USE_LLM,
    DEFAULT_SALE_PRICE,
)
from quoteforge.etsy.resolution import resolve_issue, ISSUE_CASES, _ALIASES

logger = logging.getLogger(__name__)


@dataclass
class AutoDecision:
    """One autopilot ruling on a customer issue: what to do, at what risk/cost,
    and whether it executes automatically or escalates to a human."""
    category: str
    title: str
    action: str            # machine action key
    decision: str          # human-readable outcome
    confidence: float
    risk: str              # low | medium | high
    money_out: float       # USD the business would spend (0 if Gelato-covered)
    auto: bool             # will it execute without a human?
    reason: str            # why auto / why escalated
    customer_message: str
    policy: dict = field(default_factory=dict)  # Etsy/Gelato policy facts


# ── Classifier ───────────────────────────────────────────────────

def classify_issue(text: str) -> tuple[str, float]:
    """Map free-text customer issue → (category, confidence 0..1).

    Keyword/alias based by default (deterministic, no API). If AUTOPILOT_USE_LLM
    and a key is set, Claude is used for fuzzy text and we keep its confidence.
    """
    raw = (text or "").strip().lower()
    if not raw:
        return ("", 0.0)
    # Exact category key wins outright.
    key = raw.replace(" ", "_")
    if key in ISSUE_CASES:
        return (key, 0.99)
    # Alias hits — collect distinct categories matched.
    hits = {cat for phrase, cat in _ALIASES.items() if phrase in raw}
    if len(hits) == 1:
        return (next(iter(hits)), 0.88)
    if len(hits) > 1:
        # Ambiguous — pick the first but flag low confidence for escalation.
        return (sorted(hits)[0], 0.5)
    if AUTOPILOT_USE_LLM:
        llm = _llm_classify(text)
        if llm:
            return llm
    return ("", 0.0)


def _llm_classify(text: str) -> tuple[str, float] | None:  # pragma: no cover
    """Optional Claude classifier. Returns (category, confidence) or None."""
    try:
        from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
        if not ANTHROPIC_API_KEY:
            return None
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        cats = ", ".join(ISSUE_CASES.keys())
        msg = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=60,
            messages=[{"role": "user", "content":
                f"Classify this customer message into exactly one category "
                f"[{cats}] and give confidence 0-1. Reply as JSON "
                f'{{"category":..,"confidence":..}} only.\n\nMessage: {text}'}],
        )
        data = json.loads(msg.content[0].text)
        if data.get("category") in ISSUE_CASES:
            return (data["category"], float(data.get("confidence", 0.7)))
    except Exception:
        return None
    return None


# ── Decision policy ──────────────────────────────────────────────

def _risk_and_money(res: dict, order: dict | None) -> tuple[str, float]:
    """Return (risk, money_out) for a recognised resolution."""
    # Cancellation before production = a real refund (money out).
    if res["category"] == "cancellation":
        price = (order or {}).get("sale_price") or DEFAULT_SALE_PRICE
        return ("high", float(price))
    # Free replacements are Gelato-covered → no money out of OUR pocket.
    if res["gelato_covered"]:
        return ("low", 0.0)
    # Customer-fault denials cost nothing and just send a polite 'no'.
    if res["fault"] == "customer":
        return ("low", 0.0)
    return ("medium", 0.0)


# Categories whose outcome can involve money back / accepting a return.
# These ALWAYS require human approval, regardless of any other setting.
MONEY_BACK_CATEGORIES = {"cancellation"}
# Words that signal the customer is asking for money back / a return, even if
# the issue is otherwise classified (e.g. "it's damaged, I want a refund").
REFUND_KEYWORDS = ("refund", "return", "money back", "money-back",
                   "chargeback", "reimburse", "my money", "give me back")


def involves_money_back(issue_text: str, category: str) -> bool:
    """True if this is a refund/return — which is ALWAYS a human decision."""
    if category in MONEY_BACK_CATEGORIES:
        return True
    low = (issue_text or "").lower()
    return any(k in low for k in REFUND_KEYWORDS)


def auto_replacement_block_reason(res: dict, order: dict | None) -> str | None:
    """Why a Gelato-covered replacement must NOT auto-file (None if it may).

    A free reprint is only auto-filed when it is actually file-ready with the
    supplier: covered, inside the supplier window, and with every mandatory
    photo on file. We defer to ``build_claim_package`` - the SAME logic that
    actually files the claim - so the auto-file gate and the filing path can
    never drift (one evidence table, one window definition). Anything not
    ready_to_file goes to a human (manual review). With no order in context
    nothing is filed, so there is nothing to gate."""
    if not order:
        return None
    from quoteforge.fulfillment.gelato_returns import build_claim_package
    pkg = build_claim_package(order, res.get("category", ""))
    if pkg["ready_to_file"]:
        return None
    if pkg["missing_photos"]:
        return ("claim needs photo evidence "
                f"({', '.join(pkg['missing_photos'])}) - manual review")
    if not pkg["within_gelato_window"]:
        return "claim reported past the supplier window - manual review"
    return "claim not ready to auto-file with the supplier - manual review"


def decide(issue_text: str, order: dict | None = None) -> AutoDecision:
    """Full decision: classify, resolve, and apply the auto/escalate policy."""
    category, confidence = classify_issue(issue_text)
    res = resolve_issue(category, order) if category else {"recognized": False}

    from quoteforge.etsy.policy import policy_facts
    cat = res.get("category", "")

    # HARD RULE: any return or money-back request is never automated. This fires
    # even for unrecognised issues and overrides confidence/caps/everything.
    # The Etsy/Gelato policy facts ride along so the human can decide quickly.
    if involves_money_back(issue_text, cat):
        return AutoDecision(
            category=cat or "refund_or_return",
            title="Return / refund request",
            action="escalate", decision="Refund/return - human approval required",
            confidence=confidence, risk="high",
            money_out=(order or {}).get("sale_price") or DEFAULT_SALE_PRICE,
            auto=False,
            reason="returns and money-back ALWAYS require human approval",
            customer_message=res.get("message", ""),
            policy=policy_facts(cat) if cat else {})

    if not res.get("recognized"):
        return AutoDecision(
            category="unknown", title="Unrecognised issue", action="escalate",
            decision="Needs human classification", confidence=confidence,
            risk="high", money_out=0.0, auto=False,
            reason="Could not classify the issue with confidence",
            customer_message="")

    risk, money_out = _risk_and_money(res, order)
    high_value = bool(order) and (
        (order.get("sale_price") or 0) > AUTOPILOT_HIGH_VALUE_ORDER)

    reasons = []
    if not AUTOPILOT_ENABLED:
        reasons.append("autopilot disabled")
    if confidence < AUTOPILOT_CONFIDENCE_THRESHOLD:
        reasons.append(f"confidence {confidence:.2f} < "
                       f"{AUTOPILOT_CONFIDENCE_THRESHOLD:.2f}")
    if money_out > AUTOPILOT_MAX_AUTO_REFUND:
        reasons.append(f"would spend ${money_out:.2f} > cap "
                       f"${AUTOPILOT_MAX_AUTO_REFUND:.2f}")
    if risk == "high":
        reasons.append("high-risk decision")
    if high_value:
        reasons.append(f"high-value order > ${AUTOPILOT_HIGH_VALUE_ORDER:.0f}")
    # A Gelato-covered free replacement only auto-files with evidence on file and
    # inside the window; otherwise it must go to a human (manual review).
    if res["gelato_covered"]:
        block = auto_replacement_block_reason(res, order)
        if block:
            reasons.append(block)

    auto = not reasons
    action = ("auto_replacement" if res["gelato_covered"]
              else "auto_decline" if res["fault"] == "customer"
              else "escalate")
    return AutoDecision(
        category=res["category"], title=res["title"], action=action,
        decision=res["decision"], confidence=confidence, risk=risk,
        money_out=money_out, auto=auto,
        reason="all gates passed - auto-executing" if auto
               else "escalated to human: " + "; ".join(reasons),
        customer_message=res["message"], policy=policy_facts(res["category"]))


# ── Execution ────────────────────────────────────────────────────

def handle_issue(issue_text: str, order_id: str | None = None,
                 execute: bool = True) -> dict:
    """Decide and either auto-execute or queue for human approval."""
    from quoteforge.db.database import (
        init_db, get_order, enqueue_approval, save_customer_message,
    )
    init_db()
    order = get_order(order_id) if order_id else None
    d = decide(issue_text, order)
    payload = json.dumps({"order_id": order_id, "action": d.action,
                          "category": d.category})

    if d.auto and execute:
        _execute(d, order_id)
        enqueue_approval(
            kind="issue", ref=order_id or "", summary=f"{d.title} → {d.decision}",
            proposed_action=d.action, payload=payload, confidence=d.confidence,
            risk=d.risk, status="auto", decided_by="autopilot")
        return {"outcome": "auto-executed", "decision": asdict(d)}

    # Escalate — stage for human sign-off, with the policy recommendation inline.
    rec = d.policy.get("recommended", "") if d.policy else ""
    summary = f"{d.title} → {d.decision}" + (f" | Policy: {rec}" if rec else "")
    aid = enqueue_approval(
        kind="issue", ref=order_id or "", summary=summary,
        proposed_action=d.action,
        payload=json.dumps({"order_id": order_id, "action": d.action,
                            "category": d.category, "policy": d.policy}),
        confidence=d.confidence, risk=d.risk, status="pending")
    return {"outcome": "queued_for_human", "approval_id": aid,
            "decision": asdict(d)}


def _execute(d: AutoDecision, order_id: str | None) -> None:
    """Carry out an auto-approved action (idempotent, best-effort)."""
    from quoteforge.db.database import save_customer_message, update_order
    if not order_id:
        return
    # Stage the customer reply for dispatch (auto-sends if a channel is wired).
    save_customer_message(order_id, f"resolution:{d.category}",
                          d.customer_message, sent=False)
    if d.action == "auto_replacement":
        # AUDIT H5/M11: the old path called the stub file_replacement_claim (which
        # files NOTHING) and wrote "replacement_filed" into the LIFECYCLE status
        # column - promising the customer a replacement that no one would ever see
        # (the claim queue reads claim_status, not status). Stage it where the
        # humans actually work: claim_status='supplier_review' (the claim queue +
        # digest key on claim_status), leave the fulfillment status machine alone,
        # and alert the owner so the real vendor claim gets filed same-day.
        update_order(order_id, claim_status="supplier_review")
        try:
            from quoteforge.admin import _alert
            _alert(f"Replacement approved - {order_id}",
                   f"Autopilot approved a free replacement for {order_id} "
                   f"({d.category}). File the vendor claim and place the "
                   f"replacement order - the claim queue row is "
                   f"claim_status=supplier_review.",
                   f"replacement alert for {order_id}")
        except Exception as exc:  # noqa: BLE001 - alert is best-effort
            logger.warning("autopilot replacement alert failed for %s: %s",
                           order_id, exc)
    elif d.action == "auto_decline":
        # Claim adjudication lives in claim_status; the lifecycle status column
        # keeps tracking the physical order (delivered etc.) untouched.
        update_order(order_id, claim_status="denied_customer_fault")


def execute_approved(approval_id: int) -> dict:
    """Owner approved a queued decision — run it now."""
    from quoteforge.db.database import get_approval, resolve_approval
    a = get_approval(approval_id)
    if not a:
        return {"status": "not_found"}
    if a["status"] != "pending":
        return {"status": "already_" + a["status"]}
    payload = json.loads(a["payload"] or "{}")
    d = AutoDecision(
        category=payload.get("category", ""), title=a["summary"],
        action=a["proposed_action"], decision=a["summary"],
        confidence=a["confidence"], risk=a["risk"], money_out=0.0, auto=False,
        reason="human-approved", customer_message="")
    # Re-derive the customer message from the resolution engine.
    res = resolve_issue(d.category)
    if res.get("recognized"):
        d.customer_message = res["message"]
    # AUDIT A12: only replacement/decline actions have a real effect in _execute.
    # An "escalate" (or unknown) action performs nothing - report that honestly
    # instead of claiming "executed" (the owner would believe something happened).
    if d.action in ("auto_replacement", "auto_decline"):
        _execute(d, a["ref"] or None)
        resolve_approval(approval_id, "approved")
        return {"status": "executed", "approval": approval_id}
    resolve_approval(approval_id, "approved")
    return {"status": "approved_no_action", "approval": approval_id,
            "detail": f"action '{d.action}' has no automated effect - "
                      "handle it manually"}


def autopilot_status() -> dict:
    """Summary for the daily digest: pending approvals + recent auto actions."""
    from quoteforge.db.database import get_pending_approvals, _conn
    pending = get_pending_approvals()
    with _conn() as conn:
        auto_24h = conn.execute(
            "SELECT COUNT(*) FROM approvals WHERE status='auto' "
            "AND created_at >= datetime('now','-1 day')").fetchone()[0]
    return {"pending_human": len(pending), "auto_last_24h": auto_24h,
            "pending": pending}
