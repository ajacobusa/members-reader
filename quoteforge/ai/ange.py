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
     "Always. The live preview shows exactly what prints, and we email a FREE "
     "digital proof too - spot anything off, reply right away and we fix it "
     "before printing."),
    (["ship", "shipping", "delivery", "how long", "arrive", "turnaround", "fast"],
     "How long does it take?",
     "We email your proof within about a day and double-check every file, then "
     "it's printed and shipped with tracking - typically 3-6 business days. "
     "Watch for the \"order by\" date near big holidays."),
    (["return", "refund", "guarantee", "not happy", "wrong"],
     "What if I'm not happy?",
     "We stand behind every piece with our happiness guarantee - if something "
     "isn't right, message us and we'll make it right. (Each item is "
     "personalized and made to order from the design you approved.) For "
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
    (["pet", "dog", "cat", "memorial", "remembrance", "loss"],
     "Can you make a pet or memorial piece?",
     "Yes - pet portraits and memorial keepsakes are some of our most loved "
     "pieces. Upload a clear photo and add your words; we'll send a free proof."),
    (["color", "colour", "background", "font", "change colors"],
     "Can I choose colors and fonts?",
     "Yes! On each product you can preview different background colors, text "
     "colors and fonts live, and we confirm everything on your free proof."),
    (["subscription", "membership", "monthly", "club"],
     "Do you offer a subscription?",
     "We do - a membership delivers a fresh personalized piece on a schedule "
     "(quarterly, half-year or annual). A lovely ongoing gift."),
    (["track", "tracking", "where is", "status"],
     "Can I track my order?",
     "Yes, every order ships with tracking. For the status of a specific order, "
     "message the team and we'll look it up for you."),
    (["digital", "download", "printable", "file"],
     "Do you sell digital downloads?",
     "Selected designs are available as instant printable digital files - a "
     "great budget or last-minute option. Check the product options."),
    (["international", "worldwide", "country", "outside us"],
     "Do you ship internationally?",
     "Yes - we ship worldwide with tracking via our global print network, so "
     "your order is produced close to the destination where possible."),
    (["care", "clean", "wash", "maintain", "fade", "last"],
     "How do I care for it?",
     "Wipe gently with a soft, dry (or barely damp) cloth - no harsh cleaners. "
     "Hang out of direct, harsh sunlight to keep colors vivid for years. "
     "Canvas and acrylic just need an occasional light dusting."),
    (["when", "in time", "deadline", "order by", "before christmas", "rush",
      "how soon"],
     "Will it arrive in time?",
     "We send your proof within ~1 day; after you approve, it prints and ships "
     "(typically 3-6 business days). Near big holidays, watch the 'order by' "
     "date on the site, and message us if it's urgent - we'll do our best."),
    (["what size", "which size", "how big should", "wall", "room", "recommend size"],
     "What size should I get?",
     "For a desk, nightstand or gallery wall, 8x10-11x14 is perfect. For above a "
     "sofa, bed or as a statement piece, go 16x20-24x36. Tell me the spot and "
     "I'll suggest a size!"),
    (["pay", "payment", "paypal", "card", "afterpay", "klarna"],
     "What payment methods can I use?",
     "Payment is completed via our secure checkout - credit/debit cards, "
     "PayPal, Apple Pay or Google Pay. You never enter card details on this "
     "site."),
    (["how long", "processing", "make time", "production"],
     "How long does it take to make?",
     "Because each piece is personalized and made to order: proof within ~1 day, "
     "then production + tracked shipping, usually 3-6 business days after you "
     "approve the proof."),
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
