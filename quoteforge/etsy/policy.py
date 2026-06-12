"""Etsy + Gelato policy engine.

Encodes what Etsy ALLOWS and what Gelato COVERS for each issue type, so every
return/refund decision (which always goes to a human) carries the real policy
facts and reporting window the owner needs to decide quickly and correctly.

Ground truth:
- Etsy: sellers may make personalized/made-to-order items final sale (no returns
  for change of mind / wrong personalization). BUT Etsy Purchase Protection can
  override shop policy and refund the buyer for "not received", "damaged", or
  "not as described" - so those carry real exposure even when policy says no.
- Gelato's quality guarantee COVERS: damage, misprints, production defects, and
  lost-in-transit (within reporting windows). It does NOT cover: change of mind,
  wrong personalization entered by the buyer, or a wrong address the buyer gave.
"""
from dataclasses import dataclass

from quoteforge.config import POLICY_DEFECT_WINDOW_DAYS, POLICY_LOST_WINDOW_DAYS


@dataclass
class Policy:
    """Etsy/Gelato policy facts for one issue category."""
    category: str
    etsy_returnable: bool          # does Etsy require/allow a return here?
    etsy_protection_risk: bool     # could Etsy Purchase Protection force a refund?
    gelato_covered: bool           # does Gelato's guarantee pay for a reprint?
    report_window_days: int        # window the buyer must report within (0 = n/a)
    evidence_required: str         # what evidence to collect
    recommended: str               # the recommended resolution


# Keyed by the resolution-engine category.
POLICIES: dict[str, Policy] = {
    "changed_mind": Policy(
        "changed_mind", False, False, False, 0, "none",
        "Decline (personalized = final sale). No Gelato/Etsy obligation."),
    "wrong_personalization": Policy(
        "wrong_personalization", False, False, False, 0,
        "compare to checkout details",
        "Decline free fix (produced as ordered); offer a paid discounted reprint."),
    "approved_then_changed_mind": Policy(
        "approved_then_changed_mind", False, False, False, 0,
        "proof-approval record on file",
        "Decline (buyer approved the proof); cite the approval record."),
    "damaged_package": Policy(
        "damaged_package", False, True, True, POLICY_DEFECT_WINDOW_DAYS,
        "photos of item + packaging",
        "Free replacement via Gelato claim. Etsy Protection applies - resolve "
        "fast to avoid a forced refund."),
    "printing_error": Policy(
        "printing_error", False, True, True, POLICY_DEFECT_WINDOW_DAYS,
        "photo of the defect vs. the approved design",
        "Free replacement (production error). Gelato covers the reprint."),
    "poor_quality": Policy(
        "poor_quality", False, True, True, POLICY_DEFECT_WINDOW_DAYS,
        "photo showing the quality issue",
        "Free replacement via Gelato quality claim with the photo evidence."),
    "lost_package": Policy(
        "lost_package", False, True, True, POLICY_LOST_WINDOW_DAYS,
        "tracking history",
        "Investigate tracking; if lost past the window, Gelato reprints. Etsy "
        "'not received' Protection applies."),
    "wrong_address": Policy(
        "wrong_address", False, False, False, 0, "address entered at checkout",
        "Not covered by Gelato (buyer's address error). Offer a paid reprint + "
        "shipping; no free replacement or refund owed."),
    "cancellation": Policy(
        "cancellation", True, False, False, 0, "production status",
        "Refund ONLY if production hasn't started; once in production it's "
        "personalized and final. Human decision."),
}


def policy_for(category: str) -> Policy | None:
    """Look up the Policy for an issue category (None if unmapped)."""
    return POLICIES.get(category)


def policy_facts(category: str) -> dict:
    """Structured policy facts for a category (for attaching to approvals)."""
    p = policy_for(category)
    if not p:
        return {"category": category, "known": False,
                "note": "No policy mapping - treat as a manual review."}
    return {
        "category": p.category, "known": True,
        "etsy_returnable": p.etsy_returnable,
        "etsy_protection_risk": p.etsy_protection_risk,
        "gelato_covered": p.gelato_covered,
        "report_window_days": p.report_window_days,
        "evidence_required": p.evidence_required,
        "recommended": p.recommended,
    }


def format_policy_text(category: str) -> str:
    """Render a category's policy facts as printable console text."""
    p = policy_for(category)
    if not p:
        return f"No policy mapping for '{category}' - manual review."
    yn = lambda b: "yes" if b else "no"
    window = (f"{p.report_window_days} days" if p.report_window_days
              else "n/a")
    return "\n".join([
        f"POLICY - {p.category}",
        f"  Etsy: returnable={yn(p.etsy_returnable)}, "
        f"Purchase-Protection risk={yn(p.etsy_protection_risk)}",
        f"  Gelato covers reprint : {yn(p.gelato_covered)}",
        f"  Report window         : {window}",
        f"  Evidence required     : {p.evidence_required}",
        f"  Recommended           : {p.recommended}",
    ])
