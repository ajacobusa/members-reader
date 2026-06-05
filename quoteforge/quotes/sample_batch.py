"""Quote-quality review harness.

The reviewer's #1 watch-item: "Will customers love the generated messages?"
This generates representative sample quotes across the emotional categories that
matter most (daughter/son graduation, wedding, anniversary, memorial, Christian
encouragement) so you can review them CRITICALLY before launch and ask:
"Would a parent pay $50-$100 for this?"

With a real ANTHROPIC_API_KEY it generates REAL Claude quotes (force_real);
otherwise it uses the TEST_MODE mock so the harness is always runnable.
"""
from dataclasses import dataclass


@dataclass
class SampleScenario:
    label: str
    relationship: str
    recipient_name: str
    sender_name: str
    occasion: str
    memory_or_story: str
    scenery: str
    output_style: str = "Personal Letter"


# The high-intent emotional categories from the launch strategy.
SCENARIOS: list[SampleScenario] = [
    SampleScenario("Daughter - Graduation", "To My Daughter", "Emma", "Mom",
                   "Graduation",
                   "She worked nights and studied hard for four years to become a nurse.",
                   "Mountain sunrise"),
    SampleScenario("Son - Graduation", "To My Son", "Liam", "Dad", "Graduation",
                   "He never gave up, even when the engineering program got hard.",
                   "Ocean horizon"),
    SampleScenario("Wedding - To Wife", "To My Wife", "Sarah", "James", "Wedding",
                   "From our first coffee to forever - today I marry my best friend.",
                   "Golden field"),
    SampleScenario("Anniversary - To Husband", "To My Husband", "James", "Sarah",
                   "Anniversary",
                   "Twenty-five years, three kids, and I'd choose you again every time.",
                   "Forest path"),
    SampleScenario("Memorial - In Memory Of", "In Memory Of", "Grandma Rose",
                   "The Family", "Memorial / In Memory Of",
                   "Her kitchen always smelled like cinnamon and her hugs felt like home.",
                   "Soft clouds"),
    SampleScenario("Christian - Encouragement", "To My Friend", "Grace", "Anna",
                   "Just Because",
                   "Through every storm she kept her faith and lifted everyone around her.",
                   "Sunlit path"),
]


def generate_sample_batch(force_real: bool = False,
                          per_scenario: int = 1) -> list[dict]:
    """Generate sample quotes for each scenario. Returns a list of results."""
    from quoteforge.quotes.generator import generate_personal_message
    out: list[dict] = []
    for sc in SCENARIOS:
        try:
            variations = generate_personal_message(
                relationship=sc.relationship, recipient_name=sc.recipient_name,
                sender_name=sc.sender_name, occasion=sc.occasion,
                memory_or_story=sc.memory_or_story, scenery=sc.scenery,
                output_style=sc.output_style, count=per_scenario,
                force_real=force_real)
            out.append({"label": sc.label, "ok": True,
                        "quotes": list(variations)})
        except Exception as exc:  # noqa: BLE001
            out.append({"label": sc.label, "ok": False,
                        "error": f"{type(exc).__name__}: {exc}", "quotes": []})
    return out


def format_batch_text(results: list[dict], real: bool) -> str:
    head = ("REAL AI quotes" if real else "MOCK quotes (set ANTHROPIC_API_KEY "
            "for real ones)")
    lines = ["=" * 64, f"QUOTE QUALITY REVIEW - {head}", "=" * 64]
    for r in results:
        lines.append(f"\n### {r['label']}")
        if not r["ok"]:
            lines.append(f"  [ERROR] {r['error']}")
            continue
        for i, q in enumerate(r["quotes"], 1):
            lines.append(f"  ({i}) {q}")
    lines.append("\n" + "=" * 64)
    lines.append("Review critically: would a parent pay $50-$100 for this?")
    lines.append("=" * 64)
    return "\n".join(lines)
