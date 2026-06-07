"""'Ask Ange' - the shop's AI assistant for high-level customer questions.

Two layers, same knowledge base (KB) so answers are consistent:
  * answer()    - instant, deterministic keyword match (used by the on-page
                  widget; no API key, works offline, safe on a static site).
  * ask_ange()  - Claude, grounded ONLY in the KB + shop facts, with the
                  deterministic answer as fallback (used by the `ask` command /
                  optional webhook endpoint for richer phrasing).

Ange only answers general questions (frames, sizes, personalization, shipping,
returns, etc.) and always defers order-specific or refund issues to a human.
"""
from __future__ import annotations

# (keywords, question, answer). Grounded in the actual shop policies.
KB = [
    (["frame", "framed", "included", "frame included"],
     "Is a frame included?",
     "Poster, canvas, acrylic and metal ship WITHOUT a frame. If you'd like it "
     "framed, choose the \"Framed\" material at checkout and pick your frame "
     "style (6 options, from a slim black to premium oak, walnut or gold)."),
    (["size", "sizes", "dimensions", "how big"],
     "What sizes do you offer?",
     "Sizes range from 8x10 up to 24x36 inches depending on the material. You "
     "pick the size (and quantity) right on the product page."),
    (["personalize", "custom", "wording", "name", "text", "quote", "message"],
     "Can I personalize it?",
     "Yes - that's our specialty. Add the recipient's name, the occasion, and "
     "your own words. You can even preview your colors, font and frame live "
     "before you buy."),
    (["photo", "upload", "picture", "image", "my own"],
     "Can I use my own photo?",
     "Absolutely. Upload a high-resolution photo (JPG, PNG, PDF or TIFF). We "
     "auto-check the quality and, if it's too low for a sharp print, we'll ask "
     "for a better version before anything prints."),
    (["proof", "approve", "see before", "preview"],
     "Do I see it before it prints?",
     "Always. We send a FREE digital proof and nothing prints until you approve "
     "it - so it's exactly right."),
    (["ship", "shipping", "delivery", "how long", "arrive", "turnaround", "fast"],
     "How long does it take?",
     "We send your proof within about a day; once you approve, it's printed and "
     "shipped with tracking - typically 3-6 business days. Watch for the "
     "\"order by\" date near big holidays."),
    (["return", "refund", "guarantee", "not happy", "wrong"],
     "What if I'm not happy?",
     "We stand behind every piece with our happiness guarantee - if something "
     "isn't right, message us and we'll make it right. (Because each item is "
     "personalized and made to order, approval happens on your free proof.) For "
     "a specific order issue, a team member will help you personally."),
    (["material", "materials", "canvas", "acrylic", "metal", "paper", "quality"],
     "What materials are available?",
     "Premium poster prints, gallery-wrapped canvas, framed prints, acrylic and "
     "metal - all museum-quality, made to order."),
    (["gift", "ecard", "e-card", "gift card", "send a gift", "surprise"],
     "Can I send it as a gift?",
     "Yes! Add a gift e-card and we'll send your recipient a beautiful "
     "announcement with a free personal note - perfect for surprises and "
     "last-minute or long-distance gifts."),
    (["price", "cost", "discount", "bundle", "how much", "cheaper"],
     "How much does it cost / are there discounts?",
     "Prices depend on material and size (shown live as you choose). Order more "
     "than one and a quantity discount applies automatically - great for "
     "gallery sets or gifting several people."),
    (["bulk", "wholesale", "corporate", "business", "many", "b2b"],
     "Do you do bulk / corporate orders?",
     "Yes - we offer wholesale pricing for corporate gifts, weddings, realtors, "
     "churches and schools. Use the 'Corporate & bulk gifting' form and we'll "
     "send a quote."),
]

FALLBACK = ("Great question! I'm Ange, the {shop} assistant. For anything "
            "order-specific (or a refund/return), the best step is to message "
            "the team directly - tap \"Message us\" and a real person will help.")


def answer(question: str) -> dict:
    """Deterministic best-match answer. Returns {'matched': bool, 'answer': str}."""
    from quoteforge.config import SHOP_NAME
    q = (question or "").lower()
    best, best_score = None, 0
    for keywords, _, ans in KB:
        score = sum(1 for k in keywords if k in q)
        if score > best_score:
            best, best_score = ans, score
    if best and best_score >= 1:
        return {"matched": True, "answer": best}
    return {"matched": False, "answer": FALLBACK.format(shop=SHOP_NAME)}


def ask_ange(question: str) -> dict:
    """Claude-grounded answer (KB as the only source); deterministic fallback.
    TEST_MODE / no key -> deterministic answer."""
    from quoteforge.config import SHOP_NAME
    det = answer(question)
    kb_text = "\n".join(f"- {q} {a}" for _, q, a in KB)
    from quoteforge.ai.assistant import ai_text
    prompt = (
        f"You are Ange, the warm, concise assistant for {SHOP_NAME}, a "
        f"personalized wall-art shop. Answer the customer ONLY using these "
        f"facts; if it's order-specific or about a refund/return, tell them a "
        f"team member will help and to message the shop. Keep it to 2-3 "
        f"sentences.\n\nFACTS:\n{kb_text}\n\nCUSTOMER: {question}\n\nAnge:")
    text = ai_text(prompt, operation="ask_ange", max_tokens=200,
                   mock=det["answer"])
    return {"answer": text or det["answer"], "matched": det["matched"]}


def kb_for_web() -> list:
    """Compact KB for the on-page widget: [{'q','k','a'}]."""
    return [{"q": q, "k": keywords, "a": a} for keywords, q, a in KB]
