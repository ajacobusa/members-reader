"""Generate a self-contained HTML preview of a listing as buyers would see it.

Renders an Etsy-style product page (gallery + title + price + personalization +
description) from a launch-kit listing, with all images base64-embedded so the
single .html file opens anywhere via a file:// URL - for review/comment.
"""
import base64
import hashlib
from io import BytesIO
from pathlib import Path


def _b64(path: Path) -> str:
    """Inline a PNG as a base64 data-URI (self-contained pages, no asset files)."""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _analytics_snippet() -> str:
    """Google Analytics + Microsoft Clarity tags, from config. Empty if unset."""
    from quoteforge.config import GA_MEASUREMENT_ID, CLARITY_PROJECT_ID
    parts = []
    if GA_MEASUREMENT_ID:
        parts.append(
            f'<script async src="https://www.googletagmanager.com/gtag/js?id='
            f'{GA_MEASUREMENT_ID}"></script><script>window.dataLayer=window.'
            f'dataLayer||[];function gtag(){{dataLayer.push(arguments);}}'
            f"gtag('js',new Date());gtag('config','{GA_MEASUREMENT_ID}');</script>")
    if CLARITY_PROJECT_ID:
        parts.append(
            '<script>(function(c,l,a,r,i,t,y){c[a]=c[a]||function(){'
            '(c[a].q=c[a].q||[]).push(arguments)};t=l.createElement(r);'
            't.async=1;t.src="https://www.clarity.ms/tag/"+i;'
            'y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);})'
            f'(window,document,"clarity","script","{CLARITY_PROJECT_ID}");</script>')
    return "".join(parts)


def _web_img(path: Path, max_dim: int = 900, quality: int = 82) -> str:
    """Downscaled JPEG data-URI so the shared page loads fast (small payload)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _reviews_section() -> str:
    """Real, verified reviews only. Empty until you have published reviews
    (no fabricated social proof)."""
    from quoteforge.db.database import init_db, get_published_reviews, review_stats
    init_db()
    revs = get_published_reviews(12)
    if not revs:
        return ""
    st = review_stats()
    stars = "★" * int(round(st["avg"])) + "☆" * (5 - int(round(st["avg"])))
    cards = []
    for r in revs:
        rs = "★" * int(r["rating"]) + "☆" * (5 - int(r["rating"]))
        photo = (f'<img class="rvimg" src="{r["photo_url"]}" alt="">'
                 if r.get("photo_url") else "")
        vb = '<span class="vrf">✓ Verified</span>' if r.get("verified") else ""
        cards.append(
            f'<div class="rvcard"><div class="rvstars">{rs}</div>{photo}'
            f'<div class="rvtext">{(r.get("text") or "")[:240]}</div>'
            f'<div class="rvname">- {r.get("customer_name") or "Customer"} {vb}</div></div>')
    return (
        f'<div class="reviews"><h2>What customers say</h2>'
        f'<div class="rvsum"><span class="rvbig">{st["avg"]}</span>'
        f'<span class="rvstars">{stars}</span>'
        f'<span class="rvn">{st["count"]} verified review'
        f'{"s" if st["count"] != 1 else ""}</span></div>'
        f'<div class="rvgrid">{"".join(cards)}</div></div>')


# Rich "Shop by occasion" showcase: warm subtitle + emoji + soft gradient, with a
# real lifestyle photo when one is provided in the occasions image folder.
# (name, subtitle, emoji, gradient)
# Owner-curated "Editor's pick" designs - HONEST editorial recommendations (not
# fabricated sales). A design is badged when any keyword here appears in its
# title or occasion. Edit this list to feature different designs; empty = none.
# (Once live, real bestsellers can drive this from order data.)
EDITOR_PICKS = ["graduation", "anniversary"]

OCCASION_SHOWCASE = [
    ("Birthday", "Celebrate their special day", "🎂", "linear-gradient(135deg,#f6e6c4,#fff7e6)"),
    ("Anniversary", "Celebrate your love story", "💍", "linear-gradient(135deg,#f3dcdc,#fbeeee)"),
    ("Wedding", "For their beautiful beginning", "💐", "linear-gradient(135deg,#e7efe6,#fbfdfa)"),
    ("Mother's Day", "Thank her for everything", "🌸", "linear-gradient(135deg,#f6d9e2,#fdeef3)"),
    ("Father's Day", "Honour the one who inspires", "🪶", "linear-gradient(135deg,#dde6ee,#f1f5f9)"),
    ("Valentine's Day", "Celebrate your special bond", "❤️", "linear-gradient(135deg,#f4c9cd,#fce7e9)"),
    ("Graduation", "Cheer their big achievement", "🎓", "linear-gradient(135deg,#dfe3ef,#f1f3fa)"),
    ("New Baby", "Welcome the little one", "🍼", "linear-gradient(135deg,#dce9f2,#eef6fb)"),
    ("Housewarming", "Bless their new home", "🏡", "linear-gradient(135deg,#dfe9df,#f0f6f0)"),
    ("Christmas", "Make the season magical", "🎄", "linear-gradient(135deg,#d8e6da,#f2eee0)"),
]


def _occasion_slug(name: str) -> str:
    """Filename-safe slug for an occasion ("Mother's Day" -> "mothers-day")."""
    return name.lower().replace("'", "").replace("’", "").replace(" ", "-")


def _occasion_showcase(kit_dir, external_assets: bool = False, assets=None) -> str:
    """Image+title+subtitle occasion cards (filter the grid on tap). Uses a real
    lifestyle photo if found in an occasions image folder; else an elegant
    gradient + emoji so it never looks broken or 'computer-generated'.

    In external_assets mode the photos are written to the assets folder and
    referenced by URL (keeps the HTML small); otherwise a compact inline JPEG."""
    import os
    from quoteforge.config import OUTPUT_DIR
    # where to look for occasion lifestyle photos
    search_dirs = [Path(os.getenv("OCCASION_IMG_DIR", "").strip() or "."),
                   Path(kit_dir) / "occasions",
                   Path(OUTPUT_DIR) / "occasions",
                   Path(__file__).resolve().parents[2] / "brand" / "occasions"]
    cards = []
    for name, sub, emoji, grad in OCCASION_SHOWCASE:
        slug = _occasion_slug(name)
        img = None
        for d in search_dirs:
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                p = d / f"{slug}{ext}"
                if p.exists():
                    try:
                        if external_assets and assets is not None:
                            assets.mkdir(parents=True, exist_ok=True)
                            _save_web_jpg(p, assets / f"occasion-{slug}.jpg", 700, 78)
                            img = f"assets/occasion-{slug}.jpg"
                        else:
                            img = _web_img(p, 560, 72)   # compact inline (light page)
                    except Exception:  # noqa: BLE001
                        img = None
                    break
            if img:
                break
        media = (f'<img class="ocimg" loading="lazy" src="{img}" alt="{name} gift idea">'
                 if img else
                 f'<div class="ocimg ocfallback" style="background:{grad}">'
                 f'<span class="ocemoji">{emoji}</span></div>')
        # Escape apostrophes so names like "Mother's Day" don't close the JS string
        # (an unescaped ' in the onclick makes the whole handler a syntax error).
        name_js = name.replace("\\", "\\\\").replace("'", "\\'")
        cards.append(
            f'<button class="occard" aria-label="Shop {name} gifts" '
            f'onclick="shopByOccasion(\'{name_js}\',this)">{media}'
            f'<div class="occap"><div class="octitle">{name}</div>'
            f'<div class="ocsub">{sub}</div></div></button>')
    return ('<div class="occasions" id="occasions"><h2>Shop by occasion</h2>'
            '<p class="ocintro">Find the perfect personalized gift for the moment '
            'that matters - tap an occasion to explore.</p>'
            f'<div class="ocgrid">{"".join(cards)}</div>'
            '<div class="ocall"><button class="occhip sel" '
            'onclick="shopByOccasion(\'\',this)">Show all designs</button></div></div>')


def _service_request_form() -> str:
    """Customer-facing service-request form (damage/defect/wrong/missing/lost).
    Collects name, order number, email, optional phone, issue type, description,
    photos, delivery date, and an accuracy consent. Submits as a structured
    email (static-site fallback) and shows the individual-review acknowledgement.
    Never names the marketplace or the production partner on the customer page."""
    from quoteforge.fulfillment.claim_service import ISSUE_TYPES, CUSTOMER_ACK
    opts = "".join("<option>" + t + "</option>" for t in ISSUE_TYPES)
    ack = CUSTOMER_ACK.replace('"', "&quot;")
    # Plain (non-f) string so JS braces need no escaping; OWNER is a JS global
    # defined later in the page (resolved at submit time).
    form = (
        '<div class="faqs srf" id="service"><h2>Need help with an order?</h2>'
        '<p class="policyintro">Tell us what went wrong and we will review it - '
        'because every item is custom-made, each request is reviewed '
        'individually.</p>'
        '<div id="sr_form" class="srform">'
        '<label>Your name*<input id="sr_name" type="text" autocomplete="name"></label>'
        '<label>Order number*<input id="sr_order" type="text" '
        'placeholder="from your order confirmation"></label>'
        '<label>Email on the order*<input id="sr_email" type="email" '
        'autocomplete="email"></label>'
        '<label>Phone (optional)<input id="sr_phone" type="tel"></label>'
        '<label>Issue type*<select id="sr_issue">' + opts + '</select></label>'
        '<label>What happened?*<textarea id="sr_desc" rows="4"></textarea></label>'
        '<label>Delivery date (helpful)<input id="sr_delivery" type="date"></label>'
        '<label>Preferred resolution (optional)<select id="sr_resolution">'
        '<option value="">No preference</option><option>Replacement</option>'
        '<option>Refund</option></select></label>'
        '<label class="srfile">Product photo(s) <span>- required for '
        'damage/defect/wrong item</span><input id="sr_ph_product" type="file" '
        'accept="image/*" multiple></label>'
        '<label class="srfile">Packaging photo(s) <span>- required for '
        'damage</span><input id="sr_ph_pkg" type="file" accept="image/*" multiple></label>'
        '<label class="srconsent"><input id="sr_consent" type="checkbox"> '
        'I confirm the information above is accurate.</label>'
        '<div id="sr_status" class="srstatus" role="alert"></div>'
        '<button type="button" class="esecnext" onclick="_srSubmit()">'
        'Submit request</button></div>'
        '<div id="sr_done" class="srdone" style="display:none">' + ack + '</div>'
        '</div>')
    script = (
        "<script>(function(){"
        "function _srMsg(m){var s=document.getElementById('sr_status');"
        "if(s)s.textContent=m;}"
        "window._srSubmit=function(){"
        "var req=['sr_name','sr_order','sr_email','sr_issue','sr_desc'];"
        "for(var i=0;i<req.length;i++){var e=document.getElementById(req[i]);"
        "if(!e||!e.value.trim()){if(e)e.focus();"
        "_srMsg('Please complete all required fields (*).');return;}}"
        "if(!document.getElementById('sr_consent').checked){"
        "_srMsg('Please confirm the information is accurate.');return;}"
        "var g=function(id){var e=document.getElementById(id);"
        "return e?e.value.trim():'';};"
        "var done=function(){document.getElementById('sr_form').style.display='none';"
        "document.getElementById('sr_done').style.display='block';};"
        "var mailto=function(){var lines=['Customer service request','',"
        "'Name: '+g('sr_name'),'Order number: '+g('sr_order'),"
        "'Email: '+g('sr_email'),'Phone: '+g('sr_phone'),"
        "'Issue type: '+g('sr_issue'),'Delivery date: '+g('sr_delivery'),"
        "'Preferred resolution: '+g('sr_resolution'),"
        "'','Description:',g('sr_desc'),'',"
        "'(Please attach the product/packaging photos you selected to this email.)'];"
        "window.location.href='mailto:'+OWNER+'?subject='+"
        "encodeURIComponent('Service request - '+g('sr_order'))+"
        "'&body='+encodeURIComponent(lines.join('\\n'));};"
        # When a backend is configured, POST the request + photo files so it is
        # validated + documented automatically; otherwise fall back to email.
        "if(typeof SERVICE_API!=='undefined' && SERVICE_API){"
        "var fd=new FormData();"
        "var map={sr_name:'name',sr_order:'order_number',sr_email:'email',"
        "sr_phone:'phone',sr_issue:'issue_type',sr_desc:'description',"
        "sr_delivery:'delivery_date',sr_resolution:'preferred_resolution'};"
        "for(var k in map){fd.append(map[k],g(k));}fd.append('consent','1');"
        "var pp=document.getElementById('sr_ph_product');"
        "if(pp&&pp.files){for(var i=0;i<pp.files.length;i++)fd.append('product_photo',pp.files[i]);}"
        "var pk=document.getElementById('sr_ph_pkg');"
        "if(pk&&pk.files){for(var j=0;j<pk.files.length;j++)fd.append('packaging_photo',pk.files[j]);}"
        "_srMsg('Submitting...');"
        "fetch(SERVICE_API,{method:'POST',body:fd}).then(function(r){return r.json();})"
        ".then(function(){done();}).catch(function(){mailto();done();});return;}"
        "mailto();done();};})();</script>")
    return form + script


def _competitive_sections() -> str:
    """Conversion sections that beat mass printers: why-us comparison, a real
    happiness guarantee, and an FAQ. (Honest: no fabricated reviews pre-launch.)"""
    from quoteforge.config import SHOP_NAME
    rows = [
        ("Designed by a real person for your story", "Templated, mass-produced"),
        ("Approve your free proof on screen - exactly what prints", "What you upload is what prints"),
        ("Made to order, museum-quality materials", "Bulk factory runs"),
        ("Custom wording, colors &amp; frame - you preview it live", "Limited presets"),
        ("Personal note + gift e-card included free", "Add-on fees"),
        ("Damaged, defective or wrong? Free remake on us", "Rigid return windows"),
    ]
    cmp_rows = "".join(
        f'<tr><td class="us">✓ {u}</td><td class="them">{t}</td></tr>' for u, t in rows)
    faqs = [
        ("Is the frame included?",
         "Poster, canvas, acrylic and metal ship without a frame. Choose a "
         "\"Framed\" option to add a real wood frame (6 styles)."),
        ("Can I use my own photo or exact wording?",
         "Yes! Upload a high-resolution photo and type your own words - you "
         "preview your free proof on screen and approve exactly what prints "
         "before you buy."),
        ("How fast will it arrive?",
         "You approve your proof on screen at checkout, so there's no waiting on "
         "a proof email. We double-check every file, then print and ship with "
         "tracking, typically within 3-5 business days."),
        ("What if I don't love it?",
         "Your on-screen proof shows exactly what will print, so please check the "
         "wording, names, and design carefully and approve it before you buy. "
         "Because each piece is personalized and "
         "made to order, your order is final once you confirm it at checkout: we "
         "can't offer returns, refunds, or remakes for a change of mind or for "
         "the wording, spelling, design, sizing, or photo you approved. You're "
         "still fully covered if your order arrives damaged or defective, is the "
         "wrong item, or doesn't arrive - message us within 7 days of delivery "
         "(with a photo for damage or defects) and we'll remake and reship it "
         "free."),
    ]
    faq_html = "".join(
        f'<details class="faq"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faqs)
    # Plain-English returns/promise policy - matches what our print partner
    # actually covers (free reprint, no physical return) without naming any
    # marketplace. Keeps the customer promise nested inside the 30-day partner
    # window via a 7-day reporting ask.
    policy_points = [
        ("Arrived damaged or defective?",
         "That\'s on us. Message a photo within 7 days of delivery and we\'ll "
         "send a free replacement - there\'s no need to return the original, "
         "just keep or recycle it."),
        ("Apparel sizing &amp; fit",
         "T-shirts, hoodies and sweatshirts are made to order in the exact size "
         "you choose, so sizing is final - please check the size before ordering. "
         "We can\'t exchange for fit, but we\'ll always make it right if an item "
         "arrives damaged, defective or wrong."),
        ("Made to order means your order is final",
         "Because each piece is personalized and made to order from the design "
         "you submit at checkout, all sales are final - we can\'t accept returns, "
         "refunds, or cancellations for a change of mind, or for the wording, "
         "spelling, design, sizing, or photo quality you confirmed. Your final "
         "confirmation at checkout is your go-ahead to print."),
        ("Package returned to us?",
         "If the carrier couldn\'t deliver to the address provided, we\'ll "
         "happily reship to a corrected address for a small shipping fee - just "
         "send us the right address."),
        ("Lost in the mail?",
         "If tracking stalls and it doesn\'t arrive, contact us within 7 days "
         "of the expected date and we\'ll arrange a free replacement."),
    ]
    policy_html = "".join(
        f'<details class="faq"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in policy_points)
    # (The rich occasion showcase lives above the grid now - see _occasion_showcase.)
    return (
        f'<div class="why" id="why"><h2>Why {SHOP_NAME} (not a mass printer)</h2>'
        f'<table class="cmp"><tr><th>{SHOP_NAME}</th><th>Big-box printers</th></tr>'
        f'{cmp_rows}</table></div>'
        f'<div class="guarantee">💚 <b>Happiness Guarantee.</b> Every order is '
        f'made to order from the design you approve on screen, so you see exactly '
        f'what you\'ll get before you buy. If it arrives damaged or defective, is '
        f'the wrong item, or doesn\'t arrive, message us a photo within 7 days and '
        f'we\'ll make it right with a free replacement.</div>'
        f'<div class="faqs" id="faq"><h2>Questions, answered</h2>{faq_html}</div>'
        f'<div class="faqs policy" id="returns"><h2>Our happiness &amp; returns '
        f'promise</h2><p class="policyintro">Damaged or defective is on us - '
        f'made-to-order content you approved is final. Here\'s the plain '
        f'version:</p>{policy_html}</div>')


def _gift_section(owner: str) -> str:
    """'Complete the gift' affiliate cards (off-Etsy). Appears only for links that
    are configured. FTC disclosure is included automatically."""
    from quoteforge.marketing.affiliate_programs import configured_links, emoji_for
    cards = []
    for label, url in configured_links().items():
        cards.append(
            f'<a class="gcard" href="{url}" target="_blank" '
            f'rel="sponsored noopener nofollow"><div class="ge">{emoji_for(label)}</div>'
            f'<div class="gl">{label}</div></a>')
    if not cards:
        return ""
    return (
        '<div class="giftsec"><h2>Complete the gift</h2>'
        '<p class="gsub">Pair your personalized art with flowers or a gift '
        'card - delivered by trusted partners.</p>'
        f'<div class="gcards">{"".join(cards)}</div>'
        '<p class="ftc">Some links are affiliate links - we may earn a small '
        'commission at no extra cost to you.</p></div>')


def _b2b_form(owner: str) -> str:
    """The wholesale/volume-quote form. Folded INTO the packages section so there's
    a single 'for scale' area (no separate redundant corporate block)."""
    from quoteforge.config import B2B_CONTACT_EMAIL
    b2b_to = B2B_CONTACT_EMAIL or owner
    return (
        '<div class="b2b"><h3 class="b2bh">Need a custom volume quote?</h3>'
        '<p class="gsub">For employee recognition, client gifts, weddings, realtor '
        'closings, churches &amp; schools - tell us what you need and we\'ll send '
        'wholesale pricing.</p>'
        '<div class="b2bform">'
        '<input id="bz_name" aria-label="Your name" placeholder="Your name">'
        '<input id="bz_co" aria-label="Company or organization" placeholder="Company / organization">'
        '<input id="bz_email" aria-label="Your email" placeholder="Your email">'
        '<input id="bz_qty" aria-label="Approximate quantity" placeholder="Approx. quantity">'
        '<textarea id="bz_msg" aria-label="What do you need" rows="2" placeholder="What do you need? (occasion, timeline)"></textarea>'
        f'<button onclick="b2bSend(\'{b2b_to}\')">Request a wholesale quote</button>'
        '</div></div>')


def _save_web_jpg(src: Path, dest: Path, max_dim: int = 900, quality: int = 80) -> None:
    """Write an optimized JPEG copy of src to dest (for lazy-loaded assets)."""
    from PIL import Image
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail((max_dim, max_dim), Image.LANCZOS)
    im.save(dest, "JPEG", quality=quality, optimize=True)


# ── Recipient-neutral display copy ───────────────────────────────
# The SEO data targets specific recipients (best for Etsy ranking), but the
# storefront reads generically so ANY recipient fits. We only generalize the
# DISPLAYED title/description here; the underlying launch/SEO data is untouched.
import re as _re

_RECIP = r"(daughters?|sons?|husbands?|wife|wives|grandmas?|grandmothers?|grandpas?|grandfathers?|grandsons?|granddaughters?|moms?|dads?|sisters?|brothers?|aunts?|uncles?|nieces?|nephews?|kids?|child(?:ren)?|boys?|girls?|her|him)"


def _generalize_title(t: str) -> str:
    """Strip recipient words from a title so it fits anyone (keeps occasions)."""
    s = t.replace("Mother's Day", "§MD§").replace("Father's Day", "§FD§")
    s = _re.sub(r"husband\s*/\s*wife", "Couple", s, flags=_re.I)   # couple gift
    s = _re.sub(r"\bfor (a |your |my )?" + _RECIP + r"\b", "", s, flags=_re.I)
    s = _re.sub(r"\b" + _RECIP + r"\b", "", s, flags=_re.I)
    s = s.replace("§MD§", "Mother's Day").replace("§FD§", "Father's Day")
    s = _re.sub(r"\bGift\s+Gift\b", "Gift", s)
    s = _re.sub(r"\s*/\s*", " ", s)                                # stray slashes
    s = _re.sub(r"\s{2,}", " ", s)
    s = _re.sub(r"\s+\|", " |", s)
    s = _re.sub(r"\|\s*\|", "|", s).strip().strip("|").strip()
    s = _re.sub(r"\s{2,}", " ", s).replace("Personalized  ", "Personalized ")
    return s or t


# Warm, personal default wording per occasion (varied so designs don't look
# templated/computer-generated). [Name]/[Your name] are replaced when the customer
# types their own message.
OCCASION_QUOTES = {
    "birthday": [
        "[Name], may this year bring you as much joy as you bring everyone around you. Happy birthday. With love, [Your name]",
        "Happy birthday, [Name]! Of all of life's gifts, you are my favourite. Here's to you, today and always. [Your name]",
        "[Name], the world got a little brighter the day you were born. Wishing you a birthday as wonderful as you are. [Your name]",
    ],
    "anniversary": [
        "[Name], every year with you is my favourite year. Here's to us - then, now, and always. [Your name]",
        "Through every season, my answer is still you. Happy anniversary, [Name]. [Your name]",
        "[Name], I would choose this life with you a thousand times over. Happy anniversary, my love. [Your name]",
    ],
    "wedding": [
        "[Name], today two hearts become one story. Wishing you a lifetime of love and laughter. [Your name]",
        "To [Name] - may your love grow deeper with every passing year. Congratulations on your wedding day. [Your name]",
        "[Name], here's to forever - the greatest adventure starts today. [Your name]",
    ],
    "mother's day": [
        "[Name], thank you for every sacrifice, every hug, and every bit of love. Happy Mother's Day. [Your name]",
        "To the heart of our family, [Name] - there is no love like a mother's. Happy Mother's Day. [Your name]",
        "[Name], everything I am, I owe to you. Happy Mother's Day, with all my love. [Your name]",
    ],
    "father's day": [
        "[Name], thank you for being my hero, my guide, and my biggest supporter. Happy Father's Day. [Your name]",
        "To [Name] - strong, steady, and always there when it matters. Happy Father's Day. [Your name]",
        "[Name], everything you taught me made me who I am. Happy Father's Day. [Your name]",
    ],
    "valentine's day": [
        "[Name], you are my favourite hello and my hardest goodbye. Happy Valentine's Day. [Your name]",
        "Of all the hearts in the world, I am so glad I found yours. Happy Valentine's Day, [Name]. [Your name]",
        "[Name], you have my whole heart - today and every day. Happy Valentine's Day. [Your name]",
    ],
    "graduation": [
        "[Name], you've climbed higher than any mountain - now the world is yours to explore. With love, [Your name]",
        "[Name], your hard work brought you here, and your heart will take you even further. Congratulations, graduate. [Your name]",
        "So proud of you, [Name]. This is only the beginning. Congratulations! [Your name]",
    ],
    "new baby": [
        "Welcome to the world, [Name]. You are already so deeply loved. [Your name]",
        "[Name], the moment you arrived, our whole world changed for the better. [Your name]",
        "Little [Name], may your life be filled with wonder, laughter, and endless love. [Your name]",
    ],
    "housewarming": [
        "May this home be filled with love, laughter, and a lifetime of happy memories. Welcome home, [Name]. [Your name]",
        "[Name], a home isn't built with walls - it's built with love. Congratulations on yours. [Your name]",
        "Wishing you warmth, comfort, and joy in your new home, [Name]. [Your name]",
    ],
    "christmas": [
        "[Name], may your Christmas be merry and your heart be full. With love, [Your name]",
        "Wishing you a Christmas wrapped in love and sparkling with joy, [Name]. [Your name]",
        "[Name], you make every Christmas brighter. Merry Christmas, with all my love. [Your name]",
    ],
    "faith": [
        "[Name], may God's love surround you and His light guide your every step. [Your name]",
        "[Name], faith, family, and you - the greatest blessings of all. [Your name]",
    ],
    "memorial": [
        "Forever in our hearts, [Name]. Loved beyond words, missed beyond measure.",
        "[Name], your love remains in every memory and every heart you touched.",
    ],
    "just because": [
        "[Name], no special reason - just a reminder that you are loved more than words can say. [Your name]",
        "[Name], some people make the world feel like home. Thank you for being one of them. [Your name]",
    ],
}

_OCC_COUNTER: dict = {}


def _listing_occasion_key(listing_n: int, title: str, category: str) -> str:
    """Map a listing to an OCCASION_QUOTES key using the launch pack + title/category."""
    occ = ""
    try:
        from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
        rec = next((l for l in LAUNCH_PACK_20 if l.n == listing_n), None)
        if rec:
            occ = (rec.occasion or "").lower()
            category = rec.category or category
    except Exception:  # noqa: BLE001
        pass
    t = f"{title} {category}".lower()
    if "memorial" in t:
        return "memorial"
    if "christian" in t or "prayer" in t or "faith" in t or "blessing" in t:
        return "faith"
    if "husband" in t or "wife" in t or "couple" in t:
        return "anniversary"
    # explicit occasion wins over any recipient word in the title
    if "mother's day" in occ:
        return "mother's day"
    if "father's day" in occ:
        return "father's day"
    if "valentine" in occ or "valentine" in t:
        return "valentine's day"
    if "wedding" in occ or "wedding" in t:
        return "wedding"
    if "anniversary" in occ or "anniversary" in t:
        return "anniversary"
    if "graduation" in occ or "graduation" in t:
        return "graduation"
    if "birthday" in occ or "birthday" in t:
        return "birthday"
    if "christmas" in occ or "christmas" in t:
        return "christmas"
    if "new baby" in occ or "baby" in t:
        return "new baby"
    if "housewarming" in occ or "house" in t or "new home" in occ:
        return "housewarming"
    if occ in OCCASION_QUOTES:
        return occ
    return "just because"


def _occasion_quote(listing_n: int, title: str, category: str) -> str:
    """Pick a warm, occasion-appropriate default quote, rotating within an occasion
    so multiple same-occasion designs don't show identical wording."""
    key = _listing_occasion_key(listing_n, title, category)
    pool = OCCASION_QUOTES.get(key) or OCCASION_QUOTES["just because"]
    i = _OCC_COUNTER.get(key, 0)
    _OCC_COUNTER[key] = i + 1
    return pool[i % len(pool)]


# Neutral qualifiers used to differentiate same-occasion designs after we strip
# the recipient (so we never show two identical titles).
_QUALIFIERS = ["Gift", "Keepsake", "Wall Art", "Quote Print", "Memento",
               "Art Print", "Keepsake Print", "Custom Print"]


# Calendar occasions shown in the "Shop by occasion" strip, in display order.
# (key used for filtering, Display name used for the card title.)
_CALENDAR_OCCASIONS = [
    ("birthday", "Birthday"), ("anniversary", "Anniversary"), ("wedding", "Wedding"),
    ("mother's day", "Mother's Day"), ("father's day", "Father's Day"),
    ("valentine's day", "Valentine's Day"), ("graduation", "Graduation"),
    ("new baby", "New Baby"), ("housewarming", "Housewarming"),
    ("christmas", "Christmas"),
]
# Non-calendar concepts kept as their own (single) card, in display order.
_EXTRA_OCCASIONS = ["faith", "memorial", "just because"]


def _drop_duplicate_designs(listings: list) -> None:
    """Back-compat shim: keep ONE entry per unique title."""
    seen: set = set()
    keep = []
    for e in listings:
        base = e.get("title", "")
        if base in seen:
            continue
        seen.add(base)
        keep.append(e)
    listings[:] = keep


def _occasion_card_desc(disp: str) -> str:
    """Clean, occasion-specific listing description for a synthesized occasion card."""
    return (
        f"A personalized {disp} gift you make your own. Add any name, the occasion, "
        f"and your own heartfelt message - we set it beautifully on premium wall art. "
        f"HOW IT WORKS\n1. Choose your size, frame or canvas.\n2. Add the recipient's "
        f"name and your own words at checkout.\n3. We design it and ship a "
        f"ready-to-hang keepsake. A thoughtful, personal {disp} gift.")


def _reorder_by_occasion(listings: list) -> None:
    """Order the grid: calendar occasions in showcase order, then the extras
    (faith/memorial/just-because), then anything else - one entry per occasion."""
    by_occ = {}
    rest = []
    for e in listings:
        k = e.get("occ")
        if k and k not in by_occ:
            by_occ[k] = e
        else:
            rest.append(e)
    final, used = [], set()
    for key, _ in _CALENDAR_OCCASIONS:
        if key in by_occ:
            final.append(by_occ[key]); used.add(key)
    for key in _EXTRA_OCCASIONS:
        if key in by_occ and key not in used:
            final.append(by_occ[key]); used.add(key)
    for k, e in by_occ.items():
        if k not in used:
            final.append(e); used.add(k)
    listings[:] = final


def _render_occasion_design(kit_dir: Path, disp: str, quote: str) -> Path | None:
    """Ensure a real poster + 5-image gallery exists for a synthesized occasion card
    (its OWN wording burned in - never borrowed from another design).

    Cached in a SHARED dir keyed by occasion+wording so the art is rendered once and
    reused across every site rebuild (and every test), not regenerated per build.
    The published copies are downscaled JPEGs (via _emit), so we render at a modest
    web size for speed. Returns the design folder, or None if rendering is
    unavailable."""
    import hashlib
    import tempfile
    slug = disp.lower().replace("'", "").replace(" ", "-")
    sig = hashlib.md5(quote.encode("utf-8")).hexdigest()[:8]  # noqa: S324 (cache key)
    folder = Path(tempfile.gettempdir()) / "qf_occasions" / f"{slug}-{sig}"
    gallery = folder / "gallery"
    poster = folder / "poster_18x24.png"
    if gallery.exists() and any(gallery.glob("*.png")):
        return folder
    try:
        from quoteforge.images.local_renderer import render_local_poster
        from quoteforge.images.listing_pack import build_listing_pack
        folder.mkdir(parents=True, exist_ok=True)
        render_local_poster(quote=quote, output_path=poster, size=(1500, 2000))
        (folder / "quote.txt").write_text(quote, encoding="utf-8")
        build_listing_pack(poster, gallery)
        return folder
    except Exception:  # noqa: BLE001
        return None


def _collapse_to_one_per_occasion(listings: list) -> list:
    """Show exactly ONE design per occasion - every print is fully personalizable,
    so 6 graduation cards or 3 birthday cards is just noise. Keep the first design
    per occasion, normalize calendar cards to a clean 'Personalized <Occasion> Gift'
    title, and RETURN the calendar occasions that still have no design so the caller
    can synthesize a real (separately rendered) card for each. Result: the 'Shop by
    occasion' strip and every chip always lands on exactly one matching design."""
    if not listings:
        return [(k, d) for k, d in _CALENDAR_OCCASIONS]
    by_occ: dict = {}
    order: list = []
    for e in listings:
        k = e.get("occ") or "just because"
        if k not in by_occ:
            by_occ[k] = e
            order.append(k)
    missing: list = []
    for key, disp in _CALENDAR_OCCASIONS:
        if key in by_occ:
            e = by_occ[key]
            e["title"] = f"Personalized {disp} Gift"
            e["full_title"] = (f"Personalized {disp} Gift | {disp} Wall Art | "
                               f"Custom Quote Print - You Personalize It")
        else:
            missing.append((key, disp))
    # Order: calendar occasions (showcase order) first, then extras, then the rest.
    final, used = [], set()
    for key, _ in _CALENDAR_OCCASIONS:
        if key in by_occ:
            final.append(by_occ[key]); used.add(key)
    for key in _EXTRA_OCCASIONS:
        if key in by_occ and key not in used:
            final.append(by_occ[key]); used.add(key)
    for key in order:
        if key not in used:
            final.append(by_occ[key]); used.add(key)
    listings[:] = final
    return missing


def _dedupe_titles(listings: list) -> None:
    """Ensure every display title is unique by swapping the trailing qualifier
    (e.g. two 'Personalized Birthday Gift' -> '... Gift' and '... Keepsake')."""
    seen: dict[str, int] = {}
    for e in listings:
        base = e["title"]
        if base not in seen:
            seen[base] = 0
            continue
        seen[base] += 1
        n = seen[base]
        qual = _QUALIFIERS[n % len(_QUALIFIERS)]
        # replace a trailing 'Gift'/'Print' etc. with the next qualifier, else append
        new = _re.sub(r"\b(Gift|Keepsake|Print|Wall Art|Memento)\s*$", qual, base)
        if new == base:
            new = f"{base} {qual}"
        # keep uniqueness even if the swap collided
        while new in seen:
            n += 1
            qual = _QUALIFIERS[n % len(_QUALIFIERS)]
            new = _re.sub(r"\b(Gift|Keepsake|Print|Wall Art|Memento)\s*$", qual, base)
            if new == base:
                new = f"{base} {qual} {n}"
        seen[new] = 0
        # update both the card title and the modal full title's first segment
        if e.get("full_title", "").startswith(base):
            e["full_title"] = new + e["full_title"][len(base):]
        e["title"] = new


def _generalize_quote(q: str) -> str:
    """Make the DEFAULT preview wording recipient-neutral so it fits anyone:
    'Dear Emma, ...' -> 'Dear [Name], ...'; sign-offs like ', Mom' -> ', [Your name]'.
    The customer's own message replaces this entirely once they type it."""
    if not q:
        return q
    s = q.strip()
    # Leading salutation: optional 'Dear ' + a name/short phrase up to the first comma.
    s = _re.sub(r"^(Dear\s+)?[A-Z][A-Za-z'’]*(?:\s[A-Z][A-Za-z'’]*)?\s*,",
                lambda m: (m.group(1) or "") + "[Name],", s, count=1)
    # Sender sign-off at the very end (e.g. 'With love, Mom' / 'Your Child').
    s = _re.sub(r",\s*(Mom|Mum|Mother|Dad|Father|Your Child|Grandma|Grandpa)\s*$",
                ", [Your name]", s, flags=_re.I)
    # Any residual bracketed placeholder name variants -> [Name].
    s = s.replace("[Your name]", "[Your name]")
    return s


def _generalize_desc(d: str) -> str:
    """Generalize a multi-line description: recipients -> 'loved one'."""
    s = d.replace("Mother's Day", "§MD§").replace("Father's Day", "§FD§")
    s = _re.sub(r"\bfor (a |your |my )?" + _RECIP + r"\b", "for your loved one",
                s, flags=_re.I)
    s = _re.sub(r"\b(your|my|a)\s+" + _RECIP + r"\b", r"\1 loved one", s, flags=_re.I)
    s = _re.sub(r"\b" + _RECIP + r"\b", "loved one", s, flags=_re.I)
    s = s.replace("§MD§", "Mother's Day").replace("§FD§", "Father's Day")
    s = _re.sub(r"\bloved one ideas\b", "gift ideas", s)
    s = _re.sub(r"\s{2,}", " ", s)
    return s


# Professional product tiles: a detailed, shaded garment illustration on a soft
# studio backdrop, per garment - on-brand muted palette (sage / teal / clay),
# fabric detail + ground shadow, so each reads like a real product shot.
_APPAREL_TILE = {
    "tshirt": ("radial-gradient(circle at 50% 38%,#f3f6f1 0%,#dde6da 100%)",
        '<defs><linearGradient id="teeG" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#9fb89f"/><stop offset="1" stop-color="#79977c"/>'
        '</linearGradient></defs>'
        '<ellipse cx="60" cy="111" rx="33" ry="5" fill="rgba(0,0,0,.12)"/>'
        '<path d="M47 22 C41 25 34 28 27 31 L20 46 L35 52 L35 104 L85 104 L85 52 '
        'L100 46 L93 31 C86 28 79 25 73 22 C66 31 54 31 47 22 Z" fill="url(#teeG)"/>'
        '<path d="M35 52 L35 104 L45 104 L43 53 Z" fill="rgba(0,0,0,.07)"/>'
        '<path d="M47 22 C54 31 66 31 73 22 L69 28 C60 37 51 37 51 28 Z" '
        'fill="rgba(0,0,0,.13)"/>'
        '<path d="M51 28 C51 37 60 37 69 28" fill="none" '
        'stroke="rgba(255,255,255,.4)" stroke-width="1.3"/>'
        '<path d="M35 52 L27 31" fill="none" stroke="rgba(255,255,255,.16)" '
        'stroke-width="1.2"/>'),
    "hoodie": ("radial-gradient(circle at 50% 38%,#eef4f4 0%,#d4e3e3 100%)",
        '<defs><linearGradient id="hooG" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#54908f"/><stop offset="1" stop-color="#3b6c6e"/>'
        '</linearGradient></defs>'
        '<ellipse cx="60" cy="111" rx="34" ry="5" fill="rgba(0,0,0,.12)"/>'
        '<path d="M44 30 C38 33 32 36 26 39 L20 54 L34 60 L34 104 L86 104 L86 60 '
        'L100 54 L94 39 C88 36 82 33 76 30 Z" fill="url(#hooG)"/>'
        '<path d="M44 30 C38 22 50 14 60 14 C70 14 82 22 76 30 C68 38 52 38 44 30 Z" '
        'fill="url(#hooG)"/>'
        '<path d="M49 28 C45 21 53 15 60 15 C67 15 75 21 71 28 C66 35 54 35 49 28 Z" '
        'fill="rgba(0,0,0,.17)"/>'
        '<path d="M34 60 L34 104 L44 104 L42 61 Z" fill="rgba(0,0,0,.08)"/>'
        '<rect x="42" y="80" width="36" height="18" rx="4" fill="none" '
        'stroke="rgba(0,0,0,.13)" stroke-width="1.5"/>'
        '<line x1="56" y1="33" x2="56" y2="52" stroke="rgba(0,0,0,.2)" '
        'stroke-width="2" stroke-linecap="round"/>'
        '<line x1="64" y1="33" x2="64" y2="52" stroke="rgba(0,0,0,.2)" '
        'stroke-width="2" stroke-linecap="round"/>'),
    "sweatshirt": ("radial-gradient(circle at 50% 38%,#f7efe5 0%,#e6d6c4 100%)",
        '<defs><linearGradient id="sweG" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#cd9576"/><stop offset="1" stop-color="#b07a5c"/>'
        '</linearGradient></defs>'
        '<ellipse cx="60" cy="111" rx="33" ry="5" fill="rgba(0,0,0,.12)"/>'
        '<path d="M47 24 C41 27 34 30 27 33 L21 48 L34 54 L34 100 L86 100 L86 54 '
        'L99 48 L93 33 C86 30 79 27 73 24 C66 33 54 33 47 24 Z" fill="url(#sweG)"/>'
        '<path d="M47 24 C54 33 66 33 73 24" fill="none" stroke="rgba(0,0,0,.17)" '
        'stroke-width="3.2"/>'
        '<path d="M34 96 L86 96" stroke="rgba(0,0,0,.13)" stroke-width="3.6"/>'
        '<path d="M28 50 L36 53" stroke="rgba(0,0,0,.13)" stroke-width="3"/>'
        '<path d="M92 50 L84 53" stroke="rgba(0,0,0,.13)" stroke-width="3"/>'
        '<path d="M34 54 L34 100 L44 100 L42 55 Z" fill="rgba(0,0,0,.08)"/>'),
}


# Occasion-first entry points for apparel: pick the moment -> the editor opens
# pre-loaded with a fitting quote (key matches OCCASION_QUOTES). Gift intent is
# what sells a personalized shop, so this leads the apparel department.
_APPAREL_OCCASIONS = [
    ("birthday", "Birthday", "🎂"), ("anniversary", "Anniversary", "💍"),
    ("mother's day", "For Mom", "🌷"), ("father's day", "For Dad", "🧢"),
    ("wedding", "Wedding", "💒"), ("new baby", "New Baby", "🍼"),
    ("graduation", "Graduation", "🎓"), ("memorial", "Memorial", "🕊️"),
    ("just because", "Just Because", "💛"),
]


# Per-occasion line icon (inline SVG) + soft colour-coded circle, replacing the
# flat emoji with a premium, consistent visual cue (the page has no icon webfont).
_APPAREL_OCC_ICON = {
    "birthday": ('<path d="M5 21h14v-8H5z"/><path d="M5 13c1.6 0 1.6-1.6 3.5-1.6S10 13 12 13'
                 's1.6-1.6 3.5-1.6S17 13 19 13"/><path d="M8 8.5v3M12 7.5v4M16 8.5v3"/>',
                 "#fbeaf0", "#b03a5f"),
    "anniversary": ('<path d="M5 9l3-4h8l3 4-7 10z"/><path d="M5 9h14M9 5l3 4 3-4M9 9l3 10 3-10"/>',
                    "#f1ecfb", "#6b4ea3"),
    "mother's day": ('<circle cx="12" cy="8" r="2"/><circle cx="8.6" cy="10.4" r="2"/>'
                     '<circle cx="15.4" cy="10.4" r="2"/><circle cx="9.9" cy="13.8" r="2"/>'
                     '<circle cx="14.1" cy="13.8" r="2"/><path d="M12 16v5"/>',
                     "#fdeae6", "#c2562f"),
    "father's day": ('<path d="M8 4h8v4a4 4 0 0 1-8 0z"/><path d="M8 5.5H6a2 2 0 0 0 2.3 2'
                     'M16 5.5h2a2 2 0 0 1-2.3 2"/><path d="M12 12v3M9 19h6M10 19c0-1 .5-2 2-2'
                     's2 1 2 2"/>', "#e8f1fb", "#2b6da5"),
    "wedding": ('<circle cx="9.5" cy="14" r="3.8"/><circle cx="14.5" cy="14" r="3.8"/>'
                '<path d="M8 9l1.5 2M16 9l-1.5 2M12 7l1 2"/>', "#faf0d8", "#b3902f"),
    "new baby": ('<path d="M17 13a5.2 5.2 0 1 1-5.6-5.2A4 4 0 0 0 17 13z"/>'
                 '<path d="M17.5 5l.5 1.3 1.3.5-1.3.6-.5 1.4-.6-1.4-1.3-.6 1.4-.5z"/>',
                 "#e1f5ee", "#0f6e56"),
    "graduation": ('<path d="M12 6 2.5 9.5 12 13l9.5-3.5z"/><path d="M6 11.2V15c0 1.2 2.7 2.2 6 2.2'
                   's6-1 6-2.2v-3.8"/><path d="M21.5 9.5V15"/>', "#eaf3de", "#3b6d11"),
    "memorial": ('<path d="M4 20c8 0 14-6 14-14 0 0-9.5 1-11.5 7C5.2 16 4 20 4 20z"/>'
                 '<path d="M9 15c3-1 5-3 6.5-5.5"/>', "#eef1f0", "#5f6e66"),
    "just because": ('<path d="M12 20S4.5 15.3 4.5 9.9A3.6 3.6 0 0 1 12 7a3.6 3.6 0 0 1 7.5 2.9'
                     'C19.5 15.3 12 20 12 20z"/>', "#faeeda", "#b3902f"),
}


def _apparel_hero() -> str:
    """The apparel department hero: a deep-green banner with an editorial
    lifestyle photo (when bundled at brand/apparel-hero.jpg) and the CTA. Falls
    back to the gradient-only banner when no photo is present."""
    from quoteforge.config import OUTPUT_DIR
    img = ""
    for p in (Path(__file__).resolve().parents[2] / "brand" / "apparel-hero.jpg",
              Path(OUTPUT_DIR) / "apparel-hero.jpg"):
        try:
            if p.exists():
                img = (f'<img class="apheroimg" src="{_web_img(p, 1200, 80)}" '
                       f'alt="People wearing custom apparel" loading="lazy">')
                break
        except Exception:  # noqa: BLE001
            img = ""
    return (
        '<div class="aphero">'
        '<div class="apherobody">'
        '<span class="apheroeyebrow">Personalized &middot; made to order</span>'
        '<h2 class="apheroh">Custom Apparel</h2>'
        '<p class="apherosub">Put your name, words or photo on a tee, hoodie, tank '
        'or sweatshirt - the same easy editor, and a free proof you approve on '
        'screen before anything prints.</p>'
        '<button type="button" class="apherocta" onclick="'
        "document.querySelector('.appoccchips')."
        "scrollIntoView({behavior:'smooth',block:'center'})"
        '">Start designing &rarr;</button>'
        '</div>'
        f'<div class="apheromedia">{img}</div>'
        '</div>')


def _wallart_hero() -> str:
    """The wall-art department hero - mirrors the apparel hero for a consistent,
    premium department look. Uses brand/wallart-hero.jpg (else the room hero)."""
    from quoteforge.config import OUTPUT_DIR
    img = ""
    for p in (Path(__file__).resolve().parents[2] / "brand" / "wallart-hero.jpg",
              Path(__file__).resolve().parents[2] / "brand" / "hero.jpg",
              Path(OUTPUT_DIR) / "wallart-hero.jpg"):
        try:
            if p.exists():
                img = (f'<img class="apheroimg" src="{_web_img(p, 1200, 80)}" '
                       f'alt="Personalized framed wall art styled in a cozy room" '
                       f'loading="lazy">')
                break
        except Exception:  # noqa: BLE001
            img = ""
    return (
        '<div class="aphero" id="wallart">'
        '<div class="apherobody">'
        '<span class="apheroeyebrow">Made to order &middot; museum quality</span>'
        '<h2 class="apheroh">Wall Art</h2>'
        '<p class="apherosub">Your names, dates &amp; own words on poster, framed, '
        'canvas, acrylic or metal - hand-designed, with a free proof you approve on '
        'screen before anything prints.</p>'
        '<button type="button" class="apherocta" onclick="'
        "(document.getElementById('occasions')||document.getElementById('grid'))"
        ".scrollIntoView({behavior:'smooth',block:'start'})"
        '">Browse designs &rarr;</button>'
        '</div>'
        f'<div class="apheromedia">{img}</div>'
        '</div>')


def _apparel_occasions() -> str:
    """The 'Shop by occasion' strip for apparel - each chip opens the design
    editor pre-loaded with that occasion's quote, ready to personalize."""
    chips = []
    for key, disp, _emoji in _APPAREL_OCCASIONS:
        pool = OCCASION_QUOTES.get(key) or OCCASION_QUOTES["just because"]
        qjs = pool[0].replace("\\", "\\\\").replace("'", "\\'")
        svg, bg, fg = _APPAREL_OCC_ICON.get(
            key, _APPAREL_OCC_ICON["just because"])
        chips.append(
            f'<button class="appocc" type="button" '
            f'onclick="shopApparelOccasion(\'{qjs}\')" '
            f'aria-label="Design a {disp} garment">'
            f'<span class="appoccic" style="background:{bg}">'
            f'<svg viewBox="0 0 24 24" style="stroke:{fg}" aria-hidden="true">{svg}</svg>'
            f'</span>'
            f'<span class="appocclbl">{disp}</span></button>')
    return (
        '<div class="appoccrow">'
        '<span class="appocceyebrow">Start with the moment</span>'
        '<h3 class="appocch">🎁 Shop by occasion</h3>'
        '<p class="appoccsub">Pick the moment - your design starts with the perfect '
        'words, ready to make your own.</p>'
        f'<div class="appoccchips">{"".join(chips)}</div></div>')


def _apparel_section(photos: dict | None = None) -> str:
    """Visible top-level Apparel department, split into Men's and Women's
    sub-sections like a department store. Real product PHOTO per garment TYPE when
    `photos` (garment_type -> src) is supplied, else a shaded SVG fallback. Each
    card opens the design editor into apparel mode for that garment."""
    photos = photos or {}
    try:
        from quoteforge.etsy.apparel_catalog import (
            APPAREL_CATALOG, build_apparel_variations)
    except Exception:  # noqa: BLE001
        return ""
    frm: dict = {}
    for v in build_apparel_variations():
        frm[v.garment_id] = min(frm.get(v.garment_id, 1e9), v.price)
    if not frm:
        return ""
    # Collapse the three brand tiers (Value/Classic/Premium) into ONE tile per
    # (gender, garment type): the Classic garment is the visible card, the buyer
    # picks the quality tier inside the editor. "from" shows the cheapest tier.
    _group_from: dict = {}     # (gender, type) -> min price across its tiers
    _group_tiers: dict = {}    # (gender, type) -> set of tier names present
    for g in APPAREL_CATALOG:
        if frm.get(g.garment_id) is None:
            continue
        k = (g.gender, g.garment_type)
        _group_from[k] = min(_group_from.get(k, 1e9), frm[g.garment_id])
        _group_tiers.setdefault(k, set()).add(g.tier)

    def _brand_disp(g) -> str:
        """Brand label without the trailing style code (e.g. 'Lane Seven')."""
        return g.brand.rsplit(" ", 1)[0] if g.brand else ""   # drop style code

    def _card(g) -> str:
        """Render one garment tile (product photo, else shaded SVG fallback).
        Carries data-* facets (gender/type/brand/colours/sizes) the filter bar
        reads to show or hide the tile."""
        low = _group_from.get((g.gender, g.garment_type))
        if low is None:
            return ""
        # Prefer the EXACT per-garment product image (tier/gender), else the
        # per-type AI tile, else the SVG fallback.
        src = photos.get(g.garment_id) or photos.get(g.garment_type)
        if src:
            tile = (f'<span class="apptile apptilephoto"><img class="appimg" '
                    f'loading="lazy" src="{src}" alt="Custom {g.name}"></span>')
        else:
            grad, art = _APPAREL_TILE.get(g.garment_type, _APPAREL_TILE["tshirt"])
            tile = (f'<span class="apptile" style="background:{grad}">'
                    f'<svg class="appsvg" viewBox="0 0 120 120" aria-hidden="true">'
                    f'{art}</svg></span>')
        name_js = g.name.replace("\\", "\\\\").replace("'", "\\'")
        brand_disp = _brand_disp(g)
        _ntiers = len(_group_tiers.get((g.gender, g.garment_type), {g.tier}))
        tier_line = ('<span class="apptier">Value · Classic · Premium</span>'
                     if _ntiers > 1 else
                     (f'<span class="apptier">{g.tier} · {brand_disp}</span>'
                      if g.tier and brand_disp else ""))
        return (
            f'<button class="appcard" type="button" '
            f'data-gender="{g.gender}" data-type="{g.type_name}" '
            f'data-brand="{brand_disp}" data-tier="{g.tier}" data-garment="{g.name}" '
            f'data-typeid="{g.garment_type}" data-gid="{g.garment_id}" '
            f'data-colors="{"|".join(g.colors)}" data-sizes="{"|".join(g.sizes)}" '
            f'onclick="shopApparel(\'{name_js}\', this.dataset.activecolor||\'\')" '
            f'aria-label="Design a custom {g.name}">'
            f'{tile}'
            f'<span class="appname">{g.type_name}</span>'
            f'{tier_line}'
            f'<span class="appsw" aria-label="Available colours"></span>'
            f'<span class="appfrom">from ${low:.2f}</span>'
            f'<span class="appcta">Design yours →</span></button>')

    shown = [g for g in APPAREL_CATALOG
             if g.tier == "Classic" and frm.get(g.garment_id) is not None]
    if not shown:
        return ""

    groups = []
    for gender, label in (("men", "Men's Clothing"), ("women", "Women's Apparel")):
        cards = [_card(g) for g in shown if g.gender == gender]
        cards = [c for c in cards if c]
        if cards:
            groups.append(f'<div class="appgroup" data-gender="{gender}">'
                          f'<h3 class="appghead">{label}</h3>'
                          f'<div class="appgrid">{"".join(cards)}</div></div>')
    if not groups:
        return ""

    # ── Faceted filter bar (Department / Type / Brand / Colour / Size) ──
    def _distinct(seq) -> list:
        """Unique truthy values, preserving first-seen order."""
        out: list = []
        for x in seq:
            if x and x not in out:
                out.append(x)
        return out
    types_f = _distinct(g.type_name for g in shown)
    brands_f = _distinct(_brand_disp(g) for g in shown)
    colors_f = _distinct(c for g in shown for c in g.colors)
    _size_order = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
    _present = {s for g in shown for s in g.sizes}
    sizes_f = ([s for s in _size_order if s in _present]
               + _distinct(s for g in shown for s in g.sizes if s not in _size_order))
    genders_f = _distinct(g.gender for g in shown)

    def _opts(vals) -> str:
        """Render <option> tags for a list of facet values."""
        return "".join(f'<option value="{v}">{v}</option>' for v in vals)
    dept_opts = "".join(
        f'<option value="{gd}">{lbl}</option>'
        for gd, lbl in (("men", "Men's"), ("women", "Women's")) if gd in genders_f)

    def _sel(sid, label, all_label, opts) -> str:
        """Render one labelled filter <select> with an 'all' default option."""
        return (f'<select class="appfilter" id="{sid}" aria-label="{label}" '
                f'onchange="applyApparelFilters()">'
                f'<option value="">{all_label}</option>{opts}</select>')
    filterbar = (
        '<div class="appfilters" role="group" aria-label="Filter apparel">'
        + '<span class="appfilterlbl">Refine</span>'
        + _sel("afDept", "Department", "All departments", dept_opts)
        + _sel("afType", "Type", "All types", _opts(types_f))
        + _sel("afBrand", "Brand", "All brands", _opts(brands_f))
        + _sel("afColor", "Colour", "All colours", _opts(colors_f))
        + _sel("afSize", "Size", "All sizes", _opts(sizes_f))
        + '<button type="button" class="appfilterclear" '
          'onclick="clearApparelFilters()">Clear</button>'
        + f'<span class="appfiltercount" id="afCount">{len(shown)} styles</span>'
        + '</div>')
    nomatch = (
        '<p class="apnomatch" id="afNoMatch" style="display:none">'
        'No styles match those filters. '
        '<button type="button" class="appfilterclear" '
        'onclick="clearApparelFilters()">Clear filters</button></p>')
    return (
        '<section class="apparel-sec" id="apparel">'
        f'{_apparel_hero()}'
        f'{_apparel_occasions()}{filterbar}{"".join(groups)}{nomatch}</section>')


# Customer-safe colour-name -> hex map for branded tile swatch dots. Mirrors the
# JS APPARELCOLOR map (the single source of truth on the client) so the tiles
# paint identically server-side. Never carries supplier data.
_BRANDED_SWATCH_HEX = {
    "White": "#f4f3ef", "Sand": "#d8c9a8", "Heather Grey": "#b9bdc2",
    "Light Blue": "#a7c7e7", "Black": "#1c1c1e", "Charcoal": "#3a3f43",
    "Navy": "#26324a", "Royal Blue": "#2f4ba0", "Red": "#b3322c",
    "Maroon": "#5e2a32", "Forest Green": "#2e4a39", "Sage": "#7f9b78",
    "Mustard": "#cda434", "Purple": "#5b4b8a", "Dusty Rose": "#c98a9a",
    "Brown": "#5a4334", "Natural": "#e7ddc7", "Cream": "#f3ecd9",
    "Silver": "#c9ccce",
}


def _branded_section(photos: dict | None = None, external_assets: bool = False,
                     assets=None) -> str:
    """Visible Custom Branded Products department - a department-store grid of
    merch lines (totes, bottles, notebooks, ...). Real product PHOTO per product
    when `photos` (product_id -> src) is supplied, else a neutral SVG fallback.
    Modeled closely on `_apparel_section`: hero band, faceted filter bar, one
    tile per product with a from-price and colour swatch dots. Emits ONLY
    customer-safe facets (name/category/type/colour/size/price) - never the
    supplier brand or any SKU/cost."""
    photos = photos or {}
    try:
        from quoteforge.etsy.branded_catalog import (
            BRANDED_CATALOG, build_branded_variations)
    except Exception:  # noqa: BLE001
        return ""
    frm: dict = {}
    for v in build_branded_variations():
        frm[v.product_id] = min(frm.get(v.product_id, 1e9), v.price)
    if not frm:
        return ""
    shown = [p for p in BRANDED_CATALOG if frm.get(p.product_id) is not None]
    if not shown:
        return ""

    def _swatches(colors) -> str:
        """Static colour swatch dots painted from the customer-safe hex map."""
        dots = []
        for cn in colors:
            hexv = _BRANDED_SWATCH_HEX.get(cn, "#bbbbbb")
            ring = (";box-shadow:inset 0 0 0 1px #cfcabb"
                    if cn in ("White", "Sand", "Natural", "Cream", "Silver",
                              "Light Blue", "Heather Grey") else "")
            dots.append(f'<i class="swdot" title="{cn}" data-color="{cn}" '
                        f'style="background:{hexv}{ring}"></i>')
        return "".join(dots)

    def _card(p) -> str:
        """Render one branded product tile (product photo, else neutral SVG)."""
        low = frm.get(p.product_id)
        if low is None:
            return ""
        src = photos.get(p.product_id)
        if src:
            tile = (f'<span class="apptile apptilephoto"><img class="appimg" '
                    f'loading="lazy" src="{src}" alt="Custom {p.name}"></span>')
        else:
            tile = ('<span class="apptile" '
                    'style="background:linear-gradient(135deg,#eef1ee,#dfe5df)">'
                    '<svg class="appsvg" viewBox="0 0 120 120" aria-hidden="true">'
                    '<rect x="30" y="30" width="60" height="60" rx="8" '
                    'fill="none" stroke="#9aa79a" stroke-width="4"/>'
                    '<circle cx="60" cy="60" r="14" fill="#9aa79a" '
                    'opacity="0.5"/></svg></span>')
        name_js = p.name.replace("\\", "\\\\").replace("'", "\\'")
        color0 = (p.colors[0] if p.colors else "").replace("\\", "\\\\").replace("'", "\\'")
        return (
            f'<button class="brandcard" type="button" '
            f'data-bpid="{p.product_id}" data-cat="{p.category}" '
            f'data-type="{p.type_name}" data-product="{p.name}" '
            f'data-colors="{",".join(p.colors)}" data-sizes="{",".join(p.sizes)}" '
            f'onclick="shopBranded(\'{name_js}\',\'{color0}\')" '
            f'aria-label="Design a custom {p.name}">'
            f'{tile}'
            f'<span class="appname">{p.type_name}</span>'
            f'<span class="appsw" aria-label="Available colours">'
            f'{_swatches(p.colors)}</span>'
            f'<span class="appfrom">from ${low:.2f}</span>'
            f'<span class="appcta">Design yours &rarr;</span></button>')

    cards = [c for c in (_card(p) for p in shown) if c]
    if not cards:
        return ""

    # ── Faceted filter bar (Category / Type / Colour / Size) ──
    def _distinct(seq) -> list:
        """Distinct truthy values from seq, preserving first-seen order."""
        out: list = []
        for x in seq:
            if x and x not in out:
                out.append(x)
        return out
    cats_f = _distinct(p.category for p in shown)
    types_f = _distinct(p.type_name for p in shown)
    colors_f = _distinct(c for p in shown for c in p.colors)
    sizes_f = _distinct(s for p in shown for s in p.sizes)

    def _opts(vals) -> str:
        """Render a list of values as <option> tags for a filter <select>."""
        return "".join(f'<option value="{v}">{v}</option>' for v in vals)

    def _sel(sid, label, all_label, opts) -> str:
        """Render one labelled filter <select> with an 'all' default + options."""
        return (f'<select class="appfilter" id="{sid}" aria-label="{label}" '
                f'onchange="applyBrandedFilters()">'
                f'<option value="">{all_label}</option>{opts}</select>')
    filterbar = (
        '<div class="brandfilter" role="group" '
        'aria-label="Filter branded products">'
        + '<span class="appfilterlbl">Refine</span>'
        + _sel("bfCat", "Category", "All categories", _opts(cats_f))
        + _sel("bfType", "Type", "All types", _opts(types_f))
        + _sel("bfColor", "Colour", "All colours", _opts(colors_f))
        + _sel("bfSize", "Size", "All sizes", _opts(sizes_f))
        + '<button type="button" class="appfilterclear" '
          'onclick="clearBrandedFilters()">Clear</button>'
        + f'<span class="appfiltercount" id="bfCount">{len(cards)} products</span>'
        + '</div>')
    nomatch = (
        '<p class="apnomatch" id="bfNoMatch" style="display:none">'
        'No products match those filters. '
        '<button type="button" class="appfilterclear" '
        'onclick="clearBrandedFilters()">Clear filters</button></p>')
    return (
        '<section class="apparel-sec branded-sec" id="branded">'
        f'{_branded_hero(external_assets, assets)}{filterbar}'
        f'<div class="appgroup"><div class="appgrid">{"".join(cards)}</div></div>'
        f'{nomatch}</section>')


def _branded_hero(external_assets: bool = False, assets=None) -> str:
    """The branded-products department hero - mirrors the apparel hero markup and
    classes for a consistent department look. Generic copy (no supplier or
    marketplace names). Uses brand/branded-hero.jpg when bundled. In external_assets
    mode the hero photo is written to the assets folder and referenced by URL
    (lazy-loaded) instead of inlined as a parse-blocking data-URI."""
    from quoteforge.config import OUTPUT_DIR
    img = ""
    for p in (Path(__file__).resolve().parents[2] / "brand" / "branded-hero.jpg",
              Path(OUTPUT_DIR) / "branded-hero.jpg"):
        try:
            if p.exists():
                if external_assets and assets is not None:
                    _save_web_jpg(p, assets / "branded-hero.jpg", 1200, 80)
                    src = "assets/branded-hero.jpg"
                else:
                    src = _web_img(p, 1200, 80)
                img = (f'<img class="apheroimg" src="{src}" '
                       f'alt="Custom branded products" loading="lazy">')
                break
        except Exception:  # noqa: BLE001
            img = ""
    return (
        '<div class="aphero" id="brandedhero">'
        '<div class="apherobody">'
        '<span class="apheroeyebrow">Personalized &middot; made to order</span>'
        '<h2 class="apheroh">Custom Branded Products</h2>'
        '<p class="apherosub">Put your name, words or photo on totes, bottles, '
        'tumblers, notebooks, stickers &amp; more - the same easy editor, and a '
        'free proof you approve on screen before anything prints.</p>'
        '<button type="button" class="apherocta" onclick="'
        "(document.querySelector('.brandfilter')||document.getElementById('branded'))"
        ".scrollIntoView({behavior:'smooth',block:'center'})"
        '">Start designing &rarr;</button>'
        '</div>'
        f'<div class="apheromedia">{img}</div>'
        '</div>')


def _mug_section(photos: dict | None = None, external_assets: bool = False,
                 assets=None) -> str:
    """Visible Custom Mugs department - a department-store grid of mug lines
    (classic/large/colour-interior/accent/enamel/travel). Real product PHOTO per
    product when `photos` (product_id -> src) is supplied, else a neutral SVG
    fallback. Mirrors `_branded_section` exactly: hero band, faceted filter bar,
    one tile per product with a from-price and accent-colour swatch dots. Tiles
    carry `appcard mugcard` so they inherit the apparel tile CSS. Emits ONLY
    customer-safe facets (name/category/type/colour/size/price) - never the
    supplier brand or any SKU/cost."""
    photos = photos or {}
    try:
        from quoteforge.etsy.mug_catalog import (
            MUG_CATALOG, build_mug_variations)
    except Exception:  # noqa: BLE001
        return ""
    frm: dict = {}
    for v in build_mug_variations():
        frm[v.product_id] = min(frm.get(v.product_id, 1e9), v.price)
    if not frm:
        return ""
    shown = [p for p in MUG_CATALOG if frm.get(p.product_id) is not None]
    if not shown:
        return ""

    def _swatches(colors) -> str:
        """Static accent-colour swatch dots painted from the customer-safe hex map."""
        dots = []
        for cn in colors:
            hexv = _BRANDED_SWATCH_HEX.get(cn, "#bbbbbb")
            ring = (";box-shadow:inset 0 0 0 1px #cfcabb"
                    if cn in ("White", "Sand", "Natural", "Cream", "Silver",
                              "Light Blue", "Heather Grey") else "")
            dots.append(f'<i class="swdot" title="{cn}" data-color="{cn}" '
                        f'style="background:{hexv}{ring}"></i>')
        return "".join(dots)

    def _card(p) -> str:
        """Render one mug product tile (product photo, else neutral SVG)."""
        low = frm.get(p.product_id)
        if low is None:
            return ""
        src = photos.get(p.product_id)
        if src:
            tile = (f'<span class="apptile apptilephoto"><img class="appimg" '
                    f'loading="lazy" src="{src}" alt="Custom {p.name}"></span>')
        else:
            tile = ('<span class="apptile" '
                    'style="background:linear-gradient(135deg,#eef1ee,#dfe5df)">'
                    '<svg class="appsvg" viewBox="0 0 120 120" aria-hidden="true">'
                    '<rect x="30" y="30" width="60" height="60" rx="8" '
                    'fill="none" stroke="#9aa79a" stroke-width="4"/>'
                    '<circle cx="60" cy="60" r="14" fill="#9aa79a" '
                    'opacity="0.5"/></svg></span>')
        name_js = p.name.replace("\\", "\\\\").replace("'", "\\'")
        color0 = (p.colors[0] if p.colors else "").replace("\\", "\\\\").replace("'", "\\'")
        return (
            f'<button class="appcard mugcard" type="button" '
            f'data-mpid="{p.product_id}" data-cat="{p.category}" '
            f'data-type="{p.type_name}" data-product="{p.name}" '
            f'data-colors="{",".join(p.colors)}" data-sizes="{",".join(p.sizes)}" '
            f'onclick="shopMug(\'{name_js}\',\'{color0}\')" '
            f'aria-label="Design a custom {p.name}">'
            f'{tile}'
            f'<span class="appname">{p.type_name}</span>'
            f'<span class="appsw" aria-label="Available colours">'
            f'{_swatches(p.colors)}</span>'
            f'<span class="appfrom">from ${low:.2f}</span>'
            f'<span class="appcta">Design yours &rarr;</span></button>')

    cards = [c for c in (_card(p) for p in shown) if c]
    if not cards:
        return ""

    # ── Faceted filter bar (Category / Type / Colour / Size) ──
    def _distinct(seq) -> list:
        """Distinct truthy values from seq, preserving first-seen order."""
        out: list = []
        for x in seq:
            if x and x not in out:
                out.append(x)
        return out
    cats_f = _distinct(p.category for p in shown)
    types_f = _distinct(p.type_name for p in shown)
    colors_f = _distinct(c for p in shown for c in p.colors)
    sizes_f = _distinct(s for p in shown for s in p.sizes)

    def _opts(vals) -> str:
        """Render a list of values as <option> tags for a filter <select>."""
        return "".join(f'<option value="{v}">{v}</option>' for v in vals)

    def _sel(sid, label, all_label, opts) -> str:
        """Render one labelled filter <select> with an 'all' default + options."""
        return (f'<select class="appfilter" id="{sid}" aria-label="{label}" '
                f'onchange="applyMugFilters()">'
                f'<option value="">{all_label}</option>{opts}</select>')
    filterbar = (
        '<div class="appfilters mugfilter" role="group" '
        'aria-label="Filter mugs">'
        + '<span class="appfilterlbl">Refine</span>'
        + _sel("mgCat", "Category", "All categories", _opts(cats_f))
        + _sel("mgType", "Type", "All types", _opts(types_f))
        + _sel("mgColor", "Colour", "All colours", _opts(colors_f))
        + _sel("mgSize", "Size", "All sizes", _opts(sizes_f))
        + '<button type="button" class="appfilterclear" '
          'onclick="clearMugFilters()">Clear</button>'
        + f'<span class="appfiltercount" id="mgCount">{len(cards)} products</span>'
        + '</div>')
    nomatch = (
        '<p class="apnomatch" id="mgNoMatch" style="display:none">'
        'No mugs match those filters. '
        '<button type="button" class="appfilterclear" '
        'onclick="clearMugFilters()">Clear filters</button></p>')
    return (
        '<section class="apparel-sec mug-sec" id="mugs">'
        f'{_mug_hero(external_assets, assets)}{filterbar}'
        f'<div class="appgroup"><div class="appgrid">{"".join(cards)}</div></div>'
        f'{nomatch}</section>')


def _mug_hero(external_assets: bool = False, assets=None) -> str:
    """The mugs department hero - mirrors the apparel/branded hero markup and
    classes for a consistent department look. Generic copy (no supplier or
    marketplace names). Uses brand/mugs-hero.jpg when bundled. In external_assets
    mode the hero photo is written to the assets folder and referenced by URL
    (lazy-loaded) instead of inlined as a parse-blocking data-URI."""
    from quoteforge.config import OUTPUT_DIR
    img = ""
    for p in (Path(__file__).resolve().parents[2] / "brand" / "mugs-hero.jpg",
              Path(OUTPUT_DIR) / "mugs-hero.jpg"):
        try:
            if p.exists():
                if external_assets and assets is not None:
                    _save_web_jpg(p, assets / "mugs-hero.jpg", 1200, 80)
                    src = "assets/mugs-hero.jpg"
                else:
                    src = _web_img(p, 1200, 80)
                img = (f'<img class="apheroimg" src="{src}" '
                       f'alt="Custom mugs" loading="lazy">')
                break
        except Exception:  # noqa: BLE001
            img = ""
    return (
        '<div class="aphero" id="mugshero">'
        '<div class="apherobody">'
        '<span class="apheroeyebrow">Personalized &middot; made to order</span>'
        '<h2 class="apheroh">Custom Mugs</h2>'
        '<p class="apherosub">Put your name, words or photo on classic, enamel, '
        'travel &amp; colour-accent mugs - the same easy editor, and a free proof '
        'you approve on screen before anything prints.</p>'
        '<button type="button" class="apherocta" onclick="'
        "(document.querySelector('.mugfilter')||document.getElementById('mugs'))"
        ".scrollIntoView({behavior:'smooth',block:'center'})"
        '">Start designing &rarr;</button>'
        '</div>'
        f'<div class="apheromedia">{img}</div>'
        '</div>')


def _cal_section(photos: dict | None = None, external_assets: bool = False,
                 assets=None) -> str:
    """Visible Custom Calendars department - a department-store grid of calendar
    lines (wall/desk/family/corporate/photo/event/promo). Real product PHOTO per
    product when `photos` (product_id -> src) is supplied, else a neutral SVG
    fallback. Mirrors `_mug_section` exactly: hero band, faceted filter bar, one
    tile per product with a from-price and a (single, white-paper) colour swatch.
    Tiles carry `appcard calcard` so they inherit the apparel tile CSS. Emits ONLY
    customer-safe facets (name/category/type/size/price) - never the supplier
    brand or any SKU/cost."""
    photos = photos or {}
    try:
        from quoteforge.etsy.calendar_catalog import (
            CALENDAR_CATALOG, build_calendar_variations)
    except Exception:  # noqa: BLE001
        return ""
    frm: dict = {}
    for v in build_calendar_variations():
        frm[v.product_id] = min(frm.get(v.product_id, 1e9), v.price)
    if not frm:
        return ""
    shown = [p for p in CALENDAR_CATALOG if frm.get(p.product_id) is not None]
    if not shown:
        return ""

    def _swatches(colors) -> str:
        """Static paper-colour swatch dots painted from the customer-safe hex map."""
        dots = []
        for cn in colors:
            hexv = _BRANDED_SWATCH_HEX.get(cn, "#bbbbbb")
            ring = (";box-shadow:inset 0 0 0 1px #cfcabb"
                    if cn in ("White", "Sand", "Natural", "Cream", "Silver",
                              "Light Blue", "Heather Grey") else "")
            dots.append(f'<i class="swdot" title="{cn}" data-color="{cn}" '
                        f'style="background:{hexv}{ring}"></i>')
        return "".join(dots)

    def _card(p) -> str:
        """Render one calendar product tile (product photo, else neutral SVG)."""
        low = frm.get(p.product_id)
        if low is None:
            return ""
        src = photos.get(p.product_id)
        if src:
            tile = (f'<span class="apptile apptilephoto"><img class="appimg" '
                    f'loading="lazy" src="{src}" alt="Custom {p.name}"></span>')
        else:
            tile = ('<span class="apptile" '
                    'style="background:linear-gradient(135deg,#eef1ee,#dfe5df)">'
                    '<svg class="appsvg" viewBox="0 0 120 120" aria-hidden="true">'
                    '<rect x="30" y="30" width="60" height="60" rx="8" '
                    'fill="none" stroke="#9aa79a" stroke-width="4"/>'
                    '<circle cx="60" cy="60" r="14" fill="#9aa79a" '
                    'opacity="0.5"/></svg></span>')
        name_js = p.name.replace("\\", "\\\\").replace("'", "\\'")
        color0 = (p.colors[0] if p.colors else "").replace("\\", "\\\\").replace("'", "\\'")
        return (
            f'<button class="appcard calcard" type="button" '
            f'data-cpid="{p.product_id}" data-cat="{p.category}" '
            f'data-type="{p.type_name}" data-product="{p.name}" '
            f'data-colors="{",".join(p.colors)}" data-sizes="{",".join(p.sizes)}" '
            f'onclick="shopCalendar(\'{name_js}\',\'{color0}\')" '
            f'aria-label="Design a custom {p.name}">'
            f'{tile}'
            f'<span class="appname">{p.type_name}</span>'
            f'<span class="appsw" aria-label="Available colours">'
            f'{_swatches(p.colors)}</span>'
            f'<span class="appfrom">from ${low:.2f}</span>'
            f'<span class="appcta">Design yours &rarr;</span></button>')

    cards = [c for c in (_card(p) for p in shown) if c]
    if not cards:
        return ""

    # ── Faceted filter bar (Category / Type / Size) ──
    def _distinct(seq) -> list:
        """Distinct truthy values from seq, preserving first-seen order."""
        out: list = []
        for x in seq:
            if x and x not in out:
                out.append(x)
        return out
    cats_f = _distinct(p.category for p in shown)
    types_f = _distinct(p.type_name for p in shown)
    sizes_f = _distinct(s for p in shown for s in p.sizes)

    def _opts(vals) -> str:
        """Render a list of values as <option> tags for a filter <select>."""
        return "".join(f'<option value="{v}">{v}</option>' for v in vals)

    def _sel(sid, label, all_label, opts) -> str:
        """Render one labelled filter <select> with an 'all' default + options."""
        return (f'<select class="appfilter" id="{sid}" aria-label="{label}" '
                f'onchange="applyCalFilters()">'
                f'<option value="">{all_label}</option>{opts}</select>')
    filterbar = (
        '<div class="appfilters calfilter" role="group" '
        'aria-label="Filter calendars">'
        + '<span class="appfilterlbl">Refine</span>'
        + _sel("clCat", "Category", "All categories", _opts(cats_f))
        + _sel("clType", "Type", "All types", _opts(types_f))
        + _sel("clSize", "Size", "All sizes", _opts(sizes_f))
        + '<button type="button" class="appfilterclear" '
          'onclick="clearCalFilters()">Clear</button>'
        + f'<span class="appfiltercount" id="clCount">{len(cards)} products</span>'
        + '</div>')
    nomatch = (
        '<p class="apnomatch" id="clNoMatch" style="display:none">'
        'No calendars match those filters. '
        '<button type="button" class="appfilterclear" '
        'onclick="clearCalFilters()">Clear filters</button></p>')
    return (
        '<section class="apparel-sec cal-sec" id="calendars">'
        f'{_cal_hero(external_assets, assets)}{filterbar}'
        f'<div class="appgroup"><div class="appgrid">{"".join(cards)}</div></div>'
        f'{nomatch}</section>')


def _cal_hero(external_assets: bool = False, assets=None) -> str:
    """The calendars department hero - mirrors the apparel/mug hero markup and
    classes for a consistent department look. Generic copy (no supplier or
    marketplace names). Uses brand/cal-hero.jpg when bundled. In external_assets
    mode the hero photo is written to the assets folder and referenced by URL
    (lazy-loaded) instead of inlined as a parse-blocking data-URI."""
    from quoteforge.config import OUTPUT_DIR
    img = ""
    for p in (Path(__file__).resolve().parents[2] / "brand" / "cal-hero.jpg",
              Path(OUTPUT_DIR) / "cal-hero.jpg"):
        try:
            if p.exists():
                if external_assets and assets is not None:
                    _save_web_jpg(p, assets / "cal-hero.jpg", 1200, 80)
                    src = "assets/cal-hero.jpg"
                else:
                    src = _web_img(p, 1200, 80)
                img = (f'<img class="apheroimg" src="{src}" '
                       f'alt="Custom calendars" loading="lazy">')
                break
        except Exception:  # noqa: BLE001
            img = ""
    return (
        '<div class="aphero" id="calhero">'
        '<div class="apherobody">'
        '<span class="apheroeyebrow">Personalized &middot; made to order</span>'
        '<h2 class="apheroh">Custom Calendars</h2>'
        '<p class="apherosub">Design a calendar around your own photos, dates and '
        'words - wall, desk, family, photo &amp; event styles, the same easy '
        'editor, and a free proof you approve on screen before anything prints.</p>'
        '<button type="button" class="apherocta" onclick="'
        "(document.querySelector('.calfilter')||document.getElementById('calendars'))"
        ".scrollIntoView({behavior:'smooth',block:'center'})"
        '">Start designing &rarr;</button>'
        '</div>'
        f'<div class="apheromedia">{img}</div>'
        '</div>')


def build_shop_home(password: str = "Jesus", numbers=None, kit_dir=None,
                    out_path=None, uat: bool = True, feedback_form_url=None,
                    frame_picker: bool = True, external_assets: bool = False) -> Path:
    """A polished, password-gated shop-home / UAT page: logo+banner, a 20-listing
    grid, a per-listing detail modal (all 5 images + description), a per-listing
    star rating, and one-click feedback. Shareable as one link.

    Feedback routing: if ``feedback_form_url`` (or config FEEDBACK_FORM_URL) is
    set, buttons open that Google Form / survey with the listing title + star
    rating in the URL fragment so responses auto-aggregate; otherwise a mailto
    to the owner (with the rating in the body) is used."""
    import json
    from quoteforge.config import (
        OUTPUT_DIR, ETSY_DEFAULT_LISTING_PRICE, SHOP_NAME, REPORT_RECIPIENT,
        FEEDBACK_FORM_URL,
    )
    from quoteforge.etsy.listing_seo import build_launch_seo

    form_url = (feedback_form_url if feedback_form_url is not None
                else FEEDBACK_FORM_URL) or ""

    kit_dir = Path(kit_dir) if kit_dir else (OUTPUT_DIR / "launch_kit")
    brand = Path("brand")
    bundles = build_launch_seo()
    if numbers:
        bundles = [b for b in bundles if b.listing_n in numbers]

    out = Path(out_path) if out_path else (kit_dir / "shop_home.html")
    assets = out.parent / "assets" if external_assets else None

    # Per-format "from" price (min across sizes), keyed to the preview names,
    # so the displayed price updates when a buyer picks a frame / material.
    fmt_price = {}
    try:
        from quoteforge.etsy.variations import build_variations
        _mat_name = {"poster": "Poster (unframed)",
                     "canvas": "Canvas (gallery-wrapped)",
                     "acrylic": "Acrylic", "metal": "Metal"}
        for v in build_variations():
            k = (f"Framed - {v.frame_color}" if v.material == "framed"
                 else _mat_name.get(v.material))
            if k:
                fmt_price[k] = min(fmt_price.get(k, 1e9), v.price)
    except Exception:  # noqa: BLE001
        fmt_price = {}

    # The design-INDEPENDENT format/material list (poster -> framed ladder ->
    # canvas/acrylic/metal), with real "from" prices. Every design is orderable
    # in every format, so this is the guaranteed fallback the frame picker uses
    # whenever a card has no per-frame preview thumbnails of its own - so a
    # render hiccup can never hide the picker or leave the stale default price.
    def _global_formats() -> list:
        """Ordered global format list ({name, price, img:''}) from fmt_price."""
        if not fmt_price:
            return []
        framed = sorted((k for k in fmt_price if k.startswith("Framed - ")),
                        key=lambda k: fmt_price[k])
        order = (["Poster (unframed)"] + framed
                 + ["Canvas (gallery-wrapped)", "Acrylic", "Metal"])
        return [{"name": k, "img": "", "price": fmt_price[k]}
                for k in order if k in fmt_price]
    GLOBAL_FORMATS = _global_formats()

    def _emit(src: Path, fname: str) -> str:
        """Return a data-URI (inline mode) or a lazy-loaded relative URL."""
        if external_assets:
            _save_web_jpg(src, assets / fname)
            return f"assets/{fname}"
        return _web_img(src)

    # Build a compact JS data array.
    #
    # The grid shows ONE design per occasion (the first seen). Pre-compute that
    # survivor set so dropped duplicates are skipped BEFORE any rendering:
    # otherwise we'd emit their gallery JPEGs + frame previews into docs/assets
    # as orphans on every rebuild (which the Site Doctor would then prune - a
    # pointless churn) and waste ~half the rebuild time rendering them.
    survivors: set = set()
    _seen_occ: set = set()
    for b in bundles:
        k = _listing_occasion_key(b.listing_n, b.title, getattr(b, "category", ""))
        if k not in _seen_occ:
            _seen_occ.add(k)
            survivors.add(b.listing_n)
    listings = []
    _OCC_COUNTER.clear()       # fresh occasion-quote rotation per build
    for b in bundles:
        if b.listing_n not in survivors:
            continue           # dropped duplicate - render nothing for it
        gallery = sorted((kit_dir).glob(f"{b.listing_n:02d}_*/gallery/*.png"))
        if not gallery:
            continue
        # Personal, occasion-specific default wording (varied per design) so the
        # preview never looks like the same computer-generated text on every piece.
        occ_key = _listing_occasion_key(b.listing_n, b.title, getattr(b, "category", ""))
        quote_txt = _occasion_quote(b.listing_n, b.title, getattr(b, "category", ""))
        gen_title = _generalize_title(b.title)
        entry = {
            "n": b.listing_n,
            "occ": occ_key,
            "quote": _generalize_quote(quote_txt),
            "title": gen_title.split(" | ")[0],
            "full_title": gen_title,
            "price": f"{ETSY_DEFAULT_LISTING_PRICE:.2f}",
            "desc": _generalize_desc(b.description),
            "imgs": [_emit(p, f"{b.listing_n:02d}_g{i:02d}.jpg")
                     for i, p in enumerate(gallery)],
        }
        # Frame/material picker uses the global name+price format list. The pills
        # render a colour swatch (swatchDot) + name + price and never read a
        # per-frame preview image, so we do NOT render per-design frame mockups:
        # that was dead compute (Pillow render per design every build) plus page/
        # asset bloat (the base64/JPG was generated but consumed 0 times). Every
        # design is still orderable in every format via this one global list.
        if frame_picker and GLOBAL_FORMATS:
            entry["formats"] = GLOBAL_FORMATS
        # Card "from" price = the real lowest variation price (not a flat default).
        prices = [f["price"] for f in entry.get("formats", []) if f.get("price")]
        if prices:
            entry["price"] = f"{min(prices):.2f}"
        listings.append(entry)
    # One card per occasion; get the showcased occasions still lacking a design.
    missing = _collapse_to_one_per_occasion(listings)
    # Synthesize a REAL card for each missing occasion - its own art + wording,
    # rendered (and cached) separately so nothing is borrowed from another design.
    syn_tag = 90
    for key, disp in missing:
        quote = _generalize_quote((OCCASION_QUOTES.get(key) or [""])[0])
        folder = _render_occasion_design(kit_dir, disp, quote)
        if not folder:
            continue
        gal = sorted((folder / "gallery").glob("*.png"))
        if not gal:
            continue
        syn_tag += 1
        # Synthesized cards skip only the heavy per-frame preview THUMBNAILS;
        # they still offer the full frame/material choice (same names + real
        # prices from the variation model) so every design is orderable in
        # every format - the chips just don't swap a rendered preview image.
        entry = {
            "n": 0, "occ": key, "quote": quote,
            "title": f"Personalized {disp} Gift",
            "full_title": (f"Personalized {disp} Gift | {disp} Wall Art | "
                           f"Custom Quote Print - You Personalize It"),
            "price": f"{ETSY_DEFAULT_LISTING_PRICE:.2f}",
            "desc": _occasion_card_desc(disp),
            "imgs": [_emit(p, f"{syn_tag}_g{i:02d}.jpg") for i, p in enumerate(gal)],
        }
        if frame_picker and GLOBAL_FORMATS:
            entry["formats"] = GLOBAL_FORMATS
            entry["price"] = f"{min(f['price'] for f in GLOBAL_FORMATS):.2f}"
        listings.append(entry)
    # Re-order so synthesized cards slot into showcase position with the rest.
    _reorder_by_occasion(listings)
    data_json = json.dumps(listings)
    owner = REPORT_RECIPIENT or "owner@example.com"
    try:
        from quoteforge.etsy.gift_finder import quiz_config
        quiz_json = json.dumps(quiz_config())
    except Exception:  # noqa: BLE001
        quiz_json = "{}"

    try:
        from quoteforge.analytics.ab_testing import experiments_config
        ab_json = json.dumps(experiments_config())
    except Exception:  # noqa: BLE001
        ab_json = "{}"

    # Single source of truth for quantity/bundle discounts (mirrors backend so the
    # storefront JS can never drift from variations.QTY_DISCOUNT).
    from quoteforge.etsy.variations import QTY_DISCOUNT
    qty_discount_json = json.dumps([[t, d] for t, d in QTY_DISCOUNT])
    _bundle_tiers = sorted([(t, d) for t, d in QTY_DISCOUNT if d > 0], key=lambda x: x[0])
    bundle_discount_text = ", ".join(
        f"{t}{'+' if t == max(x[0] for x in _bundle_tiers) else ''} = {round(d*100)}% off"
        for t, d in _bundle_tiers)
    # Welcome / first-order promo copy (from config, not baked into markup).
    from quoteforge.config import PROMO_WELCOME_CODE, PROMO_WELCOME_PCT
    promo_code = PROMO_WELCOME_CODE
    promo_pct = PROMO_WELCOME_PCT
    try:
        from quoteforge.config import ETSY_SHOP_URL as etsy_shop_url
    except Exception:  # noqa: BLE001
        etsy_shop_url = ""
    try:
        from quoteforge.config import PAYMENT_LINK_URL as payment_link_url
    except Exception:  # noqa: BLE001
        payment_link_url = ""
    try:
        from quoteforge.config import ESTIMATED_TAX_RATE_PCT as est_tax_pct
    except Exception:  # noqa: BLE001
        est_tax_pct = 0

    # Size -> price map per format (sizes/prices are the same across designs).
    sizemap: dict = {}
    try:
        from quoteforge.etsy.variations import build_variations as _bv
        _mn = {"poster": "Poster (unframed)", "canvas": "Canvas (gallery-wrapped)",
               "acrylic": "Acrylic", "metal": "Metal"}
        for v in _bv():
            key = (f"Framed - {v.frame_color}" if v.material == "framed"
                   else _mn.get(v.material))
            if key:
                sizemap.setdefault(key, []).append(
                    {"size": v.size.replace(" in", ""), "price": v.price})
        for k in sizemap:   # de-dup + sort by price
            seen = {}
            for r in sizemap[k]:
                seen[r["size"]] = r
            sizemap[k] = sorted(seen.values(), key=lambda r: r["price"])
    except Exception:  # noqa: BLE001
        sizemap = {}
    # Apparel: a parallel product type that REUSES this same SIZEMAP + picker.
    # Each garment+colour is a "format" (mirrors "Framed - Oak"); the garment
    # SIZE lives in SIZEMAP under that key. Emitted from garment / colour / size /
    # price ONLY - never the supplier SKU or cost - so no fulfilment name can
    # reach the customer page.
    apparel_formats: list = []
    apparel_tiers: dict = {}            # Classic name -> [{tier,name,from}] picker
    if frame_picker:
        try:
            from quoteforge.etsy.apparel_catalog import (
                build_apparel_variations, APPAREL_CATALOG)
            _ap_from: dict = {}
            _gid_from: dict = {}        # garment_id -> cheapest variant price
            _size_order = ["S", "M", "L", "XL", "2XL", "3XL"]
            # Canonical colour order (light-forward, White first) so each garment's
            # pills/swatches/default open on White - not alphabetical "Black".
            _corder = {c: i for i, c in enumerate(
                APPAREL_CATALOG[0].colors if APPAREL_CATALOG else [])}
            for av in build_apparel_variations():
                key = f"{av.name} - {av.color}"
                sizemap.setdefault(key, []).append(
                    {"size": av.size, "price": av.price})
                _ap_from[key] = min(_ap_from.get(key, 1e9), av.price)
                _gid_from[av.garment_id] = min(
                    _gid_from.get(av.garment_id, 1e9), av.price)
            for key in _ap_from:                      # sort each garment by size
                seen = {r["size"]: r for r in sizemap[key]}
                sizemap[key] = sorted(
                    seen.values(),
                    key=lambda r: (_size_order.index(r["size"])
                                   if r["size"] in _size_order else 99))
            def _ap_sort(item):
                """Sort key: garment, then catalogue colour rank (White first)."""
                g, _, c = item[0].rpartition(" - ")
                return (g, _corder.get(c, 99), c)
            apparel_formats = [{"name": k, "img": "", "price": round(p, 2)}
                               for k, p in sorted(_ap_from.items(), key=_ap_sort)]
            # Tier groups for the in-editor quality picker: the Classic garment
            # name maps to every tier (Value/Classic/Premium) of that gender+type,
            # each with its cheapest "from" price - so a collapsed tile still lets
            # the buyer reach Value and Premium.
            _trank = {"Value": 0, "Classic": 1, "Premium": 2}
            _cls_name = {(g.gender, g.garment_type): g.name
                         for g in APPAREL_CATALOG if g.tier == "Classic"}
            _grp: dict = {}
            for g in APPAREL_CATALOG:
                if g.garment_id in _gid_from:
                    _grp.setdefault((g.gender, g.garment_type), []).append(g)
            for _k, _gs in _grp.items():
                _cname = _cls_name.get(_k)
                if not _cname:
                    continue
                apparel_tiers[_cname] = [
                    {"tier": g.tier, "name": g.name,
                     "from": round(_gid_from[g.garment_id], 2)}
                    for g in sorted(_gs, key=lambda x: _trank.get(x.tier, 9))]
        except Exception:  # noqa: BLE001
            apparel_formats = []
            apparel_tiers = {}
    apparel_formats_json = json.dumps(apparel_formats)
    apparel_tiers_json = json.dumps(apparel_tiers)
    # Per-colour supplier product photos {garment_id:{colour:url}} - swaps the tile
    # photo to the picked colour at go-live; empty (no swap) in TEST_MODE.
    try:
        from quoteforge.images.supplier_mockup import apparel_tile_color_images
        apparel_color_img = apparel_tile_color_images()
    except Exception:  # noqa: BLE001
        apparel_color_img = {}
    apparel_color_img_json = json.dumps(apparel_color_img)
    # garment NAME -> garment_id, so the editor (which knows CURGARMENT by name) can
    # look up the per-garment mockup.
    try:
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG as _AC
        appgid = {g.name: g.garment_id for g in _AC}
    except Exception:  # noqa: BLE001
        appgid = {}
    appgid_json = json.dumps(appgid)
    # Branded products REUSE the shared SIZEMAP + size picker. Each product+colour
    # is a "format" ("{name} - {colour}") whose sizes/prices live in SIZEMAP under
    # that key - same shape as apparel. Emitted from name/colour/size/price ONLY
    # (never the supplier SKU or cost). Done here so it lands before sizemap_json.
    if frame_picker:
        try:
            from quoteforge.etsy.branded_catalog import (
                BRANDED_CATALOG as _BCs, build_branded_variations as _bbvs)
            _bn = {p.product_id: p.name for p in _BCs}
            _bkeys: set = set()
            for _v in _bbvs():
                if _v.product_id not in _bn:
                    continue
                _bkey = f"{_bn[_v.product_id]} - {_v.color}"
                _bkeys.add(_bkey)
                sizemap.setdefault(_bkey, []).append(
                    {"size": _v.size, "price": round(_v.price, 2)})
            for _bkey in _bkeys:                  # de-dup sizes per branded key only
                _seen = {r["size"]: r for r in sizemap[_bkey]}
                sizemap[_bkey] = sorted(
                    _seen.values(), key=lambda r: r["price"])
        except Exception:  # noqa: BLE001 — never break the build on the branded catalog
            pass
    # MUGS + CALENDARS: like branded + apparel, each is a "format" ("{name} - {colour}")
    # whose REAL sizes/prices must live in SIZEMAP under that key. These were missing,
    # so the editor's Size dropdown fell back to the first key (poster) and showed
    # 8x10..24x36 at poster prices. Mug size = capacity (11oz); calendar = A3/A4/A5.
    # Name/colour/size/price only - never the supplier SKU or cost.
    try:
        from quoteforge.etsy.mug_catalog import (
            MUG_CATALOG as _MUc, build_mug_variations as _bmuv)
        _mun = {p.product_id: p.name for p in _MUc}
        _mukeys: set = set()
        for _v in _bmuv():
            if _v.product_id not in _mun:
                continue
            _muk = f"{_mun[_v.product_id]} - {_v.color}"
            _mukeys.add(_muk)
            sizemap.setdefault(_muk, []).append(
                {"size": _v.size, "price": round(_v.price, 2)})
        for _muk in _mukeys:                  # de-dup sizes per mug key only
            _s = {r["size"]: r for r in sizemap[_muk]}
            sizemap[_muk] = sorted(_s.values(), key=lambda r: r["price"])
    except Exception:  # noqa: BLE001 — never break the build on the mug catalog
        pass
    try:
        from quoteforge.etsy.calendar_catalog import (
            CALENDAR_CATALOG as _CAc, build_calendar_variations as _bcav)
        _can = {p.product_id: p.name for p in _CAc}
        _cakeys: set = set()
        for _v in _bcav():
            if _v.product_id not in _can:
                continue
            _cak = f"{_can[_v.product_id]} - {_v.color}"
            _cakeys.add(_cak)
            sizemap.setdefault(_cak, []).append(
                {"size": _v.size, "price": round(_v.price, 2)})
        for _cak in _cakeys:                  # de-dup sizes per calendar key only
            _s = {r["size"]: r for r in sizemap[_cak]}
            sizemap[_cak] = sorted(_s.values(), key=lambda r: r["price"])
    except Exception:  # noqa: BLE001 — never break the build on the calendar catalog
        pass
    sizemap_json = json.dumps(sizemap)
    all_formats_json = json.dumps(GLOBAL_FORMATS)
    editor_picks_json = json.dumps([s.lower() for s in EDITOR_PICKS])

    # Product range + frame note for the detail modal.
    _hi = 0
    mat_short = "Poster · Framed · Canvas · Acrylic · Metal"
    try:
        from quoteforge.etsy.variations import price_range, materials_offered
        _lo, _hi = price_range()
        mats = [m.split(" (")[0] for m in materials_offered()]
        mat_short = " · ".join(mats)
        materials_line = mat_short + f" — ${_lo:.0f}–${_hi:.0f}"
    except Exception:  # noqa: BLE001
        materials_line = ""
    price_hi = f"{_hi:.0f}"
    try:
        from quoteforge.etsy.variations import build_variations as _bvc
        opt_count = len(_bvc())
    except Exception:  # noqa: BLE001
        opt_count = 0

    logo = brand / "joffiels_logo_green_gold.png"
    banner = brand / "joffiels_banner.png"
    logo_src = _web_img(logo, 240) if logo.exists() else ""
    # Hero: a lifestyle/sample photo (HERO_IMAGE or brand/hero.*) beats the banner.
    from quoteforge.config import HERO_IMAGE
    hero_img = None
    if HERO_IMAGE and Path(HERO_IMAGE).exists():
        hero_img = Path(HERO_IMAGE)
    else:
        hero_img = next((p for p in (brand / "hero.jpg", brand / "hero.png",
                                     brand / "hero.jpeg") if p.exists()), None)
    # The hero is the LCP. Externalize it (cacheable, parallel-fetched file)
    # instead of ~180KB of parse-blocking base64 in the critical HTML; inline
    # only for a self-contained build (external_assets off, e.g. unit tests).
    _hero_pick = hero_img if hero_img else (banner if banner.exists() else None)
    _hero_dim = 1600 if hero_img else 1400
    if _hero_pick and external_assets:
        _save_web_jpg(_hero_pick, assets / "hero.jpg", _hero_dim, 82)
        banner_src = "assets/hero.jpg"
    elif _hero_pick:
        banner_src = _web_img(_hero_pick, _hero_dim)
    else:
        banner_src = ""
    # Department-card lifestyle photos: Wall Art reuses the hero room shot; Apparel
    # uses a dedicated lifestyle photo. Emoji fallback if a photo is missing.
    dept_wall_src = _emit(hero_img, "dept-wallart.jpg") if hero_img else ""
    _dept_app_img = next((p for p in (brand / "dept-apparel.jpg",
                                      brand / "dept-apparel.png") if p.exists()), None)
    dept_app_src = _emit(_dept_app_img, "dept-apparel.jpg") if _dept_app_img else ""
    _dept_branded_img = next((p for p in (brand / "dept-branded.jpg",
                                          brand / "dept-branded.png") if p.exists()), None)
    dept_branded_src = (_emit(_dept_branded_img, "dept-branded.jpg")
                        if _dept_branded_img else "")
    _dept_mug_img = next((p for p in (brand / "dept-mug.jpg",
                                      brand / "dept-mug.png") if p.exists()), None)
    dept_mug_src = (_emit(_dept_mug_img, "dept-mug.jpg")
                    if _dept_mug_img else "")
    _dept_cal_img = next((p for p in (brand / "dept-cal.jpg",
                                      brand / "dept-cal.png") if p.exists()), None)
    dept_cal_src = (_emit(_dept_cal_img, "dept-cal.jpg")
                    if _dept_cal_img else "")
    # Per-garment product photos for the apparel tiles, keyed by garment_id so each
    # GENDER shows its OWN model photo (brand/tile-<garment_id>.jpg, e.g.
    # tile-m_tshirt.jpg / tile-w_tshirt.jpg). Falls back to the shaded SVG tile when
    # a photo is absent. Only the Classic tier is tiled - the three brand tiers
    # collapse into one card and the buyer picks the tier inside the editor.
    _garment_photos: dict = {}
    try:
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG as _AC_ph
        _photo_gids = [g.garment_id for g in _AC_ph if g.tier == "Classic"]
    except Exception:  # noqa: BLE001
        _photo_gids = []
    for _gid in _photo_gids:
        _gp = next((brand / f"tile-{_gid}.{e}" for e in ("jpg", "png")
                    if (brand / f"tile-{_gid}.{e}").exists()), None)
        if _gp:
            _garment_photos[_gid] = _emit(_gp, f"tile-{_gid}.jpg")
    # Real print-partner product images override the AI tiles when the supplier API
    # is live (key set + UIDs mapped); keyed PER GARMENT (garment_id) so each tier/
    # gender shows ITS exact product. TEST_MODE / no key leaves the AI tiles as-is.
    try:
        from quoteforge.images.supplier_mockup import apparel_tile_images
        for _gidk, _url in apparel_tile_images().items():
            if _url:
                _garment_photos[_gidk] = _url    # garment_id key (preferred in _card)
    except Exception:  # noqa: BLE001 — never break the build on the supplier API
        pass
    # Front + BACK garment photos for the editor's front/back FLIP, so a buyer can
    # see and design the BACK too. garment_id -> {front, back}; back is the matching
    # print-partner back-view tile (brand/tile-<gid>-back.jpg), or the front if none.
    _apparel_side_img: dict = {}
    for _gid, _front in _garment_photos.items():
        if not _front:
            continue
        _bk = next((brand / f"tile-{_gid}-back.{e}" for e in ("jpg", "png")
                    if (brand / f"tile-{_gid}-back.{e}").exists()), None)
        _apparel_side_img[_gid] = {
            "front": _front,
            "back": _emit(_bk, f"tile-{_gid}-back.jpg") if _bk else _front}
    apparel_side_img_json = json.dumps(_apparel_side_img)

    # Per-product tile photos for the Custom Branded Products grid, keyed by
    # product_id (brand/tile-<product_id>.jpg, e.g. tile-tote.jpg). Falls back to
    # the section's neutral SVG tile when a photo is absent - mirrors how the
    # apparel _garment_photos are built. Customer-safe only (no supplier data).
    _branded_photos: dict = {}
    branded_formats_json = "[]"
    branded_dims_json = "{}"
    branded_pid_json = "{}"
    try:
        from quoteforge.etsy.branded_catalog import (
            BRANDED_CATALOG as _BC, build_branded_variations as _bbv)
        for _p in _BC:
            _bp = next((brand / f"tile-{_p.product_id}.{e}" for e in ("jpg", "png")
                        if (brand / f"tile-{_p.product_id}.{e}").exists()), None)
            if _bp:
                _branded_photos[_p.product_id] = _emit(_bp, f"tile-{_p.product_id}.jpg")
        # Cheapest price per (product, colour) for the editor's branded picker.
        _bc_from: dict = {}
        for _v in _bbv():
            _key = (_v.product_id, _v.color)
            _bc_from[_key] = min(_bc_from.get(_key, 1e9), _v.price)
        _bname = {_p.product_id: _p.name for _p in _BC}
        branded_formats = [
            {"name": f"{_bname[_pid]} - {_col}", "price": round(_pr, 2)}
            for (_pid, _col), _pr in _bc_from.items() if _pid in _bname]
        branded_formats_json = json.dumps(branded_formats)
        branded_dims_json = json.dumps(
            {_p.product_id: [_p.width_px, _p.height_px] for _p in _BC})
        # Editor maps the picked product NAME (what shopBranded carries) back to a
        # product_id so it can look up BRANDED_DIMS (which is keyed by product_id).
        branded_pid_json = json.dumps({_p.name: _p.product_id for _p in _BC})
    except Exception:  # noqa: BLE001 — never break the build on the branded catalog
        _branded_photos = {}
        branded_formats_json = "[]"
        branded_dims_json = "{}"
        branded_pid_json = "{}"

    # Per-product tile photos for the Custom Mugs grid, keyed by product_id
    # (brand/tile-<product_id>.jpg, e.g. tile-classic_mug.jpg). Falls back to the
    # section's neutral SVG tile when a photo is absent - mirrors the branded grid.
    # Customer-safe only (no supplier data).
    _mug_photos: dict = {}
    mug_formats_json = "[]"
    mug_dims_json = "{}"
    mug_pid_json = "{}"
    try:
        from quoteforge.etsy.mug_catalog import (
            MUG_CATALOG as _MC, build_mug_variations as _bmv)
        for _p in _MC:
            _mp = next((brand / f"tile-{_p.product_id}.{e}" for e in ("jpg", "png")
                        if (brand / f"tile-{_p.product_id}.{e}").exists()), None)
            if _mp:
                _mug_photos[_p.product_id] = _emit(_mp, f"tile-{_p.product_id}.jpg")
        # Cheapest price per (product, accent-colour) for the editor's mug picker.
        _mc_from: dict = {}
        for _v in _bmv():
            _key = (_v.product_id, _v.color)
            _mc_from[_key] = min(_mc_from.get(_key, 1e9), _v.price)
        _mname = {_p.product_id: _p.name for _p in _MC}
        mug_formats = [
            {"name": f"{_mname[_pid]} - {_col}", "price": round(_pr, 2)}
            for (_pid, _col), _pr in _mc_from.items() if _pid in _mname]
        mug_formats_json = json.dumps(mug_formats)
        mug_dims_json = json.dumps(
            {_p.product_id: [_p.width_px, _p.height_px] for _p in _MC})
        # Editor maps the picked product NAME (what shopMug carries) back to a
        # product_id so it can look up MUG_DIMS (which is keyed by product_id).
        mug_pid_json = json.dumps({_p.name: _p.product_id for _p in _MC})
    except Exception:  # noqa: BLE001 — never break the build on the mug catalog
        _mug_photos = {}
        mug_formats_json = "[]"
        mug_dims_json = "{}"
        mug_pid_json = "{}"

    # Per-product tile photos for the Custom Calendars grid, keyed by product_id
    # (brand/tile-<product_id>.jpg, e.g. tile-wall_cal.jpg). Falls back to the
    # section's neutral SVG tile when a photo is absent - mirrors the mug grid.
    # Customer-safe only (no supplier data).
    _cal_photos: dict = {}
    cal_formats_json = "[]"
    cal_dims_json = "{}"
    cal_pid_json = "{}"
    try:
        from quoteforge.etsy.calendar_catalog import (
            CALENDAR_CATALOG as _CC, build_calendar_variations as _bcv)
        for _p in _CC:
            _cp = next((brand / f"tile-{_p.product_id}.{e}" for e in ("jpg", "png")
                        if (brand / f"tile-{_p.product_id}.{e}").exists()), None)
            if _cp:
                _cal_photos[_p.product_id] = _emit(_cp, f"tile-{_p.product_id}.jpg")
        # Cheapest price per (product, paper-colour) for the editor's calendar picker.
        _cc_from: dict = {}
        for _v in _bcv():
            _key = (_v.product_id, _v.color)
            _cc_from[_key] = min(_cc_from.get(_key, 1e9), _v.price)
        _cname = {_p.product_id: _p.name for _p in _CC}
        cal_formats = [
            {"name": f"{_cname[_pid]} - {_col}", "price": round(_pr, 2)}
            for (_pid, _col), _pr in _cc_from.items() if _pid in _cname]
        cal_formats_json = json.dumps(cal_formats)
        cal_dims_json = json.dumps(
            {_p.product_id: [_p.width_px, _p.height_px] for _p in _CC})
        # Editor maps the picked product NAME (what shopCalendar carries) back to a
        # product_id so it can look up CAL_DIMS (which is keyed by product_id).
        cal_pid_json = json.dumps({_p.name: _p.product_id for _p in _CC})
    except Exception:  # noqa: BLE001 — never break the build on the calendar catalog
        _cal_photos = {}
        cal_formats_json = "[]"
        cal_dims_json = "{}"
        cal_pid_json = "{}"

    # ── Real product-photo mockups (owner-supplied drop-in; auto-upgrade) ──────
    # Keyed by product NAME (what the editor's CURGARMENT carries). Drop a real
    # product photo at brand/mockups/<product_id>.{png,jpg} (export it once from
    # the print partner's mockup studio) plus an optional sidecar
    # <product_id>.json = {"area":[x,y,w,h fractions],"cyl":bool,"span":float}
    # marking where the print sits on the photo. The editor then composites the
    # LIVE design into that print area and shows a REAL product picture in the
    # preview. Empty until photos exist -> the editor's generated mockup is used,
    # so a half-set-up account never ships a broken image. Customer-safe: only the
    # image bytes + geometry are emitted, never a supplier/marketplace name.
    mockup_photos: dict = {}
    try:
        _id2name: dict = {}
        for _m in (appgid, json.loads(branded_pid_json), json.loads(mug_pid_json),
                   json.loads(cal_pid_json)):
            for _nm, _id in (_m or {}).items():
                _id2name[str(_id)] = _nm
        _mockdir = brand / "mockups"
        if _mockdir.is_dir():
            for _img in sorted(_mockdir.iterdir()):
                if _img.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    continue
                _name = _id2name.get(_img.stem)
                if not _name:
                    continue
                _geo: dict = {}
                _side = _mockdir / f"{_img.stem}.json"
                if _side.exists():
                    try:
                        _geo = json.loads(_side.read_text(encoding="utf-8"))
                    except Exception:  # noqa: BLE001 — bad sidecar -> defaults
                        _geo = {}
                _ln = _name.lower()
                _cyl = bool(_geo.get(
                    "cyl", "mug" in _ln or "bottle" in _ln or "tumbler" in _ln))
                _area = _geo.get("area") or (
                    [0.33, 0.34, 0.34, 0.34] if _cyl else [0.28, 0.26, 0.44, 0.50])
                mockup_photos[_name] = {
                    "src": _emit(_img, f"mockup-{_img.stem}.jpg"),
                    "area": _area, "cyl": _cyl,
                    "span": float(_geo.get("span", 1.9)),
                }
    except Exception:  # noqa: BLE001 — never break the build on mockup discovery
        mockup_photos = {}
    # Merge in the CONFIRMED auto-synced print-partner photos (the daily mockup-sync:
    # only products both review agents passed reach live_mockups()). Each master is
    # re-emitted into docs/assets (same-origin, no supplier URL). A manual
    # brand/mockups entry for the same product wins (set above). Empty until live.
    try:
        from quoteforge.automation.mockup_sync import live_mockups as _live_mockups
        for _nm, _spec in (_live_mockups() or {}).items():
            if _nm in mockup_photos:
                continue                       # manual override already set
            _src = _spec.get("src") or ""
            _master = Path(_src)
            _url = (_emit(_master, f"mockup-auto-{_master.stem}.jpg")
                    if _src and _master.exists() else _src)
            if not _url:
                continue
            mockup_photos[_nm] = {"src": _url, "area": _spec.get("area"),
                                  "cyl": bool(_spec.get("cyl")),
                                  "span": float(_spec.get("span", 1.9))}
    except Exception:  # noqa: BLE001 — never break the build on the sync catalog
        pass
    mockup_photos_json = json.dumps(mockup_photos)

    # Optional shop-logo overlay for the 'logo on front & back' toggle. Emitted as
    # PNG so its transparency is preserved on the garment (a flattened JPG boxes it
    # in white).
    def _emit_png(src: Path, fname: str, max_dim: int = 260) -> str:
        """Emit a transparency-preserving PNG (asset file, or a data URI inline)."""
        from PIL import Image
        im = Image.open(src).convert("RGBA")
        im.thumbnail((max_dim, max_dim))
        if external_assets:
            assets.mkdir(parents=True, exist_ok=True)
            im.save(assets / fname)
            return f"assets/{fname}"
        import base64
        import io
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    _glogo = next((brand / n for n in ("joffiels_logo.png",
                   "joffiels_logo_green_gold.png") if (brand / n).exists()), None)
    garment_logo_src = _emit_png(_glogo, "garment-logo.png") if _glogo else ""

    pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest() if password else ""

    # Order-by gift-deadline banner (urgency) + verified reviews summary.
    try:
        from quoteforge.etsy.shipping_cutoff import upcoming_cutoff, banner_text
        _cut = upcoming_cutoff()
        cutoff_html = (f'<div class="cutoff">⏰ {banner_text(_cut)}</div>'
                       if _cut else "")
    except Exception:  # noqa: BLE001
        cutoff_html = ""
    try:
        reviews_html = _reviews_section()
    except Exception:  # noqa: BLE001
        reviews_html = ""
    try:
        from quoteforge.etsy.social_proof import social_proof_bar, customer_gallery
        sproof_html = social_proof_bar()
        gallery_html = customer_gallery()
    except Exception:  # noqa: BLE001
        sproof_html = gallery_html = ""
    try:
        from quoteforge.ai.ange import kb_for_web
        ange_kb_json = json.dumps(kb_for_web())
    except Exception:  # noqa: BLE001
        ange_kb_json = "[]"
    try:
        from quoteforge.config import ASK_ANGE_API_URL as ask_api_url
    except Exception:  # noqa: BLE001
        ask_api_url = ""
    try:
        from quoteforge.config import SIGNUP_URL as signup_url
    except Exception:  # noqa: BLE001
        signup_url = ""
    try:
        from quoteforge.etsy.packages import packages_section
        from quoteforge.config import B2B_CONTACT_EMAIL as _b2b
        # Fold the wholesale-quote form INTO the packages section (one corporate
        # area, not two) so the page isn't redundant.
        packages_html = packages_section(_b2b or owner, _b2b_form(owner))
    except Exception:  # noqa: BLE001
        packages_html = ""

    gate = "" if not password else f"""
<div id="gate">
  <div class="gatebox">
    {f'<img src="{logo_src}" class="glogo" alt="{SHOP_NAME} logo">' if logo_src else ''}
    <h2>{SHOP_NAME}</h2>
    <p>This preview is private. Please enter the password to view.</p>
    <input id="pw" type="password" aria-label="Password" placeholder="Password" onkeydown="if(event.key==='Enter')check()">
    <button onclick="check()">View</button>
    <div id="err">Incorrect password - please try again.</div>
  </div>
</div>
<script>
 const H="{pw_hash}";
 async function sha(s){{const b=await crypto.subtle.digest('SHA-256',
   new TextEncoder().encode(s));return [...new Uint8Array(b)].map(
   x=>x.toString(16).padStart(2,'0')).join('');}}
 async function check(){{const v=document.getElementById('pw').value;
   if(await sha(v)===H){{sessionStorage.setItem('jf','1');show();}}
   else{{document.getElementById('err').style.display='block';}}}}
 function show(){{document.getElementById('gate').style.display='none';
   document.getElementById('site').style.display='block';}}
 if(sessionStorage.getItem('jf')==='1')show();
</script>"""

    site_style = "display:none" if password else "display:block"
    # A password-gated preview must never be indexed - the gate is client-side
    # only (all content is in the DOM), so without this a crawler can index the
    # unfinished page. Dropped automatically when the gate is removed for launch.
    robots_meta = ('<meta name="robots" content="noindex,nofollow">\n'
                   if password else '')
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{robots_meta}<title>Personalized Wall Art Gifts for Any Occasion | {SHOP_NAME}</title>
<meta name="description" content="Personalized gifts made to order - custom wall art &amp; apparel with your wording, names &amp; photo. Free proof you approve before printing, happiness guarantee, shipped worldwide.">
<meta name="theme-color" content="#103d2e">
<link rel="canonical" href="https://joffiels.com/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SHOP_NAME}">
<meta property="og:title" content="Personalized Wall Art Gifts | {SHOP_NAME}">
<meta property="og:description" content="Custom wording &amp; your photo on museum-quality prints. FREE proof before printing, happiness guarantee.">
<meta property="og:url" content="https://joffiels.com/">
<meta property="og:image" content="https://joffiels.com/assets/hero.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Personalized Wall Art Gifts | {SHOP_NAME}">
<meta name="twitter:description" content="Custom wording &amp; your photo, FREE proof before printing.">
<meta name="twitter:image" content="https://joffiels.com/assets/hero.jpg">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='18' fill='%23103d2e'/%3E%3Ctext x='50' y='68' font-size='58' text-anchor='middle' fill='%23e8d8a8' font-family='Georgia,serif'%3EJ%3C/text%3E%3C/svg%3E">
<script type="application/ld+json">
{{"@context":"https://schema.org","@graph":[
{{"@type":"Organization","name":"{SHOP_NAME}","url":"https://joffiels.com/",
  "description":"Personalized, made-to-order wall art - custom wording and your photo on museum-quality prints.",
  "slogan":"Turn your words into art they'll treasure forever"}},
{{"@type":"WebSite","name":"{SHOP_NAME}","url":"https://joffiels.com/"}},
{{"@type":"Product","name":"Personalized Wall Art Print","brand":{{"@type":"Brand","name":"{SHOP_NAME}"}},
  "description":"Custom-wording personalized wall art, made to order in poster, framed, canvas, acrylic or metal. Free digital proof before printing.",
  "offers":{{"@type":"AggregateOffer","priceCurrency":"USD","lowPrice":"18.99","highPrice":"256.00","offerCount":"46","availability":"https://schema.org/InStock"}}}}
]}}
</script>
{_analytics_snippet()}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<!-- Core fonts (above-the-fold: headings + body) load normally. -->
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&display=swap" rel="stylesheet">
<!-- Personalization-editor preview fonts load async (non-render-blocking); ready by
     the time a buyer opens the editor, but they never delay first paint. -->
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Montserrat:wght@400;600&family=Lora:wght@400;600&family=Dancing+Script:wght@600;700&family=Oswald:wght@500;600;700&family=Bebas+Neue&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<noscript><link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Montserrat:wght@400;600&family=Lora:wght@400;600&family=Dancing+Script:wght@600;700&family=Oswald:wght@500&display=swap" rel="stylesheet"></noscript>
<style>
 :root{{--green:#103d2e;--green-d:#0b2c21;--gold:#c9a84c;--gold-d:#b3902f;
   --gold-ink:#8a6d1f;
   --cream:#f7f4ee;--ink:#23302b;--muted:#586259;--line:#e7e1d6}}
 *{{box-sizing:border-box}}
 @media(prefers-reduced-motion:reduce){{*,*::before,*::after{{
   animation-duration:.001ms!important;animation-iteration-count:1!important;
   transition-duration:.001ms!important;scroll-behavior:auto!important}}}}
 /* Readable pairing: the elegant Cormorant serif stays on headings & titles, but
    body + UI text uses Montserrat - a clean, legible sans (the display serif was
    hard to read in paragraphs/secondary text). System sans renders instantly. */
 body{{font-family:'Montserrat',system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
   font-weight:400;margin:0;
   background:var(--cream);color:var(--ink);line-height:1.65;font-size:17px;
   -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
   text-rendering:optimizeLegibility}}
 h1,h2,h3,h4,.serif,.depttitle,.ttl,.appname,.octitle,.pktitle,.angehdr,.apheroh,.fbn,.bn{{
   font-family:'Cormorant Garamond',Georgia,serif}}
 h1,h2,h3,.serif{{font-weight:700;letter-spacing:.3px;line-height:1.2}}
 /* every control/text inherits the page font so nothing falls back to the OS font.
    (Font-PICKER chips keep their inline preview font - that's intentional.) */
 button,input,select,textarea,label,a,span,div,li{{font-family:inherit}}
 .fchip{{font-family:inherit}}  /* overridden inline per-font for the preview */
 p{{margin:0 0 12px}}
 .intro p,.mdesc,.faq p{{font-size:15.5px;line-height:1.7;color:#33423a}}
 /* visible keyboard focus for accessibility */
 a:focus-visible,button:focus-visible,select:focus-visible,input:focus-visible,
 textarea:focus-visible,.occhip:focus-visible,.fchip:focus-visible,
 .sw span:focus-visible{{outline:3px solid var(--gold);outline-offset:2px;border-radius:6px}}
 a{{color:var(--green)}}
 /* gate */
 #gate{{position:fixed;inset:0;background:linear-gradient(160deg,#103d2e,#0b2c21);
   display:flex;align-items:center;justify-content:center;z-index:99;padding:20px}}
 .gatebox{{background:#fff;border-radius:18px;padding:40px 34px;max-width:380px;
   width:100%;text-align:center;box-shadow:0 24px 60px rgba(0,0,0,.35)}}
 .glogo{{width:120px;margin-bottom:6px}}
 .gatebox h2{{color:var(--green);margin:6px 0;font-size:30px}}
 .gatebox p{{color:var(--muted);font-size:14px;margin:6px 0 14px}}
 #pw{{width:100%;padding:13px 14px;border:1px solid #d6cfc1;border-radius:10px;
   font-size:16px;margin:6px 0;outline:none}}
 #pw:focus{{border-color:var(--gold)}}
 .gatebox button{{background:var(--green);color:#fff;border:none;padding:13px 0;
   width:100%;border-radius:30px;font-size:15px;font-weight:600;cursor:pointer;
   margin-top:8px;letter-spacing:.3px;transition:background .15s}}
 .gatebox button:hover{{background:var(--green-d)}}
 #err{{display:none;color:#b3261e;font-size:13px;margin-top:10px}}
 /* header + hero */
 .nav{{position:sticky;top:0;z-index:20;background:rgba(247,244,238,.92);
   backdrop-filter:blur(8px);border-bottom:1px solid var(--line);
   display:flex;align-items:center;justify-content:center;gap:12px;padding:12px}}
 .nav img{{height:34px}} .nav .bn{{font-family:'Cormorant Garamond',serif;
   font-size:24px;color:var(--green);font-weight:700;letter-spacing:1px}}
 .navquiz{{margin-left:14px;background:var(--gold);color:#22301e;border:none;
   border-radius:20px;padding:8px 16px;font-size:14px;font-weight:600;cursor:pointer}}
 .navquiz:hover{{background:var(--gold-d)}}
 .navbasket{{margin-left:10px;background:var(--green);color:#fff;border:none;
   border-radius:20px;padding:8px 16px;font-size:14px;font-weight:700;cursor:pointer}}
 .navbasket:hover{{background:var(--green-d)}}
 .navbasket #basketCountNav{{background:#fff;color:var(--green);border-radius:50%;
   padding:1px 8px;margin-left:4px;font-size:13px}}
 .navlinks{{display:flex;gap:18px;margin:0 14px}}
 .navlinks a{{color:var(--green);text-decoration:none;font-size:14px;font-weight:600;
   padding:9px 4px;display:inline-flex;align-items:center;min-height:34px;
   border-bottom:2px solid transparent}}
 .navlinks a:hover{{border-bottom-color:var(--gold)}}
 .navham{{display:none;background:none;border:1px solid var(--line);border-radius:10px;
   padding:5px 11px;font-size:19px;line-height:1;color:var(--green);cursor:pointer}}
 /* anchored sections clear the sticky header when jumped to */
 #depts,#grid,#wallart,#occasions,#apparel,#why,#faq{{scroll-margin-top:74px}}
 .depts{{max-width:1080px;margin:24px auto 8px;padding:0 16px;text-align:center}}
 .deptshead{{margin:0 0 14px;color:var(--green);font-size:20px;
   text-transform:uppercase;letter-spacing:.06em}}
 .deptgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}}
 @media(max-width:560px){{.deptgrid{{grid-template-columns:1fr 1fr;gap:12px}}}}
 @media(max-width:380px){{.deptgrid{{grid-template-columns:1fr}}}}
 .giftsets{{max-width:1080px;margin:18px auto 8px;padding:0 16px;text-align:center}}
 .gshead{{margin:0 0 14px;color:var(--green);font-size:20px;font-weight:800;
   text-transform:uppercase;letter-spacing:.06em}}
 .occrow{{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:0 0 18px}}
 .occchip{{appearance:none;cursor:pointer;border:1px solid var(--line);
   background:#fff;color:var(--green);font:inherit;font-weight:700;font-size:13px;
   padding:8px 14px;border-radius:999px;transition:background .15s,border-color .15s}}
 .occchip:hover{{background:var(--gold);border-color:var(--gold)}}
 .setgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
 .setcard{{background:#fff;border:1px solid var(--line);border-radius:14px;
   padding:16px;text-align:left;display:flex;flex-direction:column;gap:6px}}
 .setname{{color:var(--green);font-weight:800;font-size:16px}}
 .setitems{{color:#6b7280;font-size:13px;line-height:1.4;flex:1}}
 .setfrom{{color:var(--green);font-weight:700;font-size:15px;margin-top:2px}}
 .setcta{{appearance:none;cursor:pointer;border:0;background:var(--green);color:#fff;
   font:inherit;font-weight:700;font-size:14px;padding:9px 14px;border-radius:10px;
   margin-top:8px;transition:filter .15s}}
 .setcta:hover{{filter:brightness(1.08)}}
 .hiw{{max-width:1040px;margin:42px auto 8px;padding:0 16px;text-align:center}}
 .hiweyebrow{{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold-ink);
   font-weight:700;margin:0 0 8px}}
 .hiw h2{{color:var(--green);font-size:26px;margin:0 0 8px}}
 .hiwsub{{color:#5b6b62;max-width:560px;margin:0 auto 30px;font-size:15px}}
 .hiwsub b{{color:var(--gold-d);font-weight:700}}
 .hiwsteps{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;position:relative}}
 .hiwsteps::before{{content:"";position:absolute;top:63px;left:18%;right:18%;height:2px;z-index:0;
   background:repeating-linear-gradient(90deg,#d9cba0 0 8px,transparent 8px 16px)}}
 @media(max-width:720px){{.hiwsteps{{grid-template-columns:1fr}}.hiwsteps::before{{display:none}}}}
 .hiwstep{{position:relative;z-index:1;background:#fff;border:1px solid var(--line);border-radius:18px;
   padding:34px 20px 24px;display:flex;flex-direction:column;align-items:center;gap:7px;
   box-shadow:0 3px 16px rgba(16,61,46,.05);transition:transform .14s,box-shadow .14s}}
 .hiwstep:hover{{transform:translateY(-4px);box-shadow:0 14px 32px rgba(16,61,46,.12)}}
 .hiwstep::before{{content:"";position:absolute;top:0;left:26px;right:26px;height:3px;
   background:var(--gold);border-radius:0 0 3px 3px}}
 .hiwmed{{position:relative;width:58px;height:58px;border-radius:50%;background:var(--green);
   border:3px solid var(--gold);display:flex;align-items:center;justify-content:center;margin:0 auto 6px}}
 .hiwmed svg{{width:27px;height:27px;stroke:#fff;fill:none;stroke-width:1.7;
   stroke-linecap:round;stroke-linejoin:round}}
 .hiwnum{{position:absolute;bottom:-7px;right:-7px;width:23px;height:23px;border-radius:50%;
   background:var(--gold);color:var(--green);font-weight:700;display:flex;align-items:center;
   justify-content:center;font-size:12px;border:2px solid #fff}}
 .hiwt{{font-weight:700;color:var(--green);font-size:17px}}
 .hiwd{{color:#5b6b62;font-size:14px;line-height:1.5}}
 .hiwtrust{{display:flex;gap:20px;justify-content:center;flex-wrap:wrap;margin:24px auto 0;
   color:#5b6b62;font-size:12.5px}}
 .hiwtrust span{{display:inline-flex;align-items:center;gap:6px}}
 .hiwtrust svg{{width:15px;height:15px;stroke:var(--gold-d);fill:none;stroke-width:1.7;
   stroke-linecap:round;stroke-linejoin:round;flex:none}}
 .deptcard{{display:flex;flex-direction:column;text-decoration:none;
   border-radius:18px;overflow:hidden;border:1px solid #e6e0d2;background:#fff;
   box-shadow:0 2px 10px rgba(0,0,0,.05);transition:transform .14s,box-shadow .14s}}
 .deptcard:hover{{transform:translateY(-4px);box-shadow:0 14px 32px rgba(0,0,0,.14)}}
 .deptimg{{width:100%;height:210px;object-fit:cover;display:block}}
 .deptbody{{padding:18px 18px 22px;display:flex;flex-direction:column;
   align-items:center;gap:6px}}
 .deptwall .deptimg,.deptapp .deptimg{{background:#ece6da}}
 .depticon{{font-size:46px;line-height:1;padding:34px 0 0}}
 .depttitle{{font-weight:800;color:var(--green);font-size:24px}}
 .deptsub{{color:#5b5b52;font-size:14px;max-width:300px}}
 .deptgo{{margin-top:6px;font-weight:700;color:var(--gold-ink);font-size:15px}}
 .apparel-sec{{max-width:1080px;margin:34px auto;padding:0 16px;text-align:center}}
 .apparel-sec h2{{margin:0 0 6px;color:var(--green)}}
 .apparel-sec .apsub{{margin:0 auto 18px;max-width:620px;color:#5b5b52;font-size:15px}}
 .aphero{{position:relative;display:flex;align-items:stretch;border-radius:20px;
   overflow:hidden;margin:6px 0 26px;text-align:left;box-shadow:0 8px 30px rgba(16,61,46,.16);
   background:linear-gradient(105deg,#103d2e 0%,#16523c 52%,#1d6347 100%)}}
 .apherobody{{flex:1 1 52%;padding:34px 30px;display:flex;flex-direction:column;
   justify-content:center;align-items:flex-start;z-index:2}}
 .apheroeyebrow{{font-size:11px;letter-spacing:.2em;text-transform:uppercase;
   color:#e9d9a6;font-weight:700;margin-bottom:8px}}
 .aphero .apheroh{{color:#fff;font-size:28px;margin:0 0 8px;line-height:1.12}}
 .apherosub{{color:#d6e3da;font-size:14px;line-height:1.55;margin:0 0 16px;max-width:440px}}
 .apherocta{{background:var(--gold);color:var(--green);border:none;border-radius:24px;
   padding:11px 22px;font:inherit;font-weight:700;font-size:14px;cursor:pointer;
   transition:transform .14s,box-shadow .14s}}
 .apherocta:hover{{transform:translateY(-2px);box-shadow:0 10px 22px rgba(201,168,76,.4)}}
 .apheromedia{{flex:1 1 48%;position:relative;min-height:240px}}
 .apheroimg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}}
 .apheromedia::before{{content:"";position:absolute;inset:0;z-index:1;
   background:linear-gradient(90deg,#103d2e 0%,rgba(16,61,46,.4) 24%,transparent 58%)}}
 @media(max-width:720px){{.aphero{{flex-direction:column}}
   .apheromedia{{min-height:160px;order:-1}}
   .apheromedia::before{{background:linear-gradient(0deg,#103d2e 0%,transparent 62%)}}
   .apherobody{{padding:24px 22px}}.aphero .apheroh{{font-size:24px}}}}
 .appghead{{margin:22px 0 12px;color:var(--green);font-size:18px;text-align:left;
   text-transform:uppercase;letter-spacing:.05em}}
 .appgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
   gap:16px;margin-bottom:6px}}
 @media(max-width:640px){{.appgrid{{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}}}}
 .appcard,.brandcard{{display:flex;flex-direction:column;align-items:center;gap:6px;
   padding:12px 12px 18px;border:1px solid #ece7da;border-radius:16px;background:#fff;
   box-shadow:0 2px 10px rgba(0,0,0,.05);cursor:pointer;
   transition:transform .14s,box-shadow .14s,border-color .14s}}
 .appcard:hover,.brandcard:hover{{transform:translateY(-4px);
   box-shadow:0 14px 30px rgba(0,0,0,.13);border-color:var(--gold)}}
 .apptile{{display:flex;align-items:center;justify-content:center;width:100%;
   height:172px;border-radius:13px;margin-bottom:6px;
   box-shadow:inset 0 0 0 1px rgba(0,0,0,.03)}}
 .apptilephoto{{height:240px;overflow:hidden;background:#f1ede4}}
 .appimg{{width:100%;height:100%;object-fit:cover;display:block;border-radius:13px}}
 .appsvg{{width:118px;height:118px}}
 .appname{{font-weight:700;color:var(--green);font-size:18px;letter-spacing:.01em}}
 .apptier{{color:var(--gold-ink);font-size:12px;font-weight:600;letter-spacing:.02em}}
 .appfrom{{color:#7a7466;font-size:13px}}
 .appcta{{margin-top:3px;font-weight:700;color:var(--gold-ink);font-size:14px}}
 .appoccrow{{margin:2px 0 22px;text-align:center}}
 .appocceyebrow{{display:block;font-size:11px;letter-spacing:.18em;text-transform:uppercase;
   color:var(--gold-ink);font-weight:700;margin-bottom:6px}}
 .appocch{{margin:0 0 4px;color:var(--green);font-size:20px}}
 .appoccsub{{margin:0 auto 16px;max-width:560px;color:#5b6b62;font-size:14px}}
 .appoccchips{{display:flex;flex-wrap:wrap;gap:10px;justify-content:center}}
 .appocc{{display:flex;flex-direction:column;align-items:center;gap:8px;width:102px;
   padding:15px 8px 13px;border:1px solid var(--line);border-radius:16px;background:#fff;
   cursor:pointer;transition:transform .14s,box-shadow .14s,border-color .14s}}
 .appocc:hover{{transform:translateY(-3px);box-shadow:0 12px 24px rgba(16,61,46,.13);
   border-color:var(--gold)}}
 .appoccic{{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;
   justify-content:center}}
 .appoccic svg{{width:23px;height:23px;fill:none;stroke-width:1.7;stroke-linecap:round;
   stroke-linejoin:round}}
 .appocclbl{{font-size:12.5px;font-weight:600;color:var(--green);text-align:center}}
 @media(max-width:640px){{.appocc{{width:30%;min-width:92px}}}}
 .appsw{{display:flex;gap:6px;justify-content:center;flex-wrap:wrap;margin:2px 0 1px}}
 .swdot{{width:15px;height:15px;border-radius:50%;border:1px solid rgba(0,0,0,.22);
   cursor:pointer;transition:transform .12s,box-shadow .12s}}
 .swdot:hover{{transform:scale(1.18)}}
 .swdot.seldot{{box-shadow:0 0 0 2px #fff,0 0 0 4px var(--gold-d);transform:scale(1.12)}}
 .appfilters,.brandfilter{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
   margin:6px 0 24px;padding:13px 16px;background:#fff;border:1px solid var(--line);
   border-radius:16px;box-shadow:0 3px 16px rgba(16,61,46,.05)}}
 .appfilterlbl{{font-weight:700;color:var(--green);font-size:12px;letter-spacing:.09em;
   text-transform:uppercase;padding-right:2px}}
 .appfilter{{appearance:none;-webkit-appearance:none;min-width:122px;background:var(--cream);
   border:1px solid var(--line);border-radius:11px;padding:9px 30px 9px 13px;font:inherit;
   font-size:14px;color:var(--ink);cursor:pointer;background-repeat:no-repeat;
   background-position:right 11px center;
   background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M2 4l4 4 4-4' fill='none' stroke='%236b7a72' stroke-width='1.6'/></svg>")}}
 .appfilter:hover{{border-color:var(--gold);background-color:#fff}}
 .appfilter:focus{{outline:none;border-color:var(--gold-d);box-shadow:0 0 0 3px rgba(201,168,76,.25)}}
 .appfilterclear{{background:none;border:1px solid var(--line);border-radius:11px;
   padding:9px 15px;font:inherit;font-size:14px;color:var(--muted);cursor:pointer}}
 .appfilterclear:hover{{color:var(--ink);border-color:var(--gold)}}
 .appfiltercount{{margin-left:auto;color:var(--green);font-weight:600;font-size:13px;
   white-space:nowrap;background:var(--cream);border-radius:20px;padding:6px 13px}}
 @media(max-width:640px){{.appfilters{{padding:12px;gap:8px}}.appfilterlbl{{flex-basis:100%}}}}
 .appgroup.hide,.appcard.hide,.brandcard.hide{{display:none}}
 .apnomatch{{text-align:center;color:var(--muted);padding:22px 0;font-size:15px}}
 @media(max-width:640px){{.appfilter,.appfilterclear{{flex:1 1 42%}}
   .appfiltercount{{flex-basis:100%;margin:4px 0 0;text-align:center}}}}
 #basketBtnNav.pulse{{animation:basketpulse .5s ease 2}}
 /* gift finder quiz */
 #quiz{{position:fixed;inset:0;background:rgba(11,28,22,.62);display:none;z-index:70;
   align-items:flex-start;justify-content:center;overflow:auto;padding:24px}}
 .qbox{{background:#fff;border-radius:16px;max-width:560px;width:100%;margin:24px;
   padding:26px;box-shadow:0 30px 70px rgba(0,0,0,.4)}}
 .qbox h2{{color:var(--green);font-size:26px;margin:0 0 4px}}
 .qbox p.qsub{{color:var(--muted);margin:0 0 16px}}
 .qrow{{margin:10px 0}} .qrow label{{display:block;font-size:13px;color:var(--green);
   font-weight:600;margin-bottom:4px}}
 .qrow select{{width:100%;padding:11px;border:1px solid #cdbf98;border-radius:9px;
   font-size:15px}}
 .qgo{{background:var(--green);color:#fff;border:none;border-radius:26px;
   padding:13px;width:100%;font-size:16px;font-weight:600;cursor:pointer;margin-top:14px}}
 #qresult{{margin-top:16px;background:#f3efe6;border:1px solid var(--line);
   border-radius:12px;padding:16px;display:none}}
 #qresult h3{{color:var(--green);margin:0 0 6px}}
 .qclose{{float:right;font-size:24px;cursor:pointer;color:#9aa39d}}
 /* exit-intent capture */
 #exitpop{{position:fixed;inset:0;background:rgba(11,28,22,.66);display:none;z-index:80;
   align-items:center;justify-content:center;padding:24px}}
 .xbox{{background:#fff;border-radius:16px;max-width:460px;width:100%;
   padding:28px;text-align:center;box-shadow:0 30px 70px rgba(0,0,0,.45)}}
 .xbox h2{{color:var(--green);font-size:24px;margin:0 0 6px}}
 #xform{{display:flex;gap:8px;margin:14px 0 6px;flex-wrap:wrap}}
 #xform input{{flex:1;min-width:180px;padding:12px;border:1px solid #cdbf98;
   border-radius:9px;font-size:15px}}
 #xform .qgo{{width:auto;margin:0;padding:12px 18px;white-space:nowrap}}
 #xmsg{{font-size:14px;margin:6px 0}} #xmsg.xok{{color:var(--green)}}
 #xmsg.xbad{{color:#a23a3a}}
 /* abandoned-customization resume bar */
 #resumeBar{{display:none;position:fixed;left:12px;bottom:12px;z-index:75;
   align-items:center;gap:10px;background:#fff;border:1px solid var(--gold);
   border-radius:12px;padding:10px 14px;font-size:13.5px;color:var(--green);
   box-shadow:0 8px 26px rgba(0,0,0,.18);max-width:340px}}
 #resumeBar button{{background:var(--green);color:#fff;border:none;border-radius:18px;
   padding:7px 12px;font-size:13px;font-weight:600;cursor:pointer}}
 #resumeBar .rbx{{cursor:pointer;color:#9aa39d;font-size:18px}}
 /* wedding & corporate packages */
 .packages{{max-width:1100px;margin:46px auto;padding:0 20px;text-align:center}}
 .packages>summary.pksummary{{cursor:pointer;list-style:none;display:flex;
   flex-direction:column;align-items:center;gap:2px;padding:16px;border:1px solid var(--line);
   border-radius:14px;background:#fff}}
 .packages>summary.pksummary::-webkit-details-marker{{display:none}}
 .pktitle{{font-family:'Cormorant Garamond',serif;font-size:26px;color:var(--green);font-weight:600}}
 .pkhint{{color:var(--muted);font-size:13px}}
 .packages[open]>summary.pksummary{{margin-bottom:14px}}
 .packages h2{{font-size:28px;color:var(--green);margin:0 0 4px}}
 .packages .pksub{{color:var(--muted);max-width:680px;margin:0 auto 14px}}
 .pkgrouph{{color:var(--green);text-align:left;margin:22px 0 10px;font-size:18px}}
 .pkgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));
   gap:18px}}
 .pkcard{{background:#fff;border:1px solid var(--line);border-radius:14px;
   padding:18px;text-align:left;box-shadow:0 2px 12px rgba(0,0,0,.05)}}
 .pkname{{font-weight:700;color:var(--green);font-size:18px}}
 .pkfrom{{font-size:20px;color:#1b1b1f;margin:4px 0}}
 .pkfrom .pkpp{{font-size:12px;color:var(--muted);font-weight:400}}
 .pksave{{display:inline-block;background:#f3efe0;color:#5a4a2a;font-size:11.5px;
   padding:2px 8px;border-radius:10px;margin-bottom:6px}}
 .pkblurb{{color:var(--muted);font-size:13.5px;line-height:1.5;margin:6px 0}}
 .pkinc{{margin:6px 0 12px 18px;padding:0;color:#3a4a42;font-size:13px}}
 .pkinc li{{margin:3px 0}}
 .pkcta{{display:inline-block;background:var(--green);color:#fff;text-decoration:none;
   border-radius:22px;padding:9px 16px;font-size:14px;font-weight:600}}
 /* bundle builder */
 .bundle{{max-width:1000px;margin:34px auto;padding:18px 22px;text-align:center;
   background:#fbf7ee;border:1px dashed var(--gold);border-radius:16px}}
 .bundlehdr{{display:flex;align-items:center;justify-content:space-between;gap:16px;
   text-align:left;flex-wrap:wrap}}
 .bundlehdr .gsub{{margin:4px 0 0;max-width:640px}}
 .bundle h2{{font-size:21px;color:var(--green);margin:0}}
 .bundletoggle{{background:var(--green);color:#fff;border:none;border-radius:22px;
   padding:11px 20px;font-size:14.5px;font-weight:700;cursor:pointer;white-space:nowrap}}
 .bundletoggle:hover{{background:var(--green-d)}}
 .bgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
   gap:10px;margin:14px 0}}
 .bopt{{position:relative;border:1px solid var(--line);border-radius:10px;padding:8px;
   cursor:pointer;background:#fff;font-size:12px;transition:box-shadow .12s,transform .12s}}
 .bopt:hover{{box-shadow:0 4px 14px rgba(0,0,0,.12);transform:translateY(-2px)}}
 .bopt.sel{{border-color:var(--green);box-shadow:0 0 0 2px var(--green)}}
 .bopt img{{width:100%;border-radius:6px;aspect-ratio:1/1;object-fit:cover}}
 .bcheck{{position:absolute;top:6px;right:6px;width:24px;height:24px;border-radius:50%;
   background:#fff;border:1px solid var(--line);color:#9aa39d;font-weight:700;
   display:flex;align-items:center;justify-content:center;font-size:14px}}
 .bopt.sel .bcheck{{background:var(--green);border-color:var(--green);color:#fff}}
 .btot{{font-size:15px;font-weight:600;color:var(--muted);margin:14px auto 0;
   max-width:760px;padding:12px 16px;border-radius:12px;background:#f6f2e7;
   border:1px dashed var(--line)}}
 .btot.on{{position:sticky;bottom:12px;z-index:60;color:#22301e;background:var(--gold);
   border:none;box-shadow:0 8px 24px rgba(0,0,0,.18)}}
 .btot .bsave{{color:#0a6b3b}}
 .btot.on{{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px 16px}}
 .btotline{{font-size:15px}}
 .bsetbtn{{background:var(--green);color:#fff;border:none;border-radius:22px;
   padding:10px 18px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap}}
 .bsetbtn:hover{{background:var(--green-d)}}
 #bundlebanner{{background:#eef6f0;border-bottom:1px solid var(--line);color:var(--green);
   padding:11px 16px;font-size:13.5px;border-radius:14px 14px 0 0}}
 #bundlebanner .bskip{{color:#9aa39d;cursor:pointer;text-decoration:underline;
   margin-left:8px;font-size:12.5px}}
 .hero{{position:relative}} .hero-banner{{width:100%;display:block}}
 .hero-fallback{{background:linear-gradient(160deg,#103d2e,#0b2c21);color:#fff;
   padding:64px 20px;text-align:center}}
 .hero-fallback h1{{font-size:44px;margin:0;color:#fff}}
 .hero-overlay{{position:absolute;inset:0;display:flex;flex-direction:column;
   align-items:center;justify-content:center;text-align:center;
   background:linear-gradient(180deg,rgba(8,30,22,.34) 0%,rgba(8,30,22,.5) 48%,rgba(8,30,22,.56) 100%);color:#fff;padding:20px}}
 .hero-overlay h1{{font-size:clamp(30px,5vw,52px);margin:0;color:#fff;
   text-shadow:0 2px 18px rgba(0,0,0,.4)}}
 .hero-overlay p{{font-size:clamp(14px,2vw,19px);margin:10px 0 0;max-width:620px;
   text-shadow:0 1px 10px rgba(0,0,0,.45)}}
 .herocta{{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;margin-top:22px}}
 .btn-shop{{background:var(--gold);color:#22301e;text-decoration:none;font-weight:700;
   font-size:16px;padding:13px 28px;border-radius:26px;box-shadow:0 6px 20px rgba(0,0,0,.25);
   transition:transform .12s,background .15s}}
 .btn-shop:hover{{background:var(--gold-d);transform:translateY(-2px)}}
 .btn-find{{background:rgba(255,255,255,.16);color:#fff;border:1.5px solid rgba(255,255,255,.7);
   font-weight:600;font-size:16px;padding:12px 24px;border-radius:26px;cursor:pointer;
   font-family:inherit;backdrop-filter:blur(2px)}}
 .btn-find:hover{{background:rgba(255,255,255,.28)}}
 .heroprice{{margin:13px 0 0;font-size:14px;color:#efe6cf;text-shadow:0 1px 8px rgba(0,0,0,.5)}}
 .heroprice b{{color:#fff}}
 .orderreassure{{margin:8px 0 2px;font-size:12.5px;color:var(--muted);text-align:center}}
 /* trust bar */
 .trust{{display:flex;flex-wrap:wrap;justify-content:center;gap:8px 30px;
   background:var(--green);color:#eadfb9;padding:13px 16px;font-size:13px;
   letter-spacing:.4px;text-align:center}}
 .trust b{{color:#fff;font-weight:600}}
 /* social proof (real data only) */
 .sproof{{display:flex;flex-wrap:wrap;justify-content:center;gap:10px 34px;
   background:#fbf7ee;color:#5a4a2a;padding:11px 16px;font-size:13.5px;
   text-align:center;border-bottom:1px solid #ece3cf}}
 .sproof .spi b{{color:var(--green);font-weight:700;font-size:15px}}
 /* customer gallery (real photos only) */
 .cgallery{{max-width:1100px;margin:40px auto;padding:0 20px;text-align:center}}
 .cgallery h2{{font-size:28px;color:var(--green);margin:0 0 4px}}
 .cgallery .csub{{color:var(--muted);margin:0 0 18px}}
 .ggrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
   gap:14px}}
 .gtile{{margin:0;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.08)}}
 .gtile img{{width:100%;height:170px;object-fit:cover;display:block}}
 .gtile figcaption{{font-size:11.5px;color:#6b7a72;padding:6px 4px}}
 .cgallery .cshare{{margin-top:16px;color:var(--muted);font-size:13px}}
 .intro{{text-align:center;max-width:680px;margin:34px auto 6px;padding:0 20px}}
 .intro h2{{font-size:30px;color:var(--green);margin:0 0 8px}}
 .intro p{{color:var(--muted);font-size:16px;line-height:1.6;margin:0}}
 /* Shop-by-occasion showcase */
 .occasions{{max-width:1200px;margin:30px auto 8px;padding:0 20px;text-align:center}}
 .occasions h2{{font-size:30px;color:var(--green);margin:0 0 4px}}
 .ocintro{{color:var(--muted);max-width:620px;margin:0 auto 18px}}
 .ocgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
   gap:16px}}
 .occard{{background:#fff;border:1px solid var(--line);border-radius:16px;
   overflow:hidden;cursor:pointer;padding:0;text-align:left;
   box-shadow:0 2px 12px rgba(0,0,0,.05);transition:transform .15s,box-shadow .15s}}
 .occard:hover{{transform:translateY(-4px);box-shadow:0 14px 32px rgba(0,0,0,.14)}}
 .ocimg{{width:100%;height:140px;object-fit:cover;display:block}}
 .ocfallback{{display:flex;align-items:center;justify-content:center}}
 .ocemoji{{font-size:72px;filter:drop-shadow(0 4px 10px rgba(0,0,0,.12))}}
 .occap{{padding:14px 16px 18px}}
 .octitle{{font-family:'Cormorant Garamond',serif;font-size:20px;font-weight:600;
   color:var(--green)}}
 .ocsub{{color:var(--muted);font-size:13px;margin-top:2px}}
 .occap{{padding:11px 13px 14px}}
 .ocall{{margin-top:18px}}
 .grid{{max-width:1200px;margin:26px auto 50px;display:grid;
   grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:26px;padding:0 20px}}
 .card{{background:#fff;border:1px solid var(--line);border-radius:14px;
   overflow:hidden;cursor:pointer;transition:transform .18s,box-shadow .18s;
   display:flex;flex-direction:column;position:relative}}
 .card:hover{{transform:translateY(-5px);box-shadow:0 14px 34px rgba(16,61,46,.14)}}
 .card .hero{{width:100%;display:block;aspect-ratio:1/1;object-fit:cover}}
 /* Honest editorial "Editor's pick" ribbon (owner-curated, not fabricated sales). */
 .epick{{position:absolute;top:10px;left:10px;z-index:2;background:var(--green);
   color:#fff;font-size:11px;font-weight:700;padding:4px 9px;border-radius:999px;
   box-shadow:0 2px 6px rgba(0,0,0,.18)}}
 .cap{{padding:14px 16px 18px}}
 .ttl{{font-size:15px;line-height:1.5;height:66px;overflow:hidden;color:#2b3a33}}
 .pr{{margin-top:10px;font-weight:600;color:var(--green);font-size:17px}}
 .pr small{{color:var(--muted);font-weight:400;font-size:12px}}
 .prsub{{font-size:11px;color:var(--muted);margin-top:2px}}
 .fb{{display:inline-block;margin-top:10px;font-size:12px;color:var(--green);
   text-decoration:none;border:1px solid var(--green);border-radius:16px;
   padding:5px 12px;transition:.15s}}
 .card:hover .fb{{background:var(--green);color:#fff}}
 .uatbar{{max-width:1160px;background:#fffaf0;border:1px solid #f0e2bd;
   color:#6b5a2b;margin:16px auto 0;padding:13px 18px;border-radius:10px;
   font-size:14px;text-align:center;line-height:1.55}}
 .uatbar a{{color:var(--green);font-weight:600}}
 /* ── Design pass: hierarchy, steps, trust, mobile CTA ───────────── */
 .seefinal{{display:block;margin:8px auto 2px;background:#fff;border:2px solid var(--green);
   color:var(--green);border-radius:20px;padding:8px 18px;font-weight:800;font-size:14px;
   cursor:pointer;font-family:inherit}}
 .seefinal:hover{{background:var(--green);color:#fff}}
 .dbq{{display:block;margin-bottom:7px;font-weight:700}}
 .dbq small{{color:var(--muted);font-weight:400}}
 .grabtip{{display:inline-flex;align-items:center;gap:6px;background:#e7f1ea;color:#15643c;
   border:1px solid #bcd9c8;border-radius:20px;padding:3px 11px;font-weight:600;font-size:13px;
   white-space:nowrap}}
 .grabsq{{width:12px;height:12px;border-radius:2px;background:#15643c;box-shadow:0 0 0 1.5px #fff,0 0 0 3px #15643c;flex:none}}
 .grabtip-blue{{background:#e6eff8;color:#1763b8;border-color:#bcd2ec}}
 .grabsq-blue{{background:#1763b8;box-shadow:0 0 0 1.5px #fff,0 0 0 3px #1763b8}}
 .gridmorewrap{{text-align:center;margin:4px 0 10px}}
 .gridmore{{background:#fff;border:1.5px solid var(--gold);color:var(--green);border-radius:24px;
   padding:11px 26px;font:inherit;font-weight:700;font-size:15px;cursor:pointer;
   box-shadow:0 3px 14px rgba(16,61,46,.08);transition:transform .14s,box-shadow .14s}}
 .gridmore:hover{{transform:translateY(-2px);box-shadow:0 10px 22px rgba(201,168,76,.25);background:#fffdf6}}
 .deptswitch{{display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap;
   max-width:1080px;margin:18px auto 2px;padding:0 16px}}
 .deptswitch button{{background:#fff;border:1.5px solid var(--line);border-radius:22px;
   padding:9px 20px;font:inherit;font-weight:600;font-size:14px;color:var(--green);cursor:pointer;
   transition:background .14s,color .14s,border-color .14s}}
 .deptswitch button.on{{background:var(--green);color:#fff;border-color:var(--green)}}
 .deptswitch .dsall{{border-style:dashed;color:var(--muted)}}
 .deptswitch .dsall:hover{{color:var(--ink);border-color:var(--gold)}}
 .dseg{{display:inline-flex;border:1.5px solid var(--green);border-radius:22px;overflow:hidden}}
 .dseg .dmbtn{{border:none;border-radius:0;margin:0;padding:9px 16px;background:#fff;
   color:var(--green);font-weight:700;cursor:pointer;font-family:inherit}}
 .dseg .dmbtn.sel{{background:var(--green);color:#fff}}

 .pdone{{background:var(--green);color:#fff;border:none;border-radius:16px;
   padding:7px 13px;font-weight:700;cursor:pointer;font-family:inherit}}
 .pdone:hover{{background:var(--gold);color:#22301e}}

 .fb{{display:inline-block;background:var(--green);color:#fff;border-radius:20px;
   padding:9px 16px;font-weight:700;font-size:13.5px;text-align:center}}
 .card:hover .fb{{background:var(--gold);color:#22301e}}
 .quiznudge{{text-align:center;margin:-6px 0 14px;font-size:14px;color:var(--muted)}}
 .quiznudge a{{color:var(--green);font-weight:700;text-decoration:underline}}
 #grid .card .hero{{aspect-ratio:1/1;object-fit:cover}}  /* no layout shift */

 .postadd{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
   background:#eef7ef;border:1.5px solid #3f7d5c;border-radius:12px;
   padding:11px 14px;margin:10px 0}}
 .paok{{color:#2c6e49;font-weight:800;font-size:14px}}
 .pacontinue{{background:#fff;border:1.5px solid var(--green);color:var(--green);
   border-radius:20px;padding:8px 15px;font-weight:700;cursor:pointer;font-family:inherit}}
 .pacheckout{{background:var(--green);border:none;color:#fff;border-radius:20px;
   padding:9px 17px;font-weight:700;cursor:pointer;font-family:inherit}}
 .pacheckout:hover{{background:var(--gold);color:#22301e}}

 .mtrust{{font-size:12.5px;color:#3f7d5c;font-weight:600;margin:-2px 0 10px;letter-spacing:.2px}}
 /* Consistent, taller product cards with equal heights in each row. */
 #grid .card{{display:flex;flex-direction:column}}
 #grid .card .cap{{flex:1;display:flex;flex-direction:column}}
 #grid .card .cap .fb{{margin-top:auto}}
 .ttl{{font-size:19px;font-weight:600;letter-spacing:.2px}}
 .pr{{font-size:21px}}
 .cardtrust{{display:block;margin-top:8px;font-size:11.5px;color:#3f7d5c;
   font-weight:600;letter-spacing:.2px}}
 /* Step-numbered personalization: each section label auto-numbers itself so
    the editor reads as a guided 1-2-3 flow instead of a wall of options. */
 .perso{{counter-reset:pstep}}
 .perso>.lbl::before{{counter-increment:pstep;content:"Step " counter(pstep) " - ";
   color:var(--gold-d);font-weight:800}}
 /* Thumb-zone CTA: on phones the add-to-basket bar sticks to the bottom of the
    modal so the buy action is always one thumb-tap away. */
 @media(max-width:760px){{
   #mbasketbar{{position:sticky;bottom:0;background:rgba(255,255,255,.97);
     padding:10px 4px;margin:0 -4px;box-shadow:0 -8px 18px rgba(0,0,0,.10);z-index:6}}
 }}
 /* back-to-top (bottom-left, clears the Ask Ange button on the right) */
 #toTop{{position:fixed;left:20px;bottom:20px;z-index:60;display:none;
   align-items:center;justify-content:center;width:46px;height:46px;border:none;
   border-radius:50%;background:var(--green);color:#fff;font-size:20px;cursor:pointer;
   box-shadow:0 4px 16px rgba(0,0,0,.25)}}
 #toTop:hover{{background:var(--gold);color:#22301e}}
 /* Ask Ange chat */
 #basketBtn{{position:fixed;left:20px;bottom:20px;z-index:60;background:var(--gold);
   color:#22301e;border:none;border-radius:30px;padding:13px 20px;font-size:15px;
   font-weight:700;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.28)}}
 #basketBtn:hover{{background:var(--gold-d)}}
 #basketBtn #basketCount{{background:#22301e;color:#fff;border-radius:50%;
   padding:1px 8px;margin-left:4px;font-size:13px}}
 #basketPanel{{position:fixed;inset:0;z-index:81;background:rgba(11,28,22,.55);
   display:none;align-items:center;justify-content:center;padding:24px}}
 .bpbox{{background:#fff;border-radius:16px;max-width:460px;width:100%;padding:24px;
   box-shadow:0 30px 70px rgba(0,0,0,.45);max-height:86vh;overflow:auto}}
 .bpbox h2{{color:var(--green);margin:0 0 12px;font-size:22px}}
 .bpline{{display:flex;justify-content:space-between;gap:10px;padding:8px 0;
   border-bottom:1px solid var(--line);font-size:13.5px;text-align:left}}
 .bptot{{display:grid;grid-template-columns:1fr auto;gap:2px 10px;font-weight:700;
   color:var(--green);padding:10px 0;font-size:16px}}
 .bptot .bptax{{font-weight:400;color:var(--muted);font-size:13px}}
 .bptaxnote{{font-size:11.5px;color:var(--muted);margin-bottom:8px}}
 .taxnote{{background:#f6f2e7;border-radius:8px;padding:8px 10px}}
 .bpactions{{display:flex;gap:10px;margin-top:8px}}
 .bpclear{{flex:1;background:#fff;border:1px solid var(--line);border-radius:22px;
   padding:11px;font-size:14px;cursor:pointer;color:#a23a3a}}
 .bpco{{flex:2;background:var(--green);color:#fff;border:none;border-radius:22px;
   padding:11px;font-size:15px;font-weight:600;cursor:pointer}}
 #angeBtn{{position:fixed;right:20px;bottom:20px;z-index:60;background:var(--green);
   color:#fff;border:none;border-radius:30px;padding:13px 20px;font-size:15px;
   font-weight:600;cursor:pointer;box-shadow:0 8px 24px rgba(16,61,46,.35)}}
 #angeBtn:hover{{background:var(--green-d)}}
 #angePanel{{position:fixed;right:20px;bottom:78px;z-index:61;width:340px;
   max-width:92vw;background:#fff;border:1px solid var(--line);border-radius:16px;
   box-shadow:0 20px 50px rgba(0,0,0,.3);display:none;overflow:hidden}}
 .angehdr{{background:var(--green);color:#e8d8a8;padding:13px 16px;
   font-family:'Cormorant Garamond',serif;font-size:20px}}
 .angehdr small{{display:block;font-family:inherit;font-size:11px;
   color:#cfe0d6}}
 #angeMsgs{{height:300px;overflow:auto;padding:12px;background:#f7f4ee}}
 .amsg{{margin:6px 0;padding:9px 12px;border-radius:12px;font-size:13.5px;
   line-height:1.5;max-width:85%}}
 .amsg.bot{{background:#fff;border:1px solid var(--line)}}
 .amsg.me{{background:var(--green);color:#fff;margin-left:auto}}
 .achips{{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px;background:#f7f4ee}}
 .achip{{background:#fff;border:1px solid #cdbf98;border-radius:14px;padding:5px 10px;
   font-size:12px;cursor:pointer}}
 .angein{{display:flex;border-top:1px solid var(--line)}}
 .angein input{{flex:1;border:none;padding:12px;font-size:14px;outline:none}}
 .angein button{{background:var(--gold);border:none;padding:0 16px;cursor:pointer;
   font-weight:700;color:#22301e}}
 .cutoff{{background:#7a2e2e;color:#ffe9cf;text-align:center;padding:11px 16px;
   font-size:14px;font-weight:600;letter-spacing:.3px}}
 .reviews{{max-width:1100px;margin:34px auto;padding:0 20px;text-align:center}}
 .reviews h2{{font-size:28px;color:var(--green);margin:0 0 8px}}
 .rvsum{{display:flex;gap:10px;justify-content:center;align-items:baseline;margin-bottom:16px}}
 .rvbig{{font-size:34px;font-weight:700;color:var(--green)}}
 .rvsum .rvstars{{color:var(--gold);font-size:20px}} .rvn{{color:var(--muted);font-size:14px}}
 .rvgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
 .rvcard{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;text-align:left}}
 .rvcard .rvstars{{color:var(--gold)}} .rvimg{{width:100%;border-radius:8px;margin:8px 0}}
 .rvtext{{font-size:14px;color:#3a463f;line-height:1.5}}
 .rvname{{font-size:12px;color:var(--muted);margin-top:8px}}
 .vrf{{color:#15633f;font-weight:600}}
 .shopocc{{max-width:1000px;margin:18px auto 0;padding:0 24px;text-align:center;
   box-sizing:border-box}}
 .shopocc .lbl{{font-size:13px;color:var(--muted);margin-bottom:8px}}
 .occrow{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;
   padding:0 4px;max-width:100%}}
 .occhip{{background:#fff;border:1px solid var(--line);border-radius:18px;
   padding:7px 14px;font-size:13px;color:var(--green);cursor:pointer}}
 .occhip:hover{{border-color:var(--gold)}}
 .occback{{margin-left:10px;background:var(--green);color:#fff;border:none;
   border-radius:16px;padding:5px 13px;font-size:13px;font-weight:600;
   cursor:pointer;font-family:inherit}}
 .occback:hover{{background:var(--gold)}}
 .occallcard{{display:flex;align-items:center;justify-content:center;
   background:#f3f1ea;border:1.5px dashed var(--green)}}
 .occallinner{{text-align:center;padding:24px}}
 .occallicon{{font-size:30px;color:var(--green);line-height:1}}
 .occalltitle{{font-size:15px;color:var(--green);font-weight:600;margin:8px 0 12px}}
 .occallbtn{{background:var(--green);color:#fff;border:none;border-radius:22px;
   padding:10px 20px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}}
 .occallbtn:hover{{background:var(--gold)}}
 .occbottom{{text-align:center;margin:22px 0 4px}}
 .occhip.sel{{background:var(--green);color:#fff;border-color:var(--green)}}
 .qjwrap{{max-width:640px;margin:0 auto 18px;border:2px solid var(--gold);
   border-radius:16px;background:linear-gradient(135deg,#fff8e8,#fff);
   padding:4px 10px;box-shadow:0 6px 22px rgba(201,168,76,.25);
   animation:qjglow 2.2s ease-in-out infinite}}
 @keyframes qjglow{{0%,100%{{box-shadow:0 6px 22px rgba(201,168,76,.25)}}
   50%{{box-shadow:0 6px 30px rgba(201,168,76,.55)}}}}
 .qjwrap:hover{{transform:translateY(-2px)}}
 .qjwrap>summary.qjsum{{cursor:pointer;list-style:none;text-align:center;
   padding:11px;color:var(--green);font-weight:800;font-size:18px}}
 .qjwrap>summary.qjsum::-webkit-details-marker{{display:none}}
 .qjsum small{{display:block;color:var(--muted);font-weight:400;font-size:12px}}
 .qjwrap[open]{{padding-bottom:12px}}
 .quickjump{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;
   max-width:1100px;margin:0 auto 16px;padding:0 14px}}
 .qjt{{border:1px solid var(--line);background:#fff;border-radius:10px;padding:5px;
   cursor:pointer;width:74px;text-align:center;font-family:inherit}}
 .qjt:hover{{border-color:var(--gold);transform:translateY(-2px)}}
 .qjt img{{width:62px;height:62px;object-fit:cover;border-radius:7px;display:block}}
 .qjt span{{font-size:10px;color:var(--green);font-weight:600;display:block;
   margin-top:3px;text-transform:capitalize;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
 .gridcount{{text-align:center;color:var(--green);font-weight:600;font-size:14px;
   letter-spacing:.3px;margin:6px 0 14px;text-transform:uppercase;opacity:.85}}
 .occnote{{text-align:center;color:var(--muted);font-size:13px;margin:8px 0 -8px}}
 .baddlbl{{font-size:11px;color:var(--green);font-weight:600;margin-top:3px}}
 .bopt.sel .baddlbl{{color:#0a6b3b}}
 .why{{max-width:760px;margin:34px auto 10px;padding:0 20px;text-align:center}}
 .why h2{{font-size:28px;color:var(--green);margin:0 0 12px}}
 .cmp{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);
   border-radius:12px;overflow:hidden}}
 .cmp th{{background:var(--green);color:#fff;padding:10px;font-size:14px}}
 .cmp td{{padding:10px 12px;font-size:13px;border-top:1px solid var(--line);
   text-align:left;width:50%}}
 .cmp td.us{{color:#15633f;font-weight:600}} .cmp td.them{{color:#9aa39d}}
 .guarantee{{max-width:760px;margin:18px auto;padding:16px 20px;text-align:center;
   background:#eaf3ee;border:1px solid #cfe3d6;border-radius:12px;color:#22463a;
   font-size:15px}}
 .faqs{{max-width:760px;margin:24px auto;padding:0 20px}}
 .faqs h2{{font-size:26px;color:var(--green);text-align:center;margin:0 0 12px}}
 .faq{{background:#fff;border:1px solid var(--line);border-radius:10px;
   padding:12px 16px;margin-bottom:8px}}
 .faq summary{{font-weight:600;color:var(--ink);cursor:pointer}}
 .faq p{{color:var(--muted);font-size:14px;margin:8px 0 0}}
 .giftsec,.b2b{{max-width:1000px;margin:30px auto;padding:0 20px;text-align:center}}
 .giftsec h2,.b2b h2{{font-size:28px;color:var(--green);margin:0 0 6px}}
 .b2b{{margin-top:26px;padding-top:22px;border-top:1px solid var(--line)}}
 .b2bh{{font-size:20px;color:var(--green);margin:0 0 6px}}
 .gsub{{color:var(--muted);font-size:15px;margin:0 auto 16px;max-width:620px}}
 .gcards{{display:flex;flex-wrap:wrap;gap:16px;justify-content:center}}
 .gcard{{background:#fff;border:1px solid var(--line);border-radius:14px;
   padding:22px 28px;min-width:170px;text-decoration:none;color:var(--green);
   transition:.18s}}
 .gcard:hover{{transform:translateY(-4px);box-shadow:0 12px 28px rgba(16,61,46,.14)}}
 .gcard .ge{{font-size:34px}} .gcard .gl{{font-weight:600;margin-top:6px}}
 .ftc{{font-size:11px;color:#9aa39d;margin-top:12px}}
 .b2b{{background:#f3efe6;border:1px solid var(--line);border-radius:16px;
   padding:26px 20px}}
 .b2bform{{display:grid;grid-template-columns:1fr 1fr;gap:10px;max-width:620px;
   margin:0 auto}}
 .b2bform input,.b2bform textarea{{padding:11px 13px;border:1px solid #cdbf98;
   border-radius:9px;font-size:14px;font-family:inherit}}
 .b2bform textarea,.b2bform button{{grid-column:1/3}}
 .b2bform button{{background:var(--green);color:#fff;border:none;padding:13px;
   border-radius:26px;font-size:15px;font-weight:600;cursor:pointer}}
 .b2bform button:hover{{background:var(--green-d)}}
 @media(max-width:520px){{.b2bform{{grid-template-columns:1fr}}
   .b2bform textarea,.b2bform button{{grid-column:1}}}}
 .foot{{background:var(--green-d);color:#cfe0d6;text-align:center;
   padding:34px 20px;font-size:13px;line-height:1.7;margin-top:30px}}
 .foot .fbn{{font-family:'Cormorant Garamond',serif;font-size:24px;color:var(--gold);
   letter-spacing:1px}}
 /* modal */
 #modal{{position:fixed;inset:0;background:rgba(11,28,22,.62);display:none;
   align-items:flex-start;justify-content:center;z-index:50;overflow:auto;padding:20px}}
 .mbox{{background:#fff;border-radius:16px;max-width:880px;width:100%;margin:24px;
   overflow:hidden;box-shadow:0 30px 70px rgba(0,0,0,.4)}}
 .mbody{{display:flex;flex-wrap:wrap;gap:22px;padding:22px}}
 .mleft{{flex:1.1;min-width:300px}} .mright{{flex:1;min-width:280px}}
 #mmain{{width:100%;border-radius:10px;border:1px solid var(--line)}}
 .mthumbs{{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap}}
 .mthumbs img{{width:62px;height:62px;object-fit:cover;border:1px solid #d8cdb6;
   border-radius:7px;cursor:pointer;transition:.12s}}
 .mthumbs img:hover{{border-color:var(--gold)}}
 .fpick{{margin-top:12px;background:#f3efe6;border:1px solid var(--line);
   border-radius:12px;padding:12px}}
 .fpick .lbl{{font-size:13px;color:var(--green);margin-bottom:8px;font-weight:700}}
 .fchips{{display:flex;flex-wrap:wrap;gap:7px}}
 .fchip{{border:1px solid #cdbf98;background:#fff;border-radius:18px;padding:7px 13px;
   font-size:12.5px;cursor:pointer;transition:.12s;white-space:nowrap}}
 .fchip:hover{{border-color:var(--gold);background:#fffaf0}}
 .fchip.sel{{background:var(--green);color:#fff;border-color:var(--green);
   box-shadow:0 2px 8px rgba(16,61,46,.25)}}
 /* Colour-cue dot on each frame/material pill (visual without the heavy tiles). */
 #mfchips .fdot{{display:inline-block;width:13px;height:13px;border-radius:3px;
   margin-right:6px;vertical-align:-2px;border:1px solid rgba(0,0,0,.18)}}
 .perso{{margin-top:14px;background:#f3efe6;border:1px solid var(--line);
   border-radius:12px;padding:12px}}
 .perso .lbl{{font-size:13px;color:var(--green);font-weight:700;margin-bottom:8px}}
 .sw{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}
 .sw span{{width:26px;height:26px;border-radius:50%;cursor:pointer;
   border:2px solid #fff;box-shadow:0 0 0 1px #cdbf98;transition:.12s}}
 .sw span.sel{{box-shadow:0 0 0 2px var(--green);transform:scale(1.12)}}
 .perso input,.perso textarea{{width:100%;border:1px solid #cdbf98;border-radius:8px;
   padding:8px 10px;font-size:13px;font-weight:600;font-family:inherit;
   margin-bottom:6px}}
 .perso .note{{font-size:11px;color:var(--muted)}}
 .perso .cc{{font-size:11px;color:var(--muted);text-align:right;margin:-2px 0 4px}}
 .fonts{{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:6px}}
 .fonts .fchip{{font-size:14px}}
 .perso .swrow{{font-size:11.5px;color:var(--ink);margin:6px 0 4px;font-weight:700}}
 .tsizerow{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
 .tsizerow input[type=range]{{flex:1;accent-color:var(--green)}}
 .rotrow{{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 6px}}
 .rotrow button{{flex:1;background:#fff;border:1px solid var(--line);border-radius:12px;
   padding:5px 8px;font-size:12px;cursor:pointer;color:var(--green);white-space:nowrap}}
 .rotrow button:hover{{border-color:var(--gold)}}
 .tposreset{{background:#fff;border:1px solid var(--line);border-radius:14px;
   padding:4px 12px;font-size:12px;cursor:pointer;color:var(--green)}}
 .tposhint{{margin-left:8px;color:#8a6210;font-weight:700}}
 .perso .note.tip{{color:#1f3d2e;font-weight:600;background:#eef6f0;
   border:1px solid #cfe3d6;border-radius:8px;padding:8px 10px}}
 .perso .note.tip b{{color:#0a6b3b}}
 .orderactions{{display:flex;gap:8px;margin:8px 0}}
 .addbasketbtn{{flex:1.4;background:var(--green);color:#fff;border:none;border-radius:18px;
   padding:11px;font-size:14.5px;font-weight:700;cursor:pointer}}
 .addbasketbtn:hover{{background:var(--green-d)}}
 .savebtn2{{width:100%;background:#fff;border:1px dashed var(--line);color:var(--green);
   border-radius:14px;padding:8px;font-size:13px;cursor:pointer;margin:6px 0}}
 .mbasketbar{{background:var(--gold);color:#22301e;border-radius:12px;padding:9px 12px;
   font-size:13.5px;margin:8px 0;cursor:pointer;text-align:center;transition:transform .15s}}
 .mbasketbar:empty{{display:none}}
 .mbasketbar.added{{transform:scale(1.04)}}
 .mbasketbar .mbview{{text-decoration:underline;font-weight:600}}
 #basketBtn.pulse{{animation:basketpulse .5s ease 2}}
 @keyframes basketpulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.15)}}}}
 .savebtn{{flex:1;background:#fff;border:1px solid var(--green);color:var(--green);
   border-radius:18px;padding:9px;font-size:13.5px;font-weight:600;cursor:pointer}}
 .reviewbtn{{flex:1;background:var(--gold);color:#22301e;border:none;border-radius:18px;
   padding:9px;font-size:13.5px;font-weight:700;cursor:pointer}}
 #proofPop{{position:fixed;inset:0;z-index:82;background:rgba(11,28,22,.6);
   display:none;align-items:center;justify-content:center;padding:20px}}
 .proofbox{{background:#fff;border-radius:16px;max-width:460px;width:100%;padding:22px;
   text-align:center;max-height:90vh;overflow:auto;box-shadow:0 30px 70px rgba(0,0,0,.45)}}
 .calslots{{display:grid;grid-template-columns:repeat(6,1fr);gap:5px;margin:6px 0}}
 .calslot{{position:relative;border:1px dashed var(--line);border-radius:8px;padding:8px 2px;text-align:center;font-size:10px;color:#7a7466;cursor:pointer;background:#fff}}
 .calslot.filled{{border-style:solid;border-color:var(--green);background:#eef6f0;color:var(--green);font-weight:700}}
 .calslot input{{position:absolute;inset:0;opacity:0;cursor:pointer}}
 .calyear{{font-size:12px;color:#3a4a42;margin:2px 0 6px}}
 .calcountbar{{font-size:11px;color:#7a7466;background:#faf7f0;border:1px solid var(--line);border-radius:8px;padding:6px 9px;margin:6px 0}}
 .calcountbar b{{color:#3a4a42}}
 .calcountbar.done{{background:#eef6f0;border-color:var(--green);color:var(--green)}}
 .calcountbar.done b{{color:var(--green)}}
 .flipbox{{background:#fff;border-radius:16px;max-width:480px;width:100%;padding:20px;text-align:center;max-height:92vh;overflow:auto;box-shadow:0 30px 70px rgba(0,0,0,.45)}}
 .flipbox h2{{color:var(--green);margin:0 0 10px;font-size:20px}}
 .flipbox canvas{{width:100%;max-width:360px;border:1px solid var(--line);border-radius:8px;background:#fbfaf7}}
 .fliprow{{display:flex;gap:8px;margin-top:12px}}
 #flipPop{{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:60;align-items:center;justify-content:center;display:none}}
 .proofbox h2{{color:var(--green);margin:0 0 4px;font-size:22px}}
 .proofimg{{width:100%;max-width:300px;border-radius:8px;border:1px solid var(--line);
   margin:10px auto;display:block}}
 .proofimg.spinnable{{cursor:grab;touch-action:pan-y}}
 .proofimg.spinnable:active{{cursor:grabbing}}
 .proofflip{{display:none;align-items:center;justify-content:center;gap:10px;
   flex-wrap:wrap;margin:-2px 0 10px}}
 .proofflipbtn{{display:inline-flex;align-items:center;gap:7px;background:var(--green);
   color:#fff;border:none;border-radius:20px;padding:8px 16px;font-size:13px;
   font-weight:700;cursor:pointer}}
 .proofflipbtn:hover{{background:#0c3327}}
 .prooffliphint{{font-size:12px;color:#6b7b72}}
 .proofcross{{display:none;margin:8px 0 4px;padding:10px 12px;border:1px dashed var(--gold);
   border-radius:12px;background:#fffaf0;text-align:left}}
 .xshead{{font-weight:700;color:var(--green);font-size:14px}}
 .xssub{{font-size:12px;color:#6b7b72;margin:2px 0 8px}}
 .xsrow{{display:flex;gap:8px;flex-wrap:wrap}}
 .xsbtn{{flex:1;min-width:84px;background:#fff;border:1px solid var(--line);border-radius:20px;
   padding:9px 8px;font-size:12px;font-weight:600;color:var(--green);cursor:pointer;text-align:center}}
 .xsbtn:hover{{background:var(--green);color:#fff;border-color:var(--green)}}
 .proofsum{{background:#f6f2e7;border-radius:10px;padding:10px;font-size:13px;
   color:#3a4a42;white-space:pre-line;text-align:left;margin-bottom:8px}}
 .proofstatus{{color:var(--green);font-weight:600;font-size:14px;margin-bottom:8px}}
 .proofactions{{display:flex;gap:8px;flex-wrap:wrap}}
 .pedit,.padd{{flex:1;background:#fff;border:1px solid var(--line);border-radius:20px;
   padding:10px;font-size:13px;cursor:pointer;color:var(--green);white-space:nowrap}}
 .paccept{{flex:1;background:var(--green);color:#fff;border:none;border-radius:20px;
   padding:10px;font-size:14px;font-weight:700;cursor:pointer}}
 .dragmode{{margin-left:6px}}
 .dmbtn{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:2px 10px;
   font-size:12px;cursor:pointer;color:var(--green)}}
 .dmbtn.sel{{background:var(--green);color:#fff;border-color:var(--green)}}
 .mlogorow{{display:flex;align-items:center;gap:8px;margin:8px 0 2px;font-size:13px;
   font-weight:700;color:var(--green);cursor:pointer}}
 .mlogorow input{{width:17px;height:17px;accent-color:var(--green);cursor:pointer}}
 /* Photo-fit tool card: same gold-cream system as the wordbox/dragbar. */
 #mphotoctl{{background:#fffdf4;border:1.5px solid var(--gold);
   border-radius:12px;padding:12px 14px;margin:0 0 10px}}
 .pctitle{{font-size:14px;font-weight:800;color:var(--green);margin:0 0 8px}}
 .photorow{{display:flex;align-items:center;gap:7px;margin:8px 0;flex-wrap:wrap}}
 .photorow .plbl{{font-size:12px;font-weight:700;color:var(--ink);width:40px}}
 .photorow input[type=range]{{flex:1;accent-color:var(--green);height:6px}}
 .zico{{font-size:16px;font-weight:800;color:var(--green)}}
 .photorow button{{min-width:40px;height:38px;background:#fff;cursor:pointer;
   border:1.5px solid var(--green);border-radius:999px;padding:0 12px;
   font-size:15px;font-weight:800;color:var(--green);
   transition:transform .12s, box-shadow .12s}}
 .photorow button:hover{{transform:translateY(-1px);
   box-shadow:0 3px 10px rgba(16,61,46,.15)}}
 .photorow .pcenter{{background:var(--green);color:#fff;border-color:var(--green);
   font-size:13.5px}}
 .photorow .tposreset{{border-color:var(--line);color:#5a6b62}}
 #mphotoctl .pdone{{display:block;width:100%;margin-top:8px;padding:11px;
   border-radius:999px;font-size:14px}}
 #mcanvas{{width:100%;border-radius:8px;border:1px solid var(--line);display:block;
   margin-bottom:4px;background:#103d2e}}
 .mcanvaswrap{{position:relative;display:block;line-height:0;margin-bottom:4px}}
 .mcanvaswrap #mgarment{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;
   pointer-events:none;z-index:0;border-radius:8px}}
 .mcanvaswrap #mcanvas{{margin-bottom:0;background:transparent;position:relative;z-index:1}}
 .mcrop{{text-align:center;font-size:12px;color:#6b7a72;margin:0 0 6px}}
 .dragbar{{margin:0 0 10px;background:#fff7e0;border:1.5px solid var(--gold);
   border-radius:12px;padding:12px 14px}}
 .dragbar .dbq{{font-size:14px;font-weight:700;color:var(--green);
   text-align:center;margin-bottom:8px}}
 .dragbar .dseg{{display:flex;width:100%;border:2px solid var(--green);
   border-radius:999px;overflow:hidden;background:#fff}}
 .dragbar .dmbtn{{flex:1;border:0;border-radius:0;margin:0;padding:10px 8px;
   background:transparent;font-size:14px;font-weight:700;cursor:pointer;
   color:var(--green)}}
 .dragbar .dmbtn.sel{{background:var(--green);color:#fff}}
 .dragbar .plbtn{{flex:1;border:0;border-radius:0;margin:0;padding:10px 4px;
   background:transparent;font-size:13px;font-weight:700;cursor:pointer;color:var(--green)}}
 .dragbar .plbtn.sel{{background:var(--green);color:#fff}}
 .layoutgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(62px,1fr));gap:6px;margin:6px 0}}
 .layoutthumb{{border:1px solid var(--line);border-radius:8px;padding:3px;background:#fff;cursor:pointer}}
 .layoutthumb.sel{{outline:2px solid var(--green);outline-offset:1px;border-color:var(--green)}}
 .layoutthumb svg{{width:100%;height:auto;display:block}}
 .layoutthumb span{{display:block;font-size:9px;line-height:1.15;text-align:center;color:#3a4742;margin-top:2px;font-weight:600}}
 .layoutthumb small{{display:block;font-size:8px;line-height:1.15;text-align:center;color:#8a948c;margin-top:1px}}
 .slotinputs label{{display:block;font-size:12px;font-weight:600;margin:7px 0 2px;color:#3a4a42}}
 .slotinputs input{{width:100%;padding:8px;border:1px solid var(--line);border-radius:8px;font-size:13px}}
 .dbhint{{font-size:12.5px;color:var(--muted);font-weight:500;
   text-align:center;margin-top:7px}}
 .orderbox{{margin-top:14px;background:#fff;border:1px solid var(--line);
   border-radius:12px;padding:12px;
   transition:box-shadow .25s,border-color .25s,background .25s}}
 /* The order header is a full-width step banner, not a quiet text line. */
 .orderbox .lbl{{font-size:14.5px;color:#fff;font-weight:800;letter-spacing:.01em;
   margin:-12px -12px 12px;padding:12px 14px;border-radius:11px 11px 0 0;
   background:linear-gradient(135deg,#103d2e,#1d6048);display:flex;
   align-items:center;justify-content:space-between;gap:10px;
   transition:background .25s}}
 /* When frame selection is done, the whole order card becomes the active next
    step: a gold ring (via box-shadow, so no layout shift), lift, tint, a GOLD
    banner + a pulsing 'Next step' badge - impossible to miss. */
 .orderbox.stepnow{{border-color:var(--gold);
   box-shadow:0 0 0 2px var(--gold),0 12px 32px rgba(201,168,76,.34);
   background:linear-gradient(180deg,#fffdf6,#fff)}}
 .orderbox.stepnow .lbl{{color:#3a2c05;
   background:linear-gradient(135deg,var(--gold-d),var(--gold))}}
 .orderbox .stepbadge{{display:none}}
 .orderbox.stepnow .stepbadge{{display:inline-flex;align-items:center;
   font-size:11.5px;font-weight:800;letter-spacing:.02em;color:#7a5c12;
   background:#fff;border-radius:999px;padding:3px 11px;white-space:nowrap;
   box-shadow:0 1px 4px rgba(0,0,0,.18);
   animation:badgepulse 1.2s ease-in-out infinite}}
 @keyframes badgepulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.08)}}}}
 .orow{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-bottom:8px}}
 .orow label{{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:3px}}
 .orow select{{padding:8px;border:1px solid #cdbf98;border-radius:8px;font-size:13px}}
 .rmphoto{{color:#a23a3a;cursor:pointer;text-decoration:underline;margin-left:6px;
   font-size:12px;font-weight:600}}
 .mreview{{margin:8px 0;padding:9px 12px;background:#f6f2e7;border:1px solid var(--line);
   border-radius:10px;font-size:13px;color:#3a4a42}}
 .mreview .rvh{{font-size:12px;color:#b8860b;font-weight:800;text-transform:uppercase;
   letter-spacing:.5px;margin-bottom:3px}}
 .mreview .rvtag{{background:#e7ddc2;color:#6b5a2a;font-size:10.5px;padding:1px 6px;
   border-radius:8px;margin-left:4px}}
 .addbtn{{background:var(--green);color:#fff;border:none;border-radius:18px;
   padding:9px 16px;font-size:13px;font-weight:600;cursor:pointer}}
 .addbtn:hover{{background:var(--green-d)}}
 .cart{{font-size:13px}} .cart .line{{display:flex;justify-content:space-between;
   padding:4px 0;border-bottom:1px dashed #e7e1d6}}
 .cart .rm{{color:#b3261e;cursor:pointer;margin-left:8px}}
 .cart .tot{{font-weight:700;color:var(--green);padding-top:6px}}
 .uploadbox{{margin-top:10px;border-top:1px solid var(--line);padding-top:10px}}
 .upok{{color:#0f7a3d}} .upbad{{color:#b3261e}}
 /* Nice, bigger file uploads (service form + editor) -------------------- */
 .srfile input[type=file], .uploadbox input[type=file]{{
   width:100%;box-sizing:border-box;padding:16px;font-size:14px;cursor:pointer;
   color:#5b6b60;background:#f6fbf7;border:2px dashed var(--green);
   border-radius:12px;transition:background .15s,border-color .15s}}
 .srfile input[type=file]:hover, .uploadbox input[type=file]:hover{{
   background:#eef7f0;border-color:var(--green-d)}}
 .srfile input[type=file]::file-selector-button,
 .uploadbox input[type=file]::file-selector-button{{
   margin-right:14px;padding:11px 20px;border:0;border-radius:9px;
   background:var(--green);color:#fff;font-weight:700;font-size:14px;
   cursor:pointer;transition:background .15s}}
 .srfile input[type=file]::file-selector-button:hover,
 .uploadbox input[type=file]::file-selector-button:hover{{background:var(--green-d)}}
 .srfile input[type=file]::-webkit-file-upload-button,
 .uploadbox input[type=file]::-webkit-file-upload-button{{
   margin-right:14px;padding:11px 20px;border:0;border-radius:9px;
   background:var(--green);color:#fff;font-weight:700;font-size:14px;cursor:pointer}}
 /* Service-request form layout ------------------------------------------ */
 .srform{{display:grid;gap:13px;max-width:540px}}
 .srform label{{display:flex;flex-direction:column;gap:6px;font-size:13.5px;
   font-weight:600;color:#3a443d}}
 .srform input,.srform select,.srform textarea{{font:inherit;font-size:14px;
   font-weight:400;padding:12px 13px;border:1px solid var(--line);
   border-radius:10px;background:#fff;width:100%;box-sizing:border-box}}
 .srform textarea{{resize:vertical;min-height:96px}}
 .srform input:focus,.srform select:focus,.srform textarea:focus{{outline:none;
   border-color:var(--green);box-shadow:0 0 0 3px rgba(43,122,75,.14)}}
 .srform .srfile span{{font-weight:400;color:#8a958c;font-size:12px}}
 .srform .srconsent{{flex-direction:row;align-items:center;gap:9px;
   font-weight:500;font-size:13.5px}}
 .srform .srconsent input{{width:auto;margin:0;transform:scale(1.25)}}
 .srform>button{{padding:14px 24px;border:0;border-radius:11px;background:var(--green);
   color:#fff;font-weight:700;font-size:15.5px;cursor:pointer;transition:background .15s}}
 .srform>button:hover{{background:var(--green-d)}}
 .srstatus{{color:#b3261e;font-size:13px;min-height:1px}}
 .srdone{{padding:18px;border:1px solid var(--green);border-radius:12px;
   background:#f6fbf7;color:#2b5d3f;font-size:15px;line-height:1.55}}
 #mstepper{{display:flex;gap:6px;list-style:none;margin:0 0 4px;padding:10px 16px 0;
   font-size:12.5px;color:#7c867f;flex-wrap:wrap}}
 #mstepper li{{display:flex;align-items:center}}
 #mstepper li::after{{content:"\\203A";color:#c9d6cd;margin:0 7px}}
 #mstepper li:last-child::after{{content:""}}
 #mstepper li.cur{{color:var(--green);font-weight:700}}
 #mstepper li.done{{color:#0f7a3d}}
 .spin{{display:inline-block;width:12px;height:12px;border:2px solid #c9d6cd;
   border-top-color:var(--green);border-radius:50%;vertical-align:-2px;
   animation:spinrot .8s linear infinite}}
 @keyframes spinrot{{to{{transform:rotate(360deg)}}}}
 .nextsteps{{text-align:left;background:#f6f9f7;border:1px solid #dfe9e2;
   border-radius:10px;padding:10px 14px;margin-top:10px;font-size:13px;
   line-height:1.55}}
 .nextsteps ol{{margin:6px 0 4px 18px;padding:0}}
 .nextsteps li{{margin:4px 0}}
 .pfemail{{margin-top:8px}}
 .pfemail label{{display:block;font-weight:600;margin-bottom:4px}}
 .pfemail input{{padding:7px 9px;border:1px solid #cdd9d0;border-radius:8px;
   font-size:13px;min-width:200px}}
 .pfemail button{{padding:7px 14px;border-radius:8px;border:0;cursor:pointer;
   background:var(--green);color:#fff;font-weight:600}}
 .fcform{{text-align:left;margin-top:8px}}
 .fcform label{{display:block;font-size:13px;font-weight:700;color:#3c4a42;
   margin:8px 0 0}}
 .fcform .fcopt{{font-weight:400;color:#9aa49c}}
 .fcform input{{display:block;width:100%;box-sizing:border-box;margin-top:3px;
   padding:8px 10px;border:1px solid #cdd9d0;border-radius:8px;font-size:14px}}
 .fcrow{{display:flex;gap:8px}} .fcrow label{{flex:1}}
 .fcback{{color:var(--green);cursor:pointer;margin-top:10px;font-size:13px;
   text-decoration:underline;text-align:left}}
 .fcship{{text-align:left;background:#f6f9f7;border:1px solid #dfe9e2;
   border-radius:10px;padding:10px 14px;margin-top:10px;font-size:13px;
   line-height:1.55}}
 @media(max-width:560px){{ .fcrow{{flex-direction:column;gap:0}} }}
 /* Checkout trust strip (steps 2 & 3): security + free-proof + payment methods. */
 .trustband{{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;
   background:#f3f8f4;border:1px solid #cfe3d6;border-radius:10px;
   padding:9px 12px;margin-bottom:12px;font-size:12px;color:#1f4d38;text-align:left}}
 .trustband .paylogos{{margin-left:auto;color:#5b6b62;font-weight:700;white-space:nowrap}}
 @media(max-width:560px){{ .trustband .paylogos{{margin-left:0}} }}
 /* Benefit chips: the section's reassurances as large scannable pills. */
 .freebar{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
 .fchk{{background:#eaf4ed;border:1px solid #9fc4ab;color:#0f7a3d;
   border-radius:999px;padding:8px 13px;font-size:13.5px;font-weight:700}}
 .wordbox{{background:#fffdf4;border:2px solid var(--gold);border-radius:12px;
   padding:10px 12px;margin:12px 0;box-shadow:0 0 0 4px rgba(199,164,77,.12)}}
 /* While the wording beacon is active, the INPUT itself glow-pulses - the
    eye lands exactly where the customer should type. */
 @keyframes inputglow{{0%,100%{{border-color:#cdbf98;
   box-shadow:0 0 0 0 rgba(199,164,77,0)}}
   50%{{border-color:var(--gold);box-shadow:0 0 0 6px rgba(199,164,77,.35)}}}}
 .wordbox.pulseon textarea{{animation:inputglow 1.2s ease-in-out infinite}}
 .wordbox .wordlbl{{font-size:14.5px;font-weight:700;color:var(--green);
   margin-bottom:6px}}
 .wordbox textarea{{font-size:15px;min-height:88px;background:#fff}}
 .wordbox .cc{{margin-top:4px}}
 #esectabs{{display:flex;gap:10px;margin:14px 0 12px}}
 #esectabs button{{flex:1;display:flex;flex-direction:column;align-items:center;
   gap:4px;padding:13px 8px 11px;border-radius:14px;cursor:pointer;
   border:2px solid #cdbf98;background:#fffdf4;color:var(--green);
   transition:transform .15s, box-shadow .15s}}
 #esectabs .eicon{{font-size:24px;line-height:1}}
 #esectabs .elbl{{font-size:14px;font-weight:800;letter-spacing:.2px}}
 #esectabs button.sel{{background:var(--green);color:#fff;
   border-color:var(--green);transform:translateY(-2px);
   box-shadow:0 6px 16px rgba(16,61,46,.28)}}
 #esectabs button:not(.sel):hover{{transform:translateY(-1px);
   box-shadow:0 3px 10px rgba(16,61,46,.12)}}
 #esectabs button.done{{background:#eaf4ed;border-color:#0f7a3d;color:#0f7a3d}}
 #esectabs button.done .elbl::before{{content:"✓ "}}
 .sizeprompt{{background:#fffdf4;border:2px solid var(--gold);border-radius:10px;
   padding:8px 12px;margin-bottom:8px;font-size:13.5px;color:var(--green)}}
 @keyframes ctapulse{{0%{{box-shadow:0 0 0 0 rgba(16,61,46,.45)}}
   70%{{box-shadow:0 0 0 14px rgba(16,61,46,0)}}
   100%{{box-shadow:0 0 0 0 rgba(16,61,46,0)}}}}
 .pulseanim{{animation:ctapulse 1.1s ease-out 3;border-radius:12px}}
 /* Task-bound pulse: blinks until the customer actually finishes the step. */
 .pulseon{{animation:ctapulse 1.2s ease-out infinite;border-radius:12px}}
 /* Size/Qty dropdowns glow-pulse to draw the eye until a size is chosen.
    High-contrast: solid ring + blurred glow halo + border + background breathe
    together (no border-width change, so no layout shift). */
 @keyframes selattn{{
   0%,100%{{box-shadow:0 0 0 0 rgba(201,168,76,0),0 0 0 0 rgba(179,144,47,0);
     border-color:#cdbf98;background:#fff}}
   50%{{box-shadow:0 0 0 4px rgba(201,168,76,.65),0 0 16px 3px rgba(179,144,47,.55);
     border-color:var(--green);background:#fbf6e9}}}}
 .orow select.attn{{animation:selattn 1.05s ease-in-out infinite;
   position:relative;z-index:1;font-weight:600}}
 /* The 'Pick your size & quantity' prompt blinks until the step is finished:
    the same .pulseon ctapulse ring PLUS an animated gold<->green border-glow. */
 @keyframes promptborder{{0%,100%{{border-color:var(--gold)}}
   50%{{border-color:var(--green)}}}}
 .sizeprompt.attn{{animation:ctapulse 1.2s ease-out infinite,
     promptborder 1.2s ease-in-out infinite;border-radius:10px}}
 @media (prefers-reduced-motion:reduce){{
   .orow select.attn{{animation:none;border-color:var(--green);background:#fbf6e9;
     box-shadow:0 0 0 4px rgba(201,168,76,.55),0 0 14px 2px rgba(179,144,47,.45)}}
   .sizeprompt.attn{{animation:none;border-color:var(--green);
     box-shadow:0 0 0 4px rgba(201,168,76,.30)}}}}
 /* The active section tab breathes softly - a quiet 'you are here' while
    the strong pulse marks the one action that completes the task. */
 @keyframes tabglowk{{0%,100%{{box-shadow:0 6px 16px rgba(16,61,46,.28)}}
   50%{{box-shadow:0 2px 22px 6px rgba(16,61,46,.12)}}}}
 #esectabs button.tabglow{{animation:tabglowk 1.8s ease-in-out infinite}}
 .esecnav{{display:flex;gap:8px;justify-content:space-between;margin-top:12px}}
 .esecnav .esecnext{{flex:1;padding:11px 14px;border-radius:999px;border:0;
   cursor:pointer;background:var(--green);color:#fff;font-weight:700;
   font-size:14.5px}}
 .esecnav .esecnext:hover{{background:var(--green-d)}}
 .esecnav .esecback{{padding:11px 16px;border-radius:999px;cursor:pointer;
   border:1px solid var(--line);background:#fff;color:#5a6b62}}
 .ordmail{{display:block;text-align:center;text-decoration:none;margin-top:10px;
   padding:12px 14px;border-radius:999px;background:var(--green);color:#fff;
   font-weight:700}}
 .bpactions button[disabled]{{opacity:.45;cursor:not-allowed}}
 .bpmore{{display:block;width:100%;margin:0 0 8px;padding:11px;cursor:pointer;
   border:1.5px solid var(--green);border-radius:999px;background:#fff;
   color:var(--green);font-weight:700;font-size:14px}}
 .bpmore:hover{{background:var(--green);color:#fff}}
 .mbox h2{{font-size:24px;margin:2px 0 6px;color:var(--green);line-height:1.25}}
 .mprice{{font-weight:700;color:var(--green);font-size:24px;margin:6px 0}}
 .mdescbox{{margin-top:12px;background:#fff;border:1px solid var(--line);
   border-radius:12px;padding:12px 14px;text-align:left}}
 .mdescbox .lbl{{font-size:13px;color:var(--green);font-weight:700;
   margin-bottom:4px}}
 .dsh{{font-weight:800;color:var(--green);margin:10px 0 4px;font-size:13px;
   letter-spacing:.4px}}
 .dsb{{position:relative;padding-left:14px;margin:3px 0;font-size:13px}}
 .dsb::before{{content:"•";position:absolute;left:2px;color:var(--gold)}}
 .dsl{{margin:3px 0;font-size:13px}}
 .mdesc{{font-size:13px;line-height:1.65;color:#4a564f}}
 .closex{{float:right;font-size:26px;cursor:pointer;color:#9aa39d;padding:10px 16px;
   line-height:1}}
 .fbbtn{{display:block;background:var(--gold);color:#22301e;text-align:center;
   text-decoration:none;padding:13px;border-radius:30px;font-weight:600;
   margin:14px 0;transition:.15s}}
 .fbbtn:hover{{background:var(--gold-d)}}
 /* star rating */
 .rate{{margin:12px 0 4px}} .rate .lbl{{font-size:13px;color:var(--muted);margin-bottom:4px}}
 .stars2{{font-size:32px;line-height:1;cursor:pointer;user-select:none}}
 .stars2 span{{color:#ddd3bc;transition:color .1s}}
 .stars2 span.on{{color:var(--gold)}}
 .ratemsg{{font-size:12px;color:var(--green);min-height:16px;margin-top:2px}}
 @media(max-width:760px){{
   .mleft,.mright{{min-width:0;flex-basis:100%}}
   .mbox{{max-height:94vh}}
 }}
 @media(max-width:560px){{
   .mbody{{padding:16px}} .nav .bn{{font-size:20px}}
   .nav{{flex-wrap:nowrap;gap:7px;padding:10px 8px}} .navquiz,.navbasket{{margin-left:0}}
   .navham{{display:inline-flex;align-items:center;margin-left:auto}}
   .navquiz{{margin-left:6px}}
   .navlinks{{position:absolute;top:100%;left:0;right:0;flex-direction:column;gap:0;
     background:rgba(247,244,238,.99);border-bottom:1px solid var(--line);
     box-shadow:0 12px 26px rgba(16,61,46,.14);padding:6px 16px;display:none;z-index:60;margin:0}}
   .navlinks.open{{display:flex}}
   .navlinks a{{width:100%;padding:13px 2px;min-height:46px;border-bottom:1px solid var(--line)}}
   .navlinks a:last-child{{border-bottom:none}}
   .navquiz,.navbasket{{padding:7px 11px;font-size:13px}}
   .ocgrid{{grid-template-columns:repeat(2,1fr);gap:11px}}
   .ocimg{{height:104px}} .octitle{{font-size:17px}}
   .photorow{{flex-wrap:wrap}} .b2bform{{grid-template-columns:1fr}}
   .b2bform textarea,.b2bform button{{grid-column:1}}
   .occrow{{gap:6px}} .occhip{{padding:6px 11px;font-size:12.5px;min-height:40px}}
   .proofactions,.bpactions{{flex-wrap:wrap}}
   /* Comfortable touch targets on phones (>=~44px) for the dense controls. */
   #mfchips .fchip{{min-height:44px}}
   .fonts .fchip{{min-height:40px;display:inline-flex;align-items:center}}
   .sw span{{width:38px;height:38px}}
   #mphotoctl button{{min-width:44px;min-height:44px;font-size:18px}}
 }}
</style></head><body>
{gate}
<div id="site" style="{site_style}">
 <div class="nav">
   {f'<img src="{logo_src}" alt="{SHOP_NAME}">' if logo_src else ''}
   <span class="bn">{SHOP_NAME}</span>
   <button class="navham" aria-label="Open menu" aria-expanded="false" aria-controls="navMenu" onclick="toggleNav()">&#9776;</button>
   <nav class="navlinks" id="navMenu" aria-label="Sections" onclick="closeNav()">
     <a href="#wallart" onclick="selectDept('wall');return false;">🖼️ Wall Art</a>
     <a href="#apparel" onclick="selectDept('apparel');return false;">👕 Apparel</a>
     <a href="#branded" onclick="selectDept('branded');return false;">🎁 Branded</a>
     <a href="#mugs" onclick="selectDept('mug');return false;">🍵 Mugs</a>
     <a href="#calendars" onclick="selectDept('cal');return false;">📅 Calendars</a>
     <a href="#" onclick="openQuiz();return false;">Occasions</a>
     <a href="#why">Why</a>
     <a href="#faq">FAQ</a>
     <a href="studio.html" target="_blank" rel="noopener" title="Try our new free-canvas designer">&#10024; Pro Designer <span style="font-size:9px;background:var(--gold);color:#3a2c08;padding:1px 5px;border-radius:8px;vertical-align:middle;font-weight:800">BETA</span></a>
   </nav>
   <button class="navquiz" onclick="openQuiz()">🎁 Gift Finder</button>
   <button class="navbasket" id="basketBtnNav" onclick="toggleBasket()">🛒 Basket <span id="basketCountNav">0</span></button>
 </div>
 <div class="hero">
   {f'<img class="hero-banner" src="{banner_src}" alt="Personalized wall art styled in a cozy living room" fetchpriority="high" decoding="async">' if banner_src else '<div class="hero-fallback"><h1>'+SHOP_NAME+'</h1></div>'}
   <div class="hero-overlay">
     <h1 data-ab="hero_h1">Personalized gifts for life's most meaningful moments</h1>
     <p>Wall art &amp; custom apparel - your names, dates &amp; own words, made to order.</p>
     <div class="herocta">
       <a class="btn-shop" href="#depts">Shop by department</a>
       <button class="btn-find" onclick="openQuiz()">🎁 Find the perfect gift</button>
     </div>
     <p class="heroprice">From <b>$18.99</b> &middot; a free proof you approve before you buy</p>
   </div>
 </div>
 <div class="trust">
   <span>✦ <b>Free proof</b> you approve on screen</span>
   <span>✦ <b>Made to order</b>, just for you</span>
   <span>✦ <b>Premium</b> museum-quality materials</span>
   <span>✦ <b>Worldwide</b> tracked shipping</span>
 </div>
 <section class="depts" id="depts" aria-label="Shop by department">
   <h2 class="deptshead">Shop by department</h2>
   <div class="deptgrid">
     <a class="deptcard deptwall" href="#wallart" onclick="selectDept('wall');return false;">
       {f'<img class="deptimg" loading="lazy" src="{dept_wall_src}" alt="Personalized wall art styled in a room">' if dept_wall_src else '<span class="depticon">🖼️</span>'}
       <div class="deptbody">
         <span class="depttitle">Wall Art</span>
         <span class="deptsub">Posters, framed prints, canvas, acrylic &amp; metal</span>
         <span class="deptgo">Browse Wall Art →</span>
       </div>
     </a>
     <a class="deptcard deptapp" href="#apparel" onclick="selectDept('apparel');return false;">
       {f'<img class="deptimg" loading="lazy" src="{dept_app_src}" alt="People wearing custom personalized apparel">' if dept_app_src else '<span class="depticon">👕</span>'}
       <div class="deptbody">
         <span class="depttitle">Apparel</span>
         <span class="deptsub">T-shirts, hoodies &amp; sweatshirts</span>
         <span class="deptgo">Browse Apparel →</span>
       </div>
     </a>
     <a class="deptcard deptbranded" href="#branded" onclick="selectDept('branded');return false;">
       {f'<img class="deptimg" loading="lazy" src="{dept_branded_src}" alt="Custom branded products - totes, bottles &amp; more">' if dept_branded_src else '<span class="depticon">🎁</span>'}
       <div class="deptbody">
         <span class="depttitle">Custom Branded Products</span>
         <span class="deptsub">Totes, bottles, tumblers, notebooks &amp; more</span>
         <span class="deptgo">Browse Branded →</span>
       </div>
     </a>
     <a class="deptcard deptmug" href="#mugs" onclick="selectDept('mug');return false;">
       {f'<img class="deptimg" loading="lazy" src="{dept_mug_src}" alt="Custom mugs - ceramic, enamel &amp; travel">' if dept_mug_src else '<span class="depticon">🍵</span>'}
       <div class="deptbody">
         <span class="depttitle">Custom Mugs</span>
         <span class="deptsub">Ceramic, enamel, travel &amp; colour-changing mugs</span>
         <span class="deptgo">Browse Mugs →</span>
       </div>
     </a>
     <a class="deptcard deptcal" href="#calendars" onclick="selectDept('cal');return false;">
       {f'<img class="deptimg" loading="lazy" src="{dept_cal_src}" alt="Custom calendars - wall, desk &amp; photo">' if dept_cal_src else '<span class="depticon">📅</span>'}
       <div class="deptbody">
         <span class="depttitle">Custom Calendars</span>
         <span class="deptsub">Wall, desk &amp; photo calendars, personalized month by month</span>
         <span class="deptgo">Browse Calendars →</span>
       </div>
     </a>
   </div>
 </section>
 <section id="giftsets" class="giftsets">
   <div class="gshead">🎁 Gift sets &amp; occasions</div>
   <div class="occrow" id="occrow"></div>
   <div class="setgrid" id="setgrid"></div>
 </section>
 <section class="hiw" aria-label="How it works">
   <p class="hiweyebrow">Simple &middot; transparent &middot; risk-free</p>
   <h2>How it works</h2>
   <p class="hiwsub">Made to order, with a <b>free proof</b> before anything prints &mdash; so you
     get exactly what you pictured, every time.</p>
   <div class="hiwsteps">
     <div class="hiwstep">
       <span class="hiwmed" aria-hidden="true">
         <svg viewBox="0 0 24 24"><path d="M4 20h4L18.5 9.5a2.12 2.12 0 0 0-3-3L5 17v3z"/><path d="M13.5 6.5l3 3"/></svg>
         <span class="hiwnum">1</span></span>
       <span class="hiwt">Personalize it</span>
       <span class="hiwd">Add the name, the occasion and your own words or photo -
         preview it live as you type.</span></div>
     <div class="hiwstep">
       <span class="hiwmed" aria-hidden="true">
         <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/></svg>
         <span class="hiwnum">2</span></span>
       <span class="hiwt">Approve a free proof</span>
       <span class="hiwd">Your free proof appears on screen instantly &mdash; approve it and
         that's exactly what we print. This is your final sign-off, so it's locked in
         once you submit.</span></div>
     <div class="hiwstep">
       <span class="hiwmed" aria-hidden="true">
         <svg viewBox="0 0 24 24"><path d="M3 7h10v8H3z"/><path d="M13 10h4l3 3v2h-7z"/><circle cx="7" cy="17" r="1.5"/><circle cx="16.5" cy="17" r="1.5"/></svg>
         <span class="hiwnum">3</span></span>
       <span class="hiwt">We print &amp; ship</span>
       <span class="hiwd">Made to order on premium materials and shipped worldwide
         with tracking.</span></div>
   </div>
   <div class="hiwtrust">
     <span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l7 3v5c0 4-3 7-7 8-4-1-7-4-7-8V6z"/><path d="M9 12l2 2 4-4"/></svg>Happiness guarantee</span>
     <span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/></svg>See it before it prints</span>
     <span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18"/></svg>Worldwide shipping</span>
   </div>
 </section>
 {sproof_html}
 {cutoff_html}
 {"<div class='uatbar'>👋 Thanks for helping review " + SHOP_NAME +
  "! <b>Tap any piece</b> to see all its photos &amp; details, rate it, then "
  "tap <b>feedback</b>. "
  "<a href='mailto:" + owner + "?subject=Joffiels%20overall%20feedback'>"
  "Send overall feedback</a></div>" if uat else ""}
 <div id="deptswitch" class="deptswitch" style="display:none">
   <button type="button" class="dswall" onclick="selectDept('wall')">🖼️ Wall Art</button>
   <button type="button" class="dsapp" onclick="selectDept('apparel')">👕 Apparel</button>
   <button type="button" class="dsbranded" onclick="selectDept('branded')">🎁 Branded</button>
   <button type="button" class="dsmug" onclick="selectDept('mug')">🍵 Mugs</button>
   <button type="button" class="dscal" onclick="selectDept('cal')">📅 Calendars</button>
   <button type="button" class="dsall" onclick="showAllDepartments()">&#8593; All departments</button>
 </div>
 <div id="deptWall" class="deptpane" style="display:none">
 {_wallart_hero()}
 {_occasion_showcase(kit_dir, external_assets, assets)}
 <div id="gridcount" class="gridcount"></div>
 <p class="quiznudge">Not sure which one? <a href="#" onclick="openQuiz();return false">&#127873; Take the 30-second Gift Finder</a></p>
 <!-- Quick-jump: every design as a tap-able thumbnail that opens its page
      directly (no scrolling through the grid). Filled by render(). -->
 <details class="qjwrap"><summary class="qjsum">&#10024; Find Your Perfect Design <small>See all 13 at a glance - tap to explore!</small></summary>
 <div id="quickjump" class="quickjump" role="navigation" aria-label="Jump to a design"></div></details>
 <div id="occnote" class="occnote"></div>
 <div class="grid" id="grid"></div>
 <div id="gridmorewrap" class="gridmorewrap" style="display:none">
   <button type="button" class="gridmore" onclick="expandGrid()">Show all occasions &#8595;</button>
 </div>
 <div id="occbottom" class="occbottom" style="display:none"></div>
 <div class="bundle" id="bundleSec">
   <div class="bundlehdr">
     <div>
       <h2>💡 Optional: buy a matching set &amp; save</h2>
       <p class="gsub">Decorating a wall or gifting a family? Pick 2-3 designs and
         bundle discounts apply automatically ({bundle_discount_text}).
         You'll personalize each piece next - skip this if you just want one.</p>
     </div>
     <button class="bundletoggle" id="bundleToggle" onclick="toggleBundleSec()">Build a set &rarr;</button>
   </div>
   <div id="bundleBody" style="display:none">
     <div class="bgrid" id="bgrid"></div>
     <div class="btot" id="btot">Select 2 or more to see your set price.</div>
   </div>
 </div>
 </div>
 <div id="deptApparel" class="deptpane" style="display:none">{_apparel_section(_garment_photos)}</div>
 <div id="deptBranded" class="deptpane" style="display:none">{_branded_section(_branded_photos, external_assets, assets)}</div>
 <div id="deptMug" class="deptpane" style="display:none">{_mug_section(_mug_photos, external_assets, assets)}</div>
 <div id="deptCal" class="deptpane" style="display:none">{_cal_section(_cal_photos, external_assets, assets)}</div>
 {reviews_html}
 {gallery_html}
 {_competitive_sections()}
 {_service_request_form()}
 {packages_html}
 {_gift_section(owner)}
 <div class="foot">
   <div class="fbn">{SHOP_NAME}</div>
   <p>Personalized wall art, made to order - free proof before printing.<br>
   Sample preview for review. Prices shown are starting prices; every item is
   personalized to order.</p>
 </div>
</div>

<div id="quiz" role="dialog" aria-modal="true" aria-label="Gift finder" onclick="if(event.target.id==='quiz')closeQuiz()">
  <div class="qbox">
    <span class="qclose" role="button" tabindex="0" aria-label="Close" onclick="closeQuiz()">&times;</span>
    <h2>🎁 Find the perfect gift</h2>
    <p class="qsub">Answer 5 quick questions and we'll recommend the ideal piece.</p>
    <div class="qrow"><label>Who is it for?</label><select id="q_rel"></select></div>
    <div class="qrow"><label>Occasion</label><select id="q_occ"></select></div>
    <div class="qrow"><label>Budget</label><select id="q_bud"></select></div>
    <div class="qrow"><label>Style</label><select id="q_sty"></select></div>
    <button class="qgo" onclick="runQuiz()">Find my gift &rarr;</button>
    <div id="qresult"></div>
  </div>
</div>

<div id="resumeBar">
  🎨 Your custom artwork is still waiting.
  <button onclick="resumeDraft()">Resume your design &rarr;</button>
  <span class="rbx" onclick="document.getElementById('resumeBar').style.display='none'">&times;</span>
</div>


<div id="proofPop" role="dialog" aria-modal="true" aria-label="Your design proof" onclick="if(event.target.id==='proofPop')closeProof()">
  <div class="proofbox">
    <span class="qclose" role="button" tabindex="0" aria-label="Close" onclick="closeProof()">&times;</span>
    <h2 id="proofTitle">Your final design</h2>
    <p class="qsub" id="proofSub">This is how your piece will look - exactly what prints.
      Add it to your basket; you'll approve it at checkout before anything is made.</p>
    <img id="proofImg" class="proofimg" alt="Your design preview"
         onmousedown="_proofDown(event)" onmousemove="_proofMove(event)"
         onmouseup="_proofUp()" onmouseleave="_proofUp()"
         ontouchstart="_proofDown(event)" ontouchmove="_proofMove(event)" ontouchend="_proofUp()">
    <div id="proofFlip" class="proofflip">
      <button type="button" class="proofflipbtn" onclick="proofFlip()" aria-label="Rotate the garment to see the other side">
        &#128260; <span id="proofFlipLbl">See the back</span></button>
      <span class="prooffliphint">or drag the shirt to spin front &harr; back</span>
    </div>
    <div class="proofsum"><span id="proofSummary"></span></div>
    <div id="proofCross" class="proofcross"></div>
    <div id="proofStatus" class="proofstatus" role="status" aria-live="polite"></div>
    <div class="proofactions">
      <button class="pedit" onclick="proofEdit()">&larr; Go back &amp; edit</button>
      <button id="proofAcceptBtn" class="paccept" onclick="proofAccept()">✓ Add to basket</button>
    </div>
  </div>
</div>

<div id="flipPop" role="dialog" aria-modal="true" aria-label="Calendar preview" onclick="if(event.target.id==='flipPop')closeFlipbook()">
  <div class="flipbox">
    <span class="qclose" role="button" tabindex="0" aria-label="Close" onclick="closeFlipbook()">&times;</span>
    <h2 id="flipLbl">Cover</h2>
    <canvas id="flipCanvas" width="420" height="560"></canvas>
    <div class="fliprow">
      <button type="button" class="pedit" onclick="flipPage(-1)">&larr; Prev</button>
      <button type="button" class="pedit" onclick="flipPage(1)">Next &rarr;</button>
    </div>
  </div>
</div>

<div id="exitpop" role="dialog" aria-modal="true" aria-label="A note before you go" onclick="if(event.target.id==='exitpop')closeExit()">
  <div class="xbox">
    <span class="qclose" role="button" tabindex="0" aria-label="Close" onclick="closeExit()">&times;</span>
    <h2>Wait - here's {promo_pct}% off your first piece</h2>
    <p class="qsub">Join the insider list for an instant discount code, early
      access to new designs &amp; seasonal gift guides.</p>
    <div id="xform">
      <input id="xemail" type="email" aria-label="Your email address" placeholder="you@email.com"
        onkeydown="if(event.key==='Enter')submitExit()">
      <button class="qgo" onclick="submitExit()">Send my code &rarr;</button>
    </div>
    <div id="xmsg"></div>
    <p class="ftc">No spam - unsubscribe anytime. One email, one code.</p>
  </div>
</div>

<div id="modal" role="dialog" aria-modal="true" aria-label="Personalize your design" onclick="if(event.target.id==='modal')closeM()">
 <div class="mbox">
   <span class="closex" role="button" tabindex="0" aria-label="Close" onclick="closeM()" onkeydown="if(event.key=='Enter')closeM()">&times;</span>
   <ol id="mstepper" aria-label="Order progress">
     <li data-s="1" class="cur" aria-current="step">1. Customize</li>
     <li data-s="2">2. Review</li>
     <li data-s="3">3. Approve</li>
     <li data-s="4">4. Checkout</li>
   </ol>
   <div id="bundlebanner" style="display:none"></div>
   <div class="mbody">
     <div class="mleft" id="mleftcol">
       <div class="mcanvaswrap"><img id="mgarment" alt="Garment preview" style="display:none"><canvas id="mcanvas" width="520" height="650"></canvas><div id="mug3dwrap" style="display:none;position:absolute;inset:0;z-index:4;background:#f3efe6;border-radius:10px"><span id="mock3dttl" style="position:absolute;top:7px;left:11px;font-size:12.5px;font-weight:700;color:#103d2e;line-height:1.2">&#128260; Drag to spin your product</span><span role="button" tabindex="0" aria-label="Back to editing" onclick="close3D()" onkeydown="if(event.key==='Enter')close3D()" style="position:absolute;top:3px;right:10px;cursor:pointer;font-size:21px;line-height:1;color:#5a5448">&times;</span><div id="mug3d" style="position:absolute;left:6px;right:6px;top:27px;bottom:20px;border-radius:8px;overflow:hidden"></div><span id="mock3dsub" style="position:absolute;left:11px;right:11px;bottom:4px;font-size:10px;color:#7a7466;line-height:1.3">Your approved flat proof is exactly what prints.</span></div></div>
       <div id="mcrop" class="mcrop"></div>
       <button type="button" class="seefinal" id="seefinalbtn" aria-label="See final preview" onclick="showFinalProof('item')">
         &#128065;&#65039; See final preview</button>
       <button type="button" class="seefinal" id="view3dbtn" style="display:none" aria-label="Spin your product" onclick="view3D()">&#128260; Spin your product &mdash; front &amp; back</button>
       <div class="dragbar" id="mplacement" style="display:none">
         <div class="dbq">&#128085; Design the <b>front</b> and the <b>back</b> &mdash; each holds its own wording &amp; photo. Tap a side, or <b>drag the shirt</b> to spin it.</div>
         <div class="dseg" role="group" aria-label="Choose side">
           <button type="button" class="plbtn sel" data-p="front" onclick="setPlacement('front')">Front</button>
           <button type="button" class="plbtn" data-p="back" onclick="setPlacement('back')">Back</button>
         </div>
         <div id="mbackhint" class="dbhint" style="display:none">&#128260; You&#39;re designing the <b>back</b> &mdash; add a different photo or wording; it&#39;s separate from the front.</div>
         <label class="mlogorow"><input type="checkbox" id="mlogo" onchange="toggleLogo()"> Add our logo (front &amp; back)</label>
       </div>
       <div class="dragbar" id="mlayoutbar" style="display:none">
         <div class="dbq">&#127912; Pick a <b>layout</b> &mdash; we arrange your logo &amp; words professionally. Type your words in <b>Step 1</b>, then tweak anything.</div>
         <div id="mlayouts" class="layoutgrid"></div>
       </div>
       <div class="dragbar" id="mframebar" style="display:none">
         <div class="dbq">&#128208; <b>Move &amp; resize your design</b> &mdash; drag the dashed box to move it, or
           <span class="grabtip"><span class="grabsq"></span> drag the green corner with your mouse to resize</span>.</div>
         <div class="photorow">
           <span class="plbl">Size</span>
           <span class="zico" aria-hidden="true">&minus;</span>
           <input type="range" id="mframesize" min="0.45" max="1.7" step="0.05" value="1"
             oninput="setFrameSize(this.value)" aria-label="Design frame size">
           <span class="zico" aria-hidden="true">+</span>
         </div>
         <div class="photorow">
           <span class="plbl">Move</span>
           <button type="button" aria-label="Move design left" onclick="moveFrame(-0.04,0)">&larr;</button>
           <button type="button" aria-label="Move design right" onclick="moveFrame(0.04,0)">&rarr;</button>
           <button type="button" aria-label="Move design up" onclick="moveFrame(0,-0.04)">&uarr;</button>
           <button type="button" aria-label="Move design down" onclick="moveFrame(0,0.04)">&darr;</button>
           <button type="button" class="tposreset" onclick="resetFrame()">Reset</button>
         </div>
         <div class="dbhint">Move the whole design (wording + photo) anywhere on the garment and size it up or down.</div>
       </div>
       <div class="dragbar" id="mcalbar" style="display:none">
         <div class="dbq">&#128197; Build your <b>12-month calendar</b> &mdash; add a photo for each month, then preview the whole calendar.<br><span style="font-size:11px;color:#7a7466">&#128247; Photos are centered &amp; cropped to a landscape frame &mdash; landscape shots look best.</span></div>
         <div class="calyear"><label>Year <input type="number" id="mcalyear" value="2026" min="2025" max="2030" onchange="setCalYear(this.value)" style="width:84px"></label></div>
         <div id="mcalslots" class="calslots"></div>
         <div id="calcountbar" class="calcountbar"><b id="calcount">0</b> of 12 months added &mdash; add all 12 for the full calendar (you can finish any you skip after your cover is approved).</div>
         <button type="button" class="savebtn" onclick="openFlipbook()">&#128214; Preview calendar</button>
       </div>
       <div class="dragbar">
         <div class="dbq">&#8596;&#65039; Reposition the wording or photo</div>
         <div class="dseg" role="group" aria-label="Select what to move">
           <button type="button" class="dmbtn sel" data-m="text" aria-label="Move the wording" onclick="setDragMode('text')">✍️ Wording</button>
           <button type="button" class="dmbtn" data-m="photo" aria-label="Move the photo" onclick="setDragMode('photo')">🖼️ Photo</button>
           <button type="button" class="dmbtn" aria-label="Auto-arrange my design" onclick="autoArrange()" style="margin-left:auto">✨ Auto-arrange</button>
           <button type="button" class="dmbtn" aria-label="Reset placement" onclick="resetPlacement()">↺ Reset</button>
         </div>
         <div class="dbhint">Drag any word or the photo on the preview to move it &middot; drag a corner to resize &middot; <b>Reset</b> restores the template.</div>
       </div>
           <div id="mphotoctl" style="display:none">
             <div class="pctitle">🖼️ Resize &amp; place your photo</div>
             <div class="photorow">
               <span class="plbl">Size</span>
               <span class="zico" aria-hidden="true">−</span>
               <input type="range" id="mphotozoom" min="0.2" max="3" step="0.05" value="1"
                 oninput="setPhotoZoom(this.value)" aria-label="Photo size">
               <span class="zico" aria-hidden="true">+</span>
             </div>
             <div class="photorow">
               <span class="plbl">Move</span>
               <button type="button" aria-label="Nudge photo left" onclick="nudgePhoto(-0.05,0)">&larr;</button>
               <button type="button" aria-label="Nudge photo right" onclick="nudgePhoto(0.05,0)">&rarr;</button>
               <button type="button" aria-label="Nudge photo up" onclick="nudgePhoto(0,-0.05)">&uarr;</button>
               <button type="button" aria-label="Nudge photo down" onclick="nudgePhoto(0,0.05)">&darr;</button>
               <button type="button" class="pcenter" onclick="autoCenterPhoto()">🎯 Center</button>
               <button type="button" class="tposreset" onclick="resetPhoto()">Reset</button>
             </div>
             <div class="dbhint">✋ Drag the photo on the preview to move it, or
               <span class="grabtip grabtip-blue"><span class="grabsq grabsq-blue"></span> drag the blue corner with your mouse to resize just the photo</span>.
               AI auto-centered your subject on upload.</div>
             <button type="button" class="pcenter" style="margin-top:4px" aria-label="Remove the photo background" onclick="removeBg()">&#9986;&#65039; Remove background</button>
             <span class="tposhint">best for logos &amp; solid backdrops</span>
             <button type="button" class="pdone" onclick="setDragMode('text')">&#10003; Done - edit text</button>
           </div>

       <div class="swrow" id="mwalltip" style="font-size:11px;color:#6b7a72;margin:8px 0 0">🛋️ Tip: try the <b>Your room wall</b> colors to preview it in your space.</div>
       <div class="mdescbox">
         <div class="lbl">📋 About this piece</div>
         <div class="mdesc" id="mdesc"></div>
       </div>
     </div>
     <div class="mright">
       <h2 id="mtitle"></h2><div class="mprice" id="mprice"></div>
       <div id="mavail" style="font-size:12px;color:#5a6b62;margin:-2px 0 8px">
         Available as: {materials_line}<br>
         <b>Frame not included</b> unless you choose a Framed option
         (6 frame styles: Essential → Classic → Premium). Canvas is gallery-wrapped (open).
       </div>
       <!-- One section at a time: finish it, tap Next - no scrolling hunt. -->
       <div id="esectabs" role="tablist" aria-label="Customize sections">
         <button type="button" data-e="1" class="sel" aria-current="step" onclick="editStep(1)">
           <span class="eicon">🎨</span><span class="elbl">1. Design</span></button>
         <button type="button" data-e="2" onclick="editStep(2)">
           <span class="eicon">📷</span><span class="elbl">2. Photo</span></button>
         <button type="button" data-e="3" onclick="editStep(3)">
           <span class="eicon">🖼️</span><span class="elbl" id="e3lbl">3. Frame &amp; size</span></button>
       </div>
       <div class="esec" id="esec1">
       <div class="perso">
         <div class="lbl">🎨 Your colors - the preview on the left updates live</div>
         <div class="swrow" id="mbglbl">Background</div>
         <div class="sw" id="mbg"></div>
         <div class="swrow">Text color</div>
         <div class="sw" id="mtxt"></div>
         <div id="mwallrow">
         <div class="swrow">🛋️ Your room wall <span style="color:#9aa49c;font-weight:400">(preview against your wall color)</span></div>
         <div class="sw" id="mwall"></div>
         </div>
         <div class="wordbox" id="mwordbox">
           <div class="wordlbl">✍️ Your wording - make it yours</div>
           <textarea id="mtext" maxlength="250" rows="4" oninput="onText()"
             placeholder="Type your message - e.g. &quot;Happy 40th, Sam - love you to the mountains and back&quot;. It previews live on the left."></textarea>
           <div class="cc"><span id="mcc">0 / 250</span> characters &middot; leave empty to keep the quote shown</div>
         </div>
         <div class="wordbox" id="mslotbox" style="display:none">
           <div class="wordlbl">✍️ Your wording - type each line</div>
           <div id="mslots" class="slotinputs"></div>
         </div>
         <div class="swrow">Font</div>
         <div class="fonts" id="mfonts"></div>
         <div class="swrow">Text size <span id="mtsizelbl" style="color:#9aa49c;font-weight:400">Auto</span></div>
         <div class="tsizerow">
           <input type="range" id="mtsize" min="0" max="40" value="0" step="1"
             oninput="setTextSize(this.value)">
           <button type="button" class="tposreset" onclick="resetTextPos()">Reset</button>
         </div>
         <div class="photorow">
           <span class="plbl">Move text</span>
           <button type="button" aria-label="Move wording left" onclick="nudgeText(-0.05,0)">&larr;</button>
           <button type="button" aria-label="Move wording right" onclick="nudgeText(0.05,0)">&rarr;</button>
           <button type="button" aria-label="Move wording up" onclick="nudgeText(0,-0.05)">&uarr;</button>
           <button type="button" aria-label="Move wording down" onclick="nudgeText(0,0.05)">&darr;</button>
           <button type="button" class="pcenter" onclick="centerText()">🎯 Center</button>
           <span class="tposhint">or drag it on the preview</span>
         </div>
         <div class="swrow">Rotate text <span id="mtrotlbl" style="color:#9aa49c;font-weight:400">0°</span>
           <span class="tposhint">drag the wording on the preview to move it (Text mode)</span></div>
         <div class="tsizerow">
           <input type="range" id="mtrot" min="-180" max="180" value="0" step="1"
             oninput="setTextRot(this.value)">
         </div>
         <div class="rotrow">
           <button type="button" onclick="setRot(-90)">⟲ Sideways</button>
           <button type="button" onclick="setRot(0)">Upright</button>
           <button type="button" onclick="setRot(90)">Sideways ⟳</button>
           <button type="button" onclick="setRot(180)">Flip</button>
         </div>
         <div class="freebar" role="note">
           <span class="fchk">✓ Personalization is 100% FREE</span>
           <span class="fchk">✓ Preview updates instantly</span>
         </div>
       </div>
       <div class="esecnav">
         <button type="button" class="esecnext" id="esec1next" onclick="editStep(2)">Next: add your photo →</button>
       </div>
       </div>
       <div class="esec" id="esec2" style="display:none">
         <div class="uploadbox">
           <div class="lbl">📷 Add your own photo (optional)</div>
           <input type="file" id="mupload"
             accept="image/jpeg,image/png,application/pdf,image/tiff"
             onchange="checkUpload()">
           <div id="muploadmsg" class="note" role="status" aria-live="polite"></div>
           <div id="maicheck" class="note" role="status" aria-live="polite"></div>
           <div class="note">High-resolution JPG/PNG/PDF/TIFF only - our AI
             auto-checks quality and asks for a better photo if needed; your
             approved photo is sent with the order to our print partner.</div>
         </div>
         <div class="note">🖼️ After uploading, the <b>photo zoom &amp; move
           controls appear under the preview</b> on the left. No photo? Just
           tap Next - this step is optional.</div>
         <div class="esecnav">
           <button type="button" class="esecback" onclick="editStep(1)">← Back</button>
           <button type="button" class="esecnext" id="esec2next" onclick="editStep(3)">Next: frame &amp; size →</button>
         </div>
       </div>
       <div class="esec" id="esec3" style="display:none">
       <div class="fpick" id="mfpick" style="display:none">
         <div class="ptype" id="mptype">
           <button type="button" class="ptbtn ptsel" id="ptwall" onclick="setProductType('wallart')">🖼️ Wall Art</button>
           <button type="button" class="ptbtn" id="ptapp" onclick="setProductType('apparel')">👕 Apparel</button>
         </div>
         <div class="lbl" id="mfpicklbl">👉 Choose your frame / material:</div>
         <div class="fchips" id="mfchips"></div>
       </div>
       <div class="orderbox" id="morderbox">
         <div class="lbl">🛒 Build your order (mix sizes &amp; quantities)<span class="stepbadge">👉 Next step</span></div>
         <div id="sizeprompt" class="sizeprompt" style="display:none">👇 Pick
           your <b>size</b> &amp; <b>quantity</b>, then tap <b>Add to basket</b></div>
         <div class="orow" id="mtierrow" style="display:none">
           <label>Quality <select id="mtier" onchange="setApparelTier(this.value)"></select></label>
         </div>
         <div class="orow">
           <label>Size <select id="msize" onchange="onSizeChange()"></select></label>
           <label>Qty <select id="mqty"></select></label>
         </div>
         <div id="mapparelnote" class="note" style="display:none">📏 Garment sizing is final — please check the size before ordering. Because every item is made to order, we can't exchange for fit.</div>
         <div id="mreview" class="mreview"></div>
         <div class="orderactions">
           <button type="button" class="savebtn" id="mreviewbtn" onclick="showFinalProof('item')">👁️ Review this design</button>
           <button type="button" class="addbasketbtn" id="maddbtn" onclick="addToBasket()">🛒 Add to basket</button>
         </div>
         <div class="orderreassure">&#10003; Free proof you approve on screen &middot; made to order &middot; happiness guarantee</div>
         <div id="mbasketbar" class="mbasketbar" onclick="openBasketFromModal()"></div>
         <!-- After adding to basket: clear next-step choices, so the buyer never
              has to hunt for the X and scroll back up. -->
         <div id="postadd" class="postadd" style="display:none">
           <span class="paok">&#10003; Added to your basket!</span>
           <button class="pacontinue" onclick="continueShopping()">&#8592; Continue shopping</button>
           <button class="pacheckout" onclick="closeM();toggleBasket()">Go to checkout &#8594;</button>
         </div>
         <div id="mcart" class="cart"></div>
         <div class="savedesignrow">
           <button type="button" class="savebtn2" onclick="saveDesign()">💾 Save this design for later</button>
         </div>
         <div class="note taxnote">🧾 Prices are per item. <b>Tax &amp; shipping are
           calculated at checkout</b> based on your location.</div>
       </div>
       <div class="esecnav">
         <button type="button" class="esecback" onclick="editStep(2)">← Back</button>
       </div>
       </div>
       <div class="rate" id="mrate" style="display:none">
         <div class="lbl">How likely are you to buy this as a gift?</div>
         <div class="stars2" id="mstars">
           <span data-v="1">&#9733;</span><span data-v="2">&#9733;</span><span data-v="3">&#9733;</span><span data-v="4">&#9733;</span><span data-v="5">&#9733;</span>
         </div>
         <div class="ratemsg" id="mratemsg"></div>
       </div>
       <a id="mfb" class="fbbtn" href="#">💬 Tell us what you think</a>
     </div>
   </div>
 </div>
</div>

<script>
 const DATA = {data_json};
 const OWNER = "{owner}";
 const PRICE_HI = "{price_hi}";
 const MAT_SHORT = "{mat_short}";
 const OPT_COUNT = "{opt_count}";
 const UAT = {str(bool(uat)).lower()};
 const FORM_URL = "{form_url}";
 let RATING = 0;          // current modal star rating
 function fbLink(t){{
   const r = RATING ? RATING + "/5" : "(not rated)";
   if(FORM_URL){{
     const sep = FORM_URL.indexOf('#')>=0 ? '&' : '#';
     return FORM_URL + sep + "listing=" + encodeURIComponent(t) +
            "&rating=" + encodeURIComponent(r);
   }}
   const s = encodeURIComponent("Joffiels feedback: " + t);
   const body = encodeURIComponent(
     "Star rating (buy as a gift): " + r + "\\n\\n" +
     "Would you buy this as a gift?  (yes / maybe / no)\\n\\n" +
     "Does the price feel right?\\n\\n" +
     "Anything to change about the design or wording?\\n\\n");
   return "mailto:" + OWNER + "?subject=" + s + "&body=" + body;
 }}
 function paintStars(){{
   document.querySelectorAll('#mstars span').forEach(function(el){{
     el.classList.toggle('on', parseInt(el.dataset.v) <= RATING);
   }});
 }}
 function setRating(v){{
   RATING = v; paintStars();
   document.getElementById('mratemsg').textContent =
     "Thanks! " + v + "/5 recorded - tap below to send it.";
   document.getElementById('mfb').href = fbLink(DATA[CUR].title);
 }}
 let CUR = 0;
 // First impression stays curated: show a few designs (Editor's picks first), with
 // a "Show all occasions" reveal. These are all the SAME customizable product with
 // different default wording, so an exhaustive wall reads as choice-overload.
 let GRID_COLLAPSED = true;
 const GRID_CAP = 6;
 const _isPick = d => EDITOR_PICKS.some(k=>((d.title||'')+' '+(d.occ||'')).toLowerCase().indexOf(k)>=0);
 function render(){{
   const g = document.getElementById('grid');
   var gc=document.getElementById('gridcount');
   if(gc) gc.textContent = DATA.length+' personalized designs - each a starting point you make your own';
   // Thumbnail quick-jump: tap any design to open its page instantly.
   var qj=document.getElementById('quickjump');
   if(qj) qj.innerHTML = DATA.map((d,i)=>`<button class="qjt" onclick="openM(${{i}})" `+
     `title="${{d.title}}" aria-label="Open ${{d.title}}">`+
     `<img src="${{d.imgs[0]}}" loading="lazy" alt="${{d.title}}">`+
     `<span>${{(d.occ||'').replace("'s day",'')}}</span></button>`).join('');
   // Lead with the owner-curated Editor's picks (stable sort keeps the rest in order).
   const _order = DATA.map((d,i)=>i).sort((a,b)=>(_isPick(DATA[a])?0:1)-(_isPick(DATA[b])?0:1));
   g.innerHTML = _order.map(i => {{ const d=DATA[i]; return `
     <div class="card" role="button" tabindex="0" aria-label="Personalize ${{d.title}}"
       data-title="${{((d.full_title||d.title)||'').toLowerCase()}}" data-occ="${{d.occ||''}}" onclick="openM(${{i}})"
       onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();openM(${{i}});}}">
       ${{_isPick(d)?'<span class="epick">&#10022; Editor&#39;s pick</span>':''}}
       <img class="hero" loading="lazy" src="${{d.imgs[0]}}" alt="${{d.title}} - personalized wall art preview">
       <div class="cap"><div class="ttl">${{d.title}}</div>
         <div class="pr">Starting at $${{d.price}}</div>
         <div class="prsub">${{MAT_SHORT}} &middot; ${{OPT_COUNT}} options to $${{PRICE_HI}}</div>
         <span class="fb">&#127912; Personalize now &#8594;</span><span class="cardtrust">&#10003; Free proof before printing &nbsp;&middot;&nbsp; &#10003; Happiness guarantee</span>
       </div>
     </div>`; }}).join('') +'';
   _capGrid();
 }}
 // Default view: show only the first GRID_CAP cards; reveal the rest on demand.
 function _capGrid(){{
   if(!GRID_COLLAPSED) return;
   const cards=document.querySelectorAll('#grid .card:not(.occallcard)');
   cards.forEach((c,idx)=>{{ c.style.display = idx<GRID_CAP ? '' : 'none'; }});
   const w=document.getElementById('gridmorewrap');
   if(w) w.style.display = cards.length>GRID_CAP ? '' : 'none';
 }}
 function expandGrid(){{
   GRID_COLLAPSED=false;
   document.querySelectorAll('#grid .card:not(.occallcard)').forEach(c=>c.style.display='');
   const w=document.getElementById('gridmorewrap'); if(w) w.style.display='none';
   const note=document.getElementById('occnote');
   if(note && !note.innerHTML) note.innerHTML='Showing all '+DATA.length+' designs - tap any to make it yours.';
 }}
 // Filter the product grid by occasion (Shop by occasion chips).
 // Occasion -> matching keywords (so chips match real product titles).
 const OCC_SYN={{
   "graduation":["graduation","graduate","grad","nurse","dentist","teacher","doctor"],
   "birthday":["birthday"],
   "wedding":["wedding","vows","bride","groom","marriage"],
   "anniversary":["anniversary","husband","wife"],
   "valentine's day":["valentine","love","heart","romance","sweetheart","couple","husband","wife","anniversary"],
   "mother's day":["mother","mom","grandma","mum"],
   "father's day":["father","dad","grandpa","papa"],
   "memorial":["memorial","remember","sympathy","heaven","loss","grief"],
   "new baby":["baby","newborn","nursery","christening","new arrival","shower"],
   "housewarming":["home","house","housewarming","new home","family"],
   "new home":["home","house","housewarming","family"],
   "faith":["faith","christian","prayer","bless","god","lord","scripture"],
   "christmas":["christmas","holiday","noel"]
 }};
 function shopByOccasion(occ, el){{
   // Filtering reveals everything matching - the first-impression cap no longer applies.
   GRID_COLLAPSED=false; var _gw=document.getElementById('gridmorewrap'); if(_gw)_gw.style.display='none';
   const q=(occ||'').toLowerCase();
   let shown=0;
   document.querySelectorAll('#grid .card:not(.occallcard)').forEach(c=>{{
     const cocc=(c.getAttribute('data-occ')||'');
     // every card carries its exact occasion key, so match on that only - no fuzzy
     // keyword fallback (which used to pull e.g. Anniversary under Valentine's Day).
     const ok = !q || cocc===q;
     c.style.display = ok ? '' : 'none'; if(ok) shown++;
   }});
   // Repeat the controls at the END of the results so you can switch occasion
   // right where you finish reading, without scrolling back up.
   const bottom=document.getElementById('occbottom');
   if(bottom){{
     if(q && shown>0){{
       bottom.innerHTML=`<button class="occallbtn" onclick="showAllDesigns()">`+
         `&#8593; Pick another occasion</button>`;
       bottom.style.display='';
     }} else {{ bottom.innerHTML=''; bottom.style.display='none'; }}
   }}
   document.querySelectorAll('.occhip').forEach(e=>e.classList.toggle('sel',e===el));
   const note=document.getElementById('occnote');
   if(q && shown===0){{                       // no matches -> show all, explain
     document.querySelectorAll('#grid .card').forEach(c=>c.style.display='');
     if(note) note.innerHTML=`No designs for <b>${{occ}}</b> yet - showing all. `+
       `Tell us what you'd like and we'll create it!`;
   }} else if(note){{
     note.innerHTML = q ? `Showing <b>${{shown}}</b> design${{shown!==1?'s':''}} for <b>${{occ}}</b>` : '';
   }}
   const grid=document.getElementById('grid');
   if(grid) grid.scrollIntoView({{behavior:'smooth',block:'start'}});
 }}
 function backToOccasions(){{
   const s=document.getElementById('occasions');
   if(s) s.scrollIntoView({{behavior:'smooth',block:'start'}});
 }}
 function showAllDesigns(){{
   GRID_COLLAPSED=false; var _gw2=document.getElementById('gridmorewrap'); if(_gw2)_gw2.style.display='none';
   document.querySelectorAll('#grid .card:not(.occallcard)').forEach(c=>c.style.display='');
   const ac=document.getElementById('occallcard'); if(ac) ac.style.display='none';
   const bottom=document.getElementById('occbottom'); if(bottom){{ bottom.innerHTML=''; bottom.style.display='none'; }}
   document.querySelectorAll('.occhip').forEach(e=>e.classList.remove('sel'));
   const note=document.getElementById('occnote'); if(note) note.innerHTML='';
   backToOccasions();
 }}
 // Pretty-print the plain-text listing description: ALL-CAPS lines become
 // section headers, "- " lines become bullets - readable, not a text wall.
 function fmtDesc(t){{
   const esc=function(s){{ return s.replace(/&/g,'&amp;')
     .replace(/</g,'&lt;').replace(/>/g,'&gt;'); }};
   return (t||'').split('\\n').map(function(l){{
     l=l.trim(); if(!l) return '';
     if(l.length<46 && /^[A-Z0-9][A-Z0-9 '&(),:+-]+$/.test(l))
       return '<div class="dsh">'+esc(l)+'</div>';
     if(l.indexOf('- ')===0) return '<div class="dsb">'+esc(l.slice(2))+'</div>';
     return '<div class="dsl">'+esc(l)+'</div>';
   }}).join('');
 }}
 function openM(i){{
   CUR = i; RATING = 0; paintStars(); REVIEWED=false; ADDED=false;
   WORD_DONE=false;
   setStep(1); editStep(1);
   // Desktop: park the cursor in the wording field, ready to type (skipped
   // on phones - auto-focus would pop the keyboard over the preview).
   if(window.matchMedia('(min-width:761px)').matches){{
     const t=document.getElementById('mtext');
     if(t) try{{ t.focus({{preventScroll:true}}); }}catch(e){{}}
   }}
   const d = DATA[i];
   const fp=document.getElementById('mfpick'), fc=document.getElementById('mfchips');
   // Every design opens in WALL-ART mode; the buyer can switch to Apparel.
   IS_APPAREL=false; IS_BRANDED=false; IS_MUG=false; IS_CAL=false; CURGARMENT="";
   {{const _w=document.getElementById('ptwall'),_a=document.getElementById('ptapp');
     if(_w&&_a){{_w.classList.add('ptsel');_a.classList.remove('ptsel');}}}}
   const _l=document.getElementById('mfpicklbl');
   if(_l)_l.textContent='👉 Choose your frame / material:';
   const _an=document.getElementById('mapparelnote'); if(_an)_an.style.display='none';
   // Frame picker is ALWAYS available: a card's own previews, else the global
   // format list - so every design is orderable in every frame/material.
   const fmts = curFormats(i);
   if(fmts.length){{
     fc.innerHTML=_fchips(fmts,i);
     fp.style.display='block';
   }}
   applyProductChrome(fmts);   // wall-art chrome by default; reset on every open
   WALLART_TITLE = d.full_title;       // baseline so apparel<->wall-art can restore
   document.getElementById('mtitle').textContent = d.full_title;
   document.getElementById('mprice').textContent =
     "from $" + ((fmts[0] && fmts[0].price) ? fmts[0].price : d.price);
   document.getElementById('mdesc').innerHTML = fmtDesc(d.desc);
   WALLART_DESC = document.getElementById('mdesc').innerHTML;  // baseline for restore
   document.getElementById('mratemsg').textContent = "";
   CURQUOTE = d.quote || ""; SELBG = BGCOLORS[0]; SELTXT = TXTCOLORS[0]; TXT_USER_SET=false; APPLACEMENT='front';
   SELFONT = FONTS[0][1]; SELWALL = WALLS[0][0];
   TPOS={{x:0.5,y:0.5}}; TSIZE=0; TROT=0; setDragMode('text');
   var ts=document.getElementById('mtsize'); if(ts)ts.value=0;
   var tl=document.getElementById('mtsizelbl'); if(tl)tl.textContent='Auto';
   var tr=document.getElementById('mtrot'); if(tr)tr.value=0;
   var trl=document.getElementById('mtrotlbl'); if(trl)trl.textContent='0°';
   // Start on the first format (poster); the picker + SIZEMAP take it from here.
   CURFMT = (fmts[0] && fmts[0].name) || (Object.keys(SIZEMAP)[0] || "");
   var mt=document.getElementById('mtext'); if(mt) mt.value="";
   var cc=document.getElementById('mcc'); if(cc) cc.textContent="0 / "+MAXCHARS;
   renderBg(); renderTxt(); renderWall(); renderFonts(); drawArt();
   initTextDrag();
   fillQty(); fillSizes(); drawArt(); renderCart(); updateReview();
   var um=document.getElementById('muploadmsg'); if(um) um.textContent="";
   PHOTO=null; PHOTO_ZOOM=1; PHOTO_FX=0.5; PHOTO_FY=0.5; _showPhotoCtl(false);
   // Clear any 12-month calendar photos from a prior design so they never carry
   // into a different calendar/order (privacy + wrong-photo-into-production guard).
   CAL_PHOTOS=[null,null,null,null,null,null,null,null,null,null,null,null];
   CAL_PHOTO_URLS=[null,null,null,null,null,null,null,null,null,null,null,null]; FLIP_PAGE=0; _updCalCount();
   var ui=document.getElementById('mupload'); if(ui) ui.value="";
   document.getElementById('mrate').style.display = UAT ? 'block':'none';
   const fb = document.getElementById('mfb');
   fb.href = fbLink(d.title);
   fb.textContent = FORM_URL ? "📝 Give feedback (1 min)" : "💬 Tell us what you think";
   fb.style.display = UAT ? 'block':'none';
   document.getElementById('modal').style.display='flex';
 }}
 const BGCOLORS = ["#103d2e","#1b1b1f","#3a2e24","#7a2e2e","#2e3a55","#f4efe6","#dcd6c8","#c9a84c"];
 const TXTCOLORS = ["#f4efe6","#ffffff","#c9a84c","#1b1b1f","#103d2e","#7a2e2e"];
 const FONTS = [["Cormorant","'Cormorant Garamond',serif"],
   ["Playfair","'Playfair Display',serif"],["Montserrat","'Montserrat',sans-serif"],
   ["Lora","'Lora',serif"],["Script","'Dancing Script',cursive"],
   ["Oswald","'Oswald',sans-serif"],["Bebas","'Bebas Neue',sans-serif"]];
 const MAXCHARS = 250;
 const SIZEMAP = {sizemap_json};
 const EDITOR_PICKS = {editor_picks_json};
 // Design-independent frame/material list - the guaranteed fallback so the
 // frame picker is available for EVERY design, even one whose previews failed.
 const ALL_FORMATS = {all_formats_json};
 // The format list for design i: its own per-frame previews, else the global
 // list (every design is orderable in every format).
 function fmtsFor(i){{ const f=DATA[i].formats; return (f&&f.length)?f:ALL_FORMATS; }}
 // ── Apparel: a parallel product type sharing this picker + design editor ──
 const APPAREL_FORMATS = {apparel_formats_json};
 // ── Custom Branded Products: a parallel product family sharing this editor ──
 // BRANDED_FORMATS: one entry per product x colour ("{{name}} - {{colour}}" + from-price).
 // BRANDED_DIMS: per-product print bound [w_px,h_px]. Customer-safe (no supplier data).
 const BRANDED_FORMATS = {branded_formats_json};
 const BRANDED_DIMS = {branded_dims_json};
 // Branded product NAME -> product_id, so the editor can resolve BRANDED_DIMS
 // (keyed by product_id) from the name shopBranded carries.
 const BRANDED_PID = {branded_pid_json};
 // ── Custom Mugs: a parallel product family sharing this editor ──
 // MUG_FORMATS: one entry per product x accent-colour ("{{name}} - {{colour}}" + from-price).
 // MUG_DIMS: per-product print bound [w_px,h_px]. Customer-safe (no supplier data).
 const MUG_FORMATS = {mug_formats_json};
 const MUG_DIMS = {mug_dims_json};
 // Mug product NAME -> product_id, so the editor can resolve MUG_DIMS (keyed by
 // product_id) from the name shopMug carries.
 const MUG_PID = {mug_pid_json};
 // ── Custom Calendars: a parallel product family sharing this editor ──
 // CAL_FORMATS: one entry per product x paper-colour ("{{name}} - {{colour}}" + from-price).
 // CAL_DIMS: per-product print bound [w_px,h_px]. Customer-safe (no supplier data).
 const CAL_FORMATS = {cal_formats_json};
 const CAL_DIMS = {cal_dims_json};
 // Calendar product NAME -> product_id, so the editor can resolve CAL_DIMS (keyed
 // by product_id) from the name shopCalendar carries.
 const CAL_PID = {cal_pid_json};
 // Real per-colour supplier photos {{type:{{colour:url}}}} - populated at go-live;
 // when empty the tile keeps its default photo (the swatch still rings + carries).
 const APPAREL_COLOR_IMG = {apparel_color_img_json};
 // Front + BACK garment photo per garment_id, so the editor can FLIP the garment
 // and the buyer can design the back too: {{garment_id:{{front,back}}}}.
 const APPAREL_SIDE_IMG = {apparel_side_img_json};
 const GARMENT_LOGO_SRC = "{garment_logo_src}";   // optional logo overlay (both sides)
 const APPGID = {appgid_json};            // garment name -> garment_id (editor lookup)
 // Quality tiers per garment: Classic name -> [{{tier,name,from}}]. A collapsed
 // tile opens the Classic garment; this lets the buyer switch to Value/Premium.
 const APPAREL_TIERS = {apparel_tiers_json};
 // Real product-photo mockups, keyed by product NAME: {{name:{{src,area,cyl,span}}}}.
 // Empty until the owner drops photos in -> the editor's generated mockup is used.
 // The preview composites the LIVE design into area (fractions of the photo); cyl
 // products wrap it on the barrel. Customer-safe (no supplier names).
 const MOCKUP_PHOTOS = {mockup_photos_json};
 let IS_APPAREL=false, CURGARMENT="", CURBASE="";
 // Branded mode reuses the WHOLE apparel editor (print frame, Layout Studio,
 // colour swatches) but draws onto a flat product field, not a garment.
 let IS_BRANDED=false;
 // Mug mode ALSO reuses the whole apparel/branded editor (print frame, Layout
 // Studio, colour swatches) but draws onto a WHITE ceramic mug body - the colour
 // variant is the rim/handle ACCENT, not the print field.
 let IS_MUG=false;
 // Calendar mode ALSO reuses the whole apparel/branded/mug editor (print frame,
 // Layout Studio, colour swatches) as a COVER DESIGNER - the buyer designs the
 // calendar COVER on a PORTRAIT white-paper field; the monthly pages are added
 // after approval. The colour variant is the paper stock, not a print field.
 let IS_CAL=false;
 // ── Calendars: 12-month photo engine + flip-through preview ──────────
 let CAL_PHOTOS=[null,null,null,null,null,null,null,null,null,null,null,null];
 // Hosted, print-partner-fetchable URL per month (filled by the server /upload), so
 // the actual month photos travel with the order - not just the on-screen preview.
 let CAL_PHOTO_URLS=[null,null,null,null,null,null,null,null,null,null,null,null];
 let CAL_YEAR=2026, FLIP_PAGE=0;
 const _MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
 const _WD=['Su','Mo','Tu','We','Th','Fr','Sa'];
 function calPhotoUpload(i,inp){{
   var f=inp.files&&inp.files[0]; if(!f) return;
   if(!/(jpe?g|png)$/i.test(f.name)){{ toast('Use a JPG or PNG photo for the calendar.'); inp.value=''; return; }}
   if(f.size>MAX_UPLOAD_MB*1048576){{ toast('That photo is too large (max '+MAX_UPLOAD_MB+' MB).'); inp.value=''; return; }}
   var r=new FileReader();
   r.onload=function(e){{ var im=new Image(); im.onload=function(){{ CAL_PHOTOS[i]=im; var s=document.getElementById('calslot'+i); if(s)s.classList.add('filled'); _updCalCount(); }}; im.src=e.target.result; }};
   r.readAsDataURL(f);
   _calUpload(i,f);   // send the bytes to the server so the month photo reaches production
 }}
 // Upload one month's photo to the server (same endpoint as the single print photo),
 // tagged cal-<month>, and remember the hosted URL it returns. Fire-and-forget; the
 // on-screen preview never waits on it. No-ops if not hosted / not signed in.
 function _calUpload(i,f){{
   try{{
     var email=knownEmail(); if(!UPLOAD_API||!email||!f) return;
     var fd=new FormData(); fd.append('file',f); fd.append('email',email);
     fd.append('name','cal-'+(i+1)); fd.append('size','calendar');
     fetch(UPLOAD_API,{{method:'POST',body:fd}}).then(function(r){{return r.json();}})
       .then(function(d){{ if(d&&d.url) CAL_PHOTO_URLS[i]=d.url; }}).catch(function(){{}});
   }}catch(e){{}}
 }}
 function setCalYear(v){{ CAL_YEAR=parseInt(v)||CAL_YEAR; }}
 // How many of the 12 months have a photo - powers the live counter, the order
 // payload, and the gentle "finish your months" nudge.
 function _calCount(){{ var n=0; for(var i=0;i<12;i++) if(CAL_PHOTOS[i]) n++; return n; }}
 // Calendar specifics carried into the saved design + the basket line so production
 // receives the 12-month intent (year + which months have a photo), not just the cover.
 function _calMeta(){{ if(!IS_CAL) return null;
   var filled=[]; for(var i=0;i<12;i++) if(CAL_PHOTOS[i]) filled.push(i);
   return {{kind:'12-month', year:CAL_YEAR, photos:filled.length, months:filled,
     urls:filled.map(function(i){{ return CAL_PHOTO_URLS[i]||''; }})}}; }}
 function _updCalCount(){{ var c=document.getElementById('calcount'); if(c) c.textContent=_calCount();
   var b=document.getElementById('calcountbar');
   if(b) b.className='calcountbar'+(_calCount()===12?' done':''); }}
 function renderCalSlots(){{
   var box=document.getElementById('mcalslots'); if(!box) return;
   box.innerHTML=_MONTHS.map(function(mn,i){{ return `<label class="calslot${{CAL_PHOTOS[i]?' filled':''}}" id="calslot${{i}}" title="${{mn}}"><span>${{mn.slice(0,3)}}</span><input type="file" accept="image/png,image/jpeg" aria-label="Photo for ${{mn}}" onchange="calPhotoUpload(${{i}},this)"></label>`; }}).join('');
   _updCalCount();
 }}
 function _drawMonthGrid(ctx,x,y,w,h,year,m){{
   ctx.save(); ctx.fillStyle='#1b1b1f'; ctx.textAlign='center';
   ctx.font='700 '+Math.round(h*0.12)+"px 'Oswald',sans-serif";
   ctx.fillText(_MONTHS[m].toUpperCase()+' '+year, x+w/2, y+h*0.10);
   var gx=x+w*0.04, gy=y+h*0.18, gw=w*0.92, cellW=gw/7, rowH=(h*0.80)/7;
   ctx.font='700 '+Math.round(rowH*0.42)+"px 'Montserrat',sans-serif"; ctx.fillStyle='#9a8f78';
   for(var d=0;d<7;d++) ctx.fillText(_WD[d], gx+cellW*d+cellW/2, gy+rowH*0.6);
   var first=new Date(year,m,1).getDay(), dim=new Date(year,m+1,0).getDate();
   ctx.fillStyle='#1b1b1f'; ctx.font='600 '+Math.round(rowH*0.4)+"px 'Montserrat',sans-serif";
   var day=1;
   for(var row=1;row<7 && day<=dim;row++){{
     for(var col=0;col<7;col++){{
       if(row===1 && col<first) continue;
       if(day>dim) break;
       ctx.fillText(String(day), gx+cellW*col+cellW/2, gy+rowH*(row+0.6)); day++;
     }}
   }}
   ctx.restore();
 }}
 function _drawCalPage(ctx,W,H,page){{
   ctx.save(); ctx.fillStyle='#fbfaf7'; ctx.fillRect(0,0,W,H);
   ctx.fillStyle='rgba(0,0,0,.22)';
   for(var i=0;i<12;i++){{ ctx.beginPath(); ctx.arc(W*(0.07+i*0.078), H*0.03, Math.max(2,W*0.008),0,7); ctx.fill(); }}
   if(page===0){{
     var cv=document.getElementById('mcanvas');
     if(cv){{ _CLEAN=true; drawArt();           // strip editor chrome (frame/handles) off the cover
       var s=Math.min((W*0.9)/cv.width,(H*0.82)/cv.height); var dw=cv.width*s, dh=cv.height*s; ctx.drawImage(cv,(W-dw)/2,H*0.08,dw,dh);
       _CLEAN=false; drawArt(); }}
   }} else if(page>=1 && page<=12){{
     var m=page-1, im=CAL_PHOTOS[m], px=W*0.06, py=H*0.07, pw=W*0.88, ph=H*0.50;
     if(im&&im.complete&&im.naturalWidth){{
       ctx.save(); ctx.beginPath(); ctx.rect(px,py,pw,ph); ctx.clip();
       var cov=Math.max(pw/im.naturalWidth, ph/im.naturalHeight), iw=im.naturalWidth*cov, ih=im.naturalHeight*cov;
       ctx.drawImage(im, px+(pw-iw)/2, py+(ph-ih)/2, iw, ih); ctx.restore();
     }} else {{ ctx.fillStyle='#ece7da'; ctx.fillRect(px,py,pw,ph); ctx.fillStyle='#b3a890'; ctx.textAlign='center'; ctx.font="600 "+Math.round(H*0.024)+"px 'Montserrat',sans-serif"; ctx.fillText('Add a photo for '+_MONTHS[m], W/2, py+ph/2); }}
     ctx.strokeStyle='rgba(0,0,0,.10)'; ctx.lineWidth=1; ctx.strokeRect(px,py,pw,ph);
     _drawMonthGrid(ctx, W*0.06, H*0.60, W*0.88, H*0.36, CAL_YEAR, m);
     // Faint trim-safe guide: anything important should sit inside this dashed line
     // (the page edge is trimmed in printing). Lets the buyer see the photo crop +
     // that the last week of the grid clears the trim.
     ctx.save(); ctx.strokeStyle='rgba(154,143,120,.55)'; ctx.lineWidth=1; ctx.setLineDash([5,4]);
     var sm=W*0.035, st=H*0.05; ctx.strokeRect(sm,st,W-2*sm,H-2*st); ctx.setLineDash([]); ctx.restore();
   }} else {{
     ctx.fillStyle='#9a8f78'; ctx.textAlign='center'; ctx.font="600 "+Math.round(H*0.032)+"px 'Cormorant Garamond',serif";
     ctx.fillText('Made just for you - '+CAL_YEAR, W/2, H*0.5);
   }}
   ctx.restore();
 }}
 function _renderFlip(){{
   var cv=document.getElementById('flipCanvas'); if(!cv) return;
   _drawCalPage(cv.getContext('2d'), cv.width, cv.height, FLIP_PAGE);
   var lbl=document.getElementById('flipLbl');
   if(lbl) lbl.textContent=(FLIP_PAGE===0?'Cover':(FLIP_PAGE>=1&&FLIP_PAGE<=12?_MONTHS[FLIP_PAGE-1]+' '+CAL_YEAR:'Back cover'));
 }}
 function openFlipbook(){{ FLIP_PAGE=0; var p=document.getElementById('flipPop'); if(p)p.style.display='flex'; _renderFlip(); }}
 function closeFlipbook(){{ var p=document.getElementById('flipPop'); if(p)p.style.display='none'; }}
 function flipPage(d){{ FLIP_PAGE=Math.max(0,Math.min(13,FLIP_PAGE+d)); _renderFlip(); }}
 // Strip a tier suffix ("Men's T-Shirt (Value)" -> "Men's T-Shirt") to find the
 // Classic base name that keys APPAREL_TIERS.
 function _baseName(n){{ return (n||'').replace(/ \\((?:Value|Premium)\\)$/,''); }}
 // Populate + show the Quality picker for the current garment (apparel only, and
 // only when more than one tier exists). Hidden for wall art / single-tier items.
 function renderTierRow(){{
   var row=document.getElementById('mtierrow'), sel=document.getElementById('mtier');
   if(!row||!sel) return;
   var tiers=(typeof APPAREL_TIERS!=='undefined' && APPAREL_TIERS[CURBASE])||[];
   if(!IS_APPAREL || tiers.length<2){{ row.style.display='none'; sel.innerHTML=''; return; }}
   row.style.display='';
   sel.innerHTML=tiers.map(function(t){{
     var lab=t.tier+(t.from!=null?(' — from $'+Number(t.from).toFixed(2)):'');
     return '<option value="'+t.name+'"'+(t.name===CURGARMENT?' selected':'')+'>'+lab+'</option>';
   }}).join('');
 }}
 // Switch the editor to the chosen quality tier, keeping the picked colour when the
 // tier offers it (else the tier's first colour). Refreshes swatches + price + size.
 function setApparelTier(name){{
   if(!name) return;
   var col=(CURFMT.split(' - ')[1])||_afVal('afColor')||'';
   CURGARMENT=name;                         // the tier's full garment name
   var fmts=apparelFormatsFor(), want=name+' - '+col, j=-1;
   for(var k=0;k<fmts.length;k++){{ if(fmts[k].name===want){{ j=k; break; }} }}
   if(j<0 && fmts.length){{ col=(fmts[0].name.split(' - ')[1])||''; }}
   renderBg();                              // colour swatches scoped to this tier
   if(col) selectApparelColor(col);
   fillSizes(); updateReview();
 }}
 // Apparel pills are scoped to the SELECTED garment (CURGARMENT) so the editor
 // shows just that garment's colours, not every garment in the catalogue.
 function apparelFormatsFor(){{
   return CURGARMENT
     ? APPAREL_FORMATS.filter(f=>f.name.indexOf(CURGARMENT+' - ')===0)
     : APPAREL_FORMATS; }}
 // Branded pills are scoped to the SELECTED product (CURGARMENT holds the product
 // name) - mirrors apparelFormatsFor but over BRANDED_FORMATS.
 function brandedFormatsFor(){{
   return CURGARMENT
     ? BRANDED_FORMATS.filter(f=>f.name.indexOf(CURGARMENT+' - ')===0)
     : BRANDED_FORMATS; }}
 // Mug pills are scoped to the SELECTED mug (CURGARMENT holds the product name) -
 // mirrors brandedFormatsFor but over MUG_FORMATS.
 function mugFormatsFor(){{
   return CURGARMENT
     ? MUG_FORMATS.filter(f=>f.name.indexOf(CURGARMENT+' - ')===0)
     : MUG_FORMATS; }}
 function calFormatsFor(){{
   return CURGARMENT
     ? CAL_FORMATS.filter(f=>f.name.indexOf(CURGARMENT+' - ')===0)
     : CAL_FORMATS; }}
 function curFormats(i){{ return IS_CAL?calFormatsFor():(IS_MUG?mugFormatsFor():(IS_BRANDED?brandedFormatsFor():(IS_APPAREL?apparelFormatsFor():fmtsFor(i)))); }}
 // Shared pill renderer (used by openM AND the product-type toggle).
 function _fchips(fmts,i){{ return fmts.map((f,j)=>
   `<span class="fchip${{j===0?' sel':''}}" id="fc${{j}}" tabindex="0" role="button" aria-label="${{f.name}}" onclick="pickFmt(${{i}},${{j}})">${{swatchDot(f.name)}}${{f.name}}${{f.price?` - $${{f.price}}`:''}}</span>`).join(''); }}
 let WALLART_AVAIL="", WALLART_DESC="", WALLART_TITLE="";
 // The modal heading in Apparel mode - garment-aware, never wall-art copy.
 function apparelTitle(){{
   return CURGARMENT
     ? ('Personalized '+CURGARMENT+' - Custom Printed Apparel, You Personalize It')
     : 'Personalized Custom Apparel - Tees, Hoodies & Sweatshirts You Personalize';
 }}
 const APPAREL_AVAIL_HTML='Available as a <b>T-Shirt, Hoodie or Sweatshirt</b> - '
   +'pick your garment, colour &amp; size next. Made to order, printed on the front.';
 const APPAREL_DESC_HTML='<b>A personalized garment, made to order just for you.</b><br>'
   +'1. Personalize it live - add the recipient name, occasion and your own words or '
   +'photo, and preview it on screen.<br>'
   +'2. Approve your free proof on screen - this is your final sign-off, locked in once '
   +'you submit.<br>'
   +'3. Printed on a premium tee, hoodie or sweatshirt and shipped with tracking.<br>'
   +'<b>What you get:</b> a one-of-a-kind personalized design, a free proof before '
   +'printing, and your chosen garment, colour &amp; size. Sizing is final - please '
   +'check the size before ordering.';
 // Swap the editor chrome between Wall Art and Apparel: hide the wall-only bits
 // (room-wall colours + tip) and switch the "available as" line, the "about"
 // description, the step label and the price so an apparel buyer never sees
 // poster/frame copy.
 // Branded chrome copy (no supplier / marketplace names). The product name keys
 // the heading; a generic "personalize it" flow mirrors the apparel about-text.
 function brandedTitle(){{
   return CURGARMENT
     ? ('Personalized '+CURGARMENT+' - Custom Printed, You Personalize It')
     : 'Personalized Custom Products - You Personalize It';
 }}
 const BRANDED_AVAIL_HTML='A <b>custom printed product</b> - pick your colour '
   +'&amp; size next. Made to order, personalized just for you.';
 const BRANDED_DESC_HTML='<b>A personalized product, made to order just for you.</b><br>'
   +'1. Personalize it live - add your name, occasion and your own words or photo, '
   +'and preview it on screen.<br>'
   +'2. Approve your free proof on screen - this is your final sign-off, locked in '
   +'once you submit.<br>'
   +'3. Printed and shipped with tracking.<br>'
   +'<b>What you get:</b> a one-of-a-kind personalized design, a free proof before '
   +'printing, and your chosen colour &amp; size. Sizing is final - please check the '
   +'size before ordering.';
 // Mug chrome copy (no supplier / marketplace names). The mug name keys the
 // heading; a generic "personalize it" flow mirrors the branded about-text.
 function mugTitle(){{
   return CURGARMENT
     ? ('Personalized '+CURGARMENT+' - Custom Printed Mug, You Personalize It')
     : 'Personalized Custom Mugs - You Personalize It';
 }}
 const MUG_AVAIL_HTML='A <b>custom printed mug</b> - pick your colour next. '
   +'Made to order, personalized just for you.';
 const MUG_DESC_HTML='<b>A personalized mug, made to order just for you.</b><br>'
   +'1. Personalize it live - add your name, occasion and your own words or photo, '
   +'and preview it on screen.<br>'
   +'2. Approve your free proof on screen - this is your final sign-off, locked in '
   +'once you submit.<br>'
   +'3. Printed and shipped with tracking.<br>'
   +'<b>What you get:</b> a one-of-a-kind personalized design, a free proof before '
   +'printing, and your chosen mug. Please check the details before ordering.';
 // Calendar chrome copy (no supplier / marketplace names). The editor designs the
 // calendar COVER and now also offers a live 12-month photo build + flip-through
 // preview; months left blank can still be finished after the cover is approved.
 function calTitle(){{
   return CURGARMENT
     ? ('Personalized '+CURGARMENT+' - Design Your Calendar Cover, You Personalize It')
     : 'Personalized Custom Calendars - Design Your Cover, You Personalize It';
 }}
 const CAL_AVAIL_HTML='A <b>custom printed calendar</b> - design the <b>cover</b> '
   +'here, pick your paper next. Made to order, personalized just for you.';
 const CAL_DESC_HTML='<b>A personalized calendar, made to order just for you.</b><br>'
   +'1. Design your <b>cover</b> live - add your name, occasion and your own words or '
   +'photo, and preview the cover on screen.<br>'
   +'2. <b>Add a photo for each of the 12 months</b> and preview your whole calendar '
   +'on screen - or finish any months you skip after your cover is approved.<br>'
   +'3. Approve your free proof on screen - your final sign-off, locked in once you '
   +'submit - then we print and ship with tracking.<br>'
   +'<b>What you get:</b> a one-of-a-kind personalized calendar cover, a free proof '
   +'before printing, and your chosen size. Please check the details before ordering.';
 function applyProductChrome(fmts){{
   // The shared print editor (movable frame + Layout Studio) is on for apparel,
   // branded AND mug; only wall art keeps the legacy framed-print chrome.
   const PRINT=IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL;
   ['mwallrow','mwalltip'].forEach(id=>{{const e=document.getElementById(id);
     if(e) e.style.display = PRINT ? 'none' : '';}});
   const av=document.getElementById('mavail');
   if(av){{ if(!WALLART_AVAIL && !PRINT) WALLART_AVAIL=av.innerHTML;
     av.innerHTML = IS_CAL ? CAL_AVAIL_HTML : (IS_MUG ? MUG_AVAIL_HTML : (IS_BRANDED ? BRANDED_AVAIL_HTML
       : (IS_APPAREL ? APPAREL_AVAIL_HTML : (WALLART_AVAIL || av.innerHTML)))); }}
   const md=document.getElementById('mdesc');
   if(md){{ if(!WALLART_DESC && !PRINT) WALLART_DESC=md.innerHTML;
     md.innerHTML = IS_CAL ? CAL_DESC_HTML : (IS_MUG ? MUG_DESC_HTML : (IS_BRANDED ? BRANDED_DESC_HTML
       : (IS_APPAREL ? APPAREL_DESC_HTML : (WALLART_DESC || md.innerHTML)))); }}
   const e3=document.getElementById('e3lbl');
   if(e3) e3.textContent = PRINT ? '3. Size' : '3. Frame & size';
   // Step 1 colour row is the SHIRT colour in apparel mode / product colour in
   // branded mode (the wall-art "Background" fill is not printed on a product).
   const bl=document.getElementById('mbglbl');
   if(bl) bl.textContent = IS_CAL ? '📅 Paper' : (IS_MUG ? '🍵 Colour' : (IS_BRANDED ? '🎁 Colour'
     : (IS_APPAREL ? '👕 Shirt colour' : 'Background')));
   const mp=document.getElementById('mprice');
   if(mp && fmts && fmts[0]) mp.textContent = 'from $'+fmts[0].price;
   // Heading: apparel/branded buyers must NEVER see the wall-art listing title.
   const mt=document.getElementById('mtitle');
   if(mt) mt.textContent = IS_CAL ? calTitle() : (IS_MUG ? mugTitle() : (IS_BRANDED ? brandedTitle()
     : (IS_APPAREL ? apparelTitle() : (WALLART_TITLE || mt.textContent))));
   // Print-placement (front/back) bar is apparel-only; branded is single-side v1.
   const pl=document.getElementById('mplacement');
   if(pl) pl.style.display = IS_APPAREL ? 'block' : 'none';
   // Movable design-frame controls run for apparel AND branded.
   const fb=document.getElementById('mframebar');
   if(fb) fb.style.display = PRINT ? 'block' : 'none';
   // Layout Studio panel runs for apparel AND branded; (re)build it.
   const lb=document.getElementById('mlayoutbar');
   if(lb) lb.style.display = PRINT ? 'block' : 'none';
   if(PRINT){{ renderLayoutGallery(); renderSlotInputs(); }}
   if(typeof _upd3DBtn==='function') _upd3DBtn();   // 3D button: mugs + branded bottles/tumblers
   // Calendars get an extra 12-month photo panel + flip-through preview.
   var _cb=document.getElementById('mcalbar');
   if(_cb)_cb.style.display=IS_CAL?'block':'none';
   if(IS_CAL)renderCalSlots();
 }}
 function setProductType(t){{ if(typeof close3D==='function') close3D();   // dismiss any open spin from the previous product
   IS_CAL=(t==='cal');
   IS_MUG=(t==='mug');
   IS_BRANDED=(t==='branded');
   IS_APPAREL=(t==='apparel');          // exactly one of apparel/branded/mug/cal is true
   TXT_USER_SET=false;                 // re-auto-contrast text for the new context
   if(IS_APPAREL && !CURGARMENT && APPAREL_FORMATS.length)
     CURGARMENT=APPAREL_FORMATS[0].name.split(' - ')[0];   // toggled w/o a tile
   if(IS_BRANDED && !CURGARMENT && BRANDED_FORMATS.length)
     CURGARMENT=BRANDED_FORMATS[0].name.split(' - ')[0];   // toggled w/o a tile
   if(IS_MUG && !CURGARMENT && MUG_FORMATS.length)
     CURGARMENT=MUG_FORMATS[0].name.split(' - ')[0];       // toggled w/o a tile
   if(IS_CAL && !CURGARMENT && CAL_FORMATS.length)
     CURGARMENT=CAL_FORMATS[0].name.split(' - ')[0];       // toggled w/o a tile
   if(IS_APPAREL && !CURBASE) CURBASE=_baseName(CURGARMENT);
   const wb=document.getElementById('ptwall'),ab=document.getElementById('ptapp');
   if(wb&&ab){{wb.classList.toggle('ptsel',!IS_APPAREL);ab.classList.toggle('ptsel',IS_APPAREL);}}
   const an=document.getElementById('mapparelnote'); if(an)an.style.display=IS_APPAREL?'block':'none';
   const fc=document.getElementById('mfchips'), fmts=curFormats(CUR);
   if(fc&&fmts.length)fc.innerHTML=_fchips(fmts,CUR);
   CURFMT=(fmts[0]&&fmts[0].name)||"";
   // Apparel/branded colour lives in Step 1 now, so hide the Step-3 colour/frame
   // picker (it stays the frame picker for wall art).
   const _PRINT=IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL;
   const fpk=document.getElementById('mfpick');
   if(fpk) fpk.style.display = _PRINT ? 'none' : (fmts.length?'block':'none');
   const lbl=document.getElementById('mfpicklbl');
   if(lbl)lbl.textContent=_PRINT?'':'👉 Choose your frame / material:';
   applyProductChrome(fmts);
   renderBg();                         // colour swatches (apparel/branded) / Background
   if(_PRINT){{
     autoContrastText((CURFMT.split(' - ')[1]||''));
     BOX={{x:0.50,y:0.35,s:1.0}};      // reset the design frame position + size
     var _fs=document.getElementById('mframesize'); if(_fs) _fs.value=1;
   }}
   if(IS_APPAREL){{
     APPLACEMENT='front';              // start on the front side (apparel only)
     SIDES={{front:null,back:null}};   // clear both sides' designs for the new garment
     document.querySelectorAll('#mplacement .plbtn').forEach(function(b){{
       b.classList.toggle('sel', b.dataset.p==='front'); }});
     LOGO_ON=false;                    // reset the logo toggle + back hint per open
     var _lc=document.getElementById('mlogo'); if(_lc) _lc.checked=false;
     var _bh=document.getElementById('mbackhint'); if(_bh) _bh.style.display='none';
   }}
   renderTierRow();                    // quality picker (apparel, multi-tier only)
   fillSizes(); drawArt(); updateReview();
   _applyCarry();                      // cross-sell hop: carry the prior wording over
 }}
 // Entry point from the homepage Apparel category: open the editor straight into
 // apparel mode and preselect the chosen garment's first colour.
 function shopApparel(garment,color){{
   if(!DATA.length) return;
   openM(0);                       // openM clears CURGARMENT; set it AFTER
   CURGARMENT=garment||"";         // the full garment name, e.g. "Men's T-Shirt"
   CURBASE=garment||"";            // the Classic base name keys the tier picker
   var col=color||_afVal('afColor');  // a clicked swatch, else the active filter colour
   setProductType('apparel');      // scopes the pills to that garment's colours
   if(col) selectApparelColor(col);   // open the live preview in that colour
   renderTierRow();                   // offer Value/Classic/Premium for this garment
 }}
 // Entry point from a Branded Products tile: open the shared editor straight into
 // branded mode (flat product field, no front/back), preselecting the colour.
 // CURGARMENT holds the product NAME (BRANDED_PID maps it to a product_id).
 function shopBranded(name,color){{
   if(!DATA.length) return;
   openM(0);                       // openM clears CURGARMENT; set it AFTER
   CURGARMENT=name||"";            // the branded product name, e.g. "Tote Bag"
   CURBASE="";                     // branded has no quality-tier picker
   var col=color||'';             // the tile's first colour
   setProductType('branded');      // scopes the pills to that product's colours
   if(col) selectApparelColor(col);   // open the live preview in that colour
 }}
 // Entry point from a Custom Mugs tile: open the shared editor straight into mug
 // mode (white ceramic body, colour = rim/handle accent), preselecting the colour.
 // CURGARMENT holds the mug NAME (MUG_PID maps it to a product_id).
 function shopMug(name,color){{
   if(!DATA.length) return;
   openM(0);                       // openM clears CURGARMENT; set it AFTER
   CURGARMENT=name||"";            // the mug product name, e.g. "Classic Mug"
   CURBASE="";                     // mugs have no quality-tier picker
   var col=color||'';             // the tile's first colour
   setProductType('mug');          // scopes the pills to that mug's colours
   if(col) selectApparelColor(col);   // open the live preview in that colour
 }}
 // Entry point from a Custom Calendars tile: open the shared editor straight into
 // calendar COVER-designer mode (PORTRAIT white-paper field), preselecting paper.
 // CURGARMENT holds the calendar NAME (CAL_PID maps it to a product_id).
 function shopCalendar(name,color){{
   if(!DATA.length) return;
   openM(0);                       // openM clears CURGARMENT; set it AFTER
   CURGARMENT=name||"";            // the calendar product name, e.g. "Wall Calendar"
   CURBASE="";                     // calendars have no quality-tier picker
   var col=color||'';             // the tile's first paper colour
   setProductType('cal');          // scopes the pills to that calendar's papers
   if(col) selectApparelColor(col);   // open the live preview on that paper
 }}
 // Occasion-first entry: open the editor pre-loaded with the occasion's quote,
 // ready for the buyer to personalize (they can edit/replace it).
 function shopApparelOccasion(quote){{
   shopApparel("Men's T-Shirt","");
   var t=document.getElementById('mtext'); if(t) t.value=quote||'';
   var cc=document.getElementById('mcc'); if(cc) cc.textContent=(quote||'').length+' / '+MAXCHARS;
   CURQUOTE=quote||CURQUOTE; drawArt();
 }}
 // Preselect a garment colour in the editor so the preview renders in it -
 // applies the colour WITHOUT auto-advancing the step (unlike a chip click).
 function selectApparelColor(color){{
   var fmts=IS_CAL?calFormatsFor():(IS_MUG?mugFormatsFor():(IS_BRANDED?brandedFormatsFor():apparelFormatsFor())), target=CURGARMENT+' - '+color, j=-1;
   for(var k=0;k<fmts.length;k++){{ if(fmts[k].name===target){{ j=k; break; }} }}
   if(j<0) return;
   CURFMT=fmts[j].name;
   document.querySelectorAll('#mfchips .fchip').forEach(function(e,k){{
     e.classList.toggle('sel',k===j); }});
   document.querySelectorAll('#mbg span').forEach(function(e,k){{
     e.classList.toggle('sel',k===j); }});           // Step-1 shirt swatch in sync
   if(fmts[j].price) document.getElementById('mprice').textContent='from $'+fmts[j].price;
   autoContrastText(color);
   drawArt(); fillSizes();
 }}
 // Real per-colour photo for a tile (go-live), else '' to keep the default shot.
 function _tileColorUrl(type,color){{ var m=APPAREL_COLOR_IMG[type]; return (m&&m[color])||''; }}
 function swapTileColor(card,color){{
   var img=card.querySelector('.appimg'); if(!img) return;
   img.src = _tileColorUrl(card.dataset.gid,color) || card.dataset.defimg || img.src; }}
 function resetTileColor(card){{
   var img=card.querySelector('.appimg');
   if(img && card.dataset.defimg) img.src=card.dataset.defimg; }}
 // Preview a colour ON the tile (ring the dot + swap the photo at go-live). Does
 // NOT open the editor - the tile body / CTA does that, in the active colour.
 function selectTileColor(card,color){{
   card.dataset.activecolor=color;
   card.querySelectorAll('.swdot').forEach(function(d){{
     d.classList.toggle('seldot', d.getAttribute('data-color')===color); }});
   swapTileColor(card,color); }}
 // Paint each apparel tile's available-colour swatch dots (one source of truth:
 // APPARELCOLOR) and remember its default photo so colours can swap + reset.
 function initApparelSwatches(){{
   document.querySelectorAll('.appcard').forEach(function(card){{
     var img=card.querySelector('.appimg');
     if(img && !card.dataset.defimg) card.dataset.defimg=img.getAttribute('src')||'';
     var box=card.querySelector('.appsw'); if(!box||box.children.length) return;
     (card.dataset.colors||'').split('|').forEach(function(cn){{
       if(!cn) return;
       var dot=document.createElement('i');
       dot.className='swdot'; dot.title=cn; dot.setAttribute('data-color',cn);
       dot.style.background=(typeof APPARELCOLOR!=='undefined' && APPARELCOLOR[cn])||'#bbb';
       dot.onclick=function(ev){{ ev.stopPropagation(); selectTileColor(card,cn); }};
       box.appendChild(dot);
     }});
   }});
 }}
 function _afVal(id){{var e=document.getElementById(id);return e?e.value:'';}}
 function applyApparelFilters(){{
   var d=_afVal('afDept'),t=_afVal('afType'),b=_afVal('afBrand'),
       c=_afVal('afColor'),s=_afVal('afSize');
   var cards=document.querySelectorAll('.appcard'),shown=0;
   cards.forEach(function(card){{
     var ds=card.dataset;
     var ok=(!d||ds.gender===d)&&(!t||ds.type===t)&&(!b||ds.brand===b)
       &&(!c||(ds.colors||'').split('|').indexOf(c)>=0)
       &&(!s||(ds.sizes||'').split('|').indexOf(s)>=0);
     card.classList.toggle('hide',!ok); if(ok)shown++;
     // ring the chosen colour's swatch on each matching tile + swap the photo
     card.querySelectorAll('.swdot').forEach(function(dot){{
       dot.classList.toggle('seldot', !!c && dot.getAttribute('data-color')===c);
     }});
     if(c){{ ds.activecolor=c; swapTileColor(card,c); }}
     else {{ ds.activecolor=''; resetTileColor(card); }}
   }});
   document.querySelectorAll('.appgroup').forEach(function(gp){{
     gp.classList.toggle('hide',gp.querySelectorAll('.appcard:not(.hide)').length===0);
   }});
   var cnt=document.getElementById('afCount');
   if(cnt)cnt.textContent=shown+(shown===1?' style':' styles');
   var nm=document.getElementById('afNoMatch');
   if(nm)nm.style.display=shown?'none':'block';
 }}
 function clearApparelFilters(){{
   ['afDept','afType','afBrand','afColor','afSize'].forEach(function(id){{
     var e=document.getElementById(id); if(e)e.value='';
   }});
   applyApparelFilters();
 }}
 function applyBrandedFilters(){{
   var cat=_afVal('bfCat'),t=_afVal('bfType'),
       c=_afVal('bfColor'),s=_afVal('bfSize');
   var cards=document.querySelectorAll('.brandcard'),shown=0;
   cards.forEach(function(card){{
     var ds=card.dataset;
     var ok=(!cat||ds.cat===cat)&&(!t||ds.type===t)
       &&(!c||(ds.colors||'').split(',').indexOf(c)>=0)
       &&(!s||(ds.sizes||'').split(',').indexOf(s)>=0);
     card.classList.toggle('hide',!ok); if(ok)shown++;
   }});
   var cnt=document.getElementById('bfCount');
   if(cnt)cnt.textContent=shown+(shown===1?' product':' products');
   var nm=document.getElementById('bfNoMatch');
   if(nm)nm.style.display=shown?'none':'block';
 }}
 function clearBrandedFilters(){{
   ['bfCat','bfType','bfColor','bfSize'].forEach(function(id){{
     var e=document.getElementById(id); if(e)e.value='';
   }});
   applyBrandedFilters();
 }}
 function applyMugFilters(){{
   var cat=_afVal('mgCat'),t=_afVal('mgType'),
       c=_afVal('mgColor'),s=_afVal('mgSize');
   var cards=document.querySelectorAll('.mugcard'),shown=0;
   cards.forEach(function(card){{
     var ds=card.dataset;
     var ok=(!cat||ds.cat===cat)&&(!t||ds.type===t)
       &&(!c||(ds.colors||'').split(',').indexOf(c)>=0)
       &&(!s||(ds.sizes||'').split(',').indexOf(s)>=0);
     card.classList.toggle('hide',!ok); if(ok)shown++;
   }});
   var cnt=document.getElementById('mgCount');
   if(cnt)cnt.textContent=shown+(shown===1?' product':' products');
   var nm=document.getElementById('mgNoMatch');
   if(nm)nm.style.display=shown?'none':'block';
 }}
 function clearMugFilters(){{
   ['mgCat','mgType','mgColor','mgSize'].forEach(function(id){{
     var e=document.getElementById(id); if(e)e.value='';
   }});
   applyMugFilters();
 }}
 function applyCalFilters(){{
   var cat=_afVal('clCat'),t=_afVal('clType'),s=_afVal('clSize');
   var cards=document.querySelectorAll('.calcard'),shown=0;
   cards.forEach(function(card){{
     var ds=card.dataset;
     var ok=(!cat||ds.cat===cat)&&(!t||ds.type===t)
       &&(!s||(ds.sizes||'').split(',').indexOf(s)>=0);
     card.classList.toggle('hide',!ok); if(ok)shown++;
   }});
   var cnt=document.getElementById('clCount');
   if(cnt)cnt.textContent=shown+(shown===1?' product':' products');
   var nm=document.getElementById('clNoMatch');
   if(nm)nm.style.display=shown?'none':'block';
 }}
 function clearCalFilters(){{
   ['clCat','clType','clSize'].forEach(function(id){{
     var e=document.getElementById(id); if(e)e.value='';
   }});
   applyCalFilters();
 }}
 let CART = [];
 const QD = {qty_discount_json};
 function qdisc(q){{let best=0; for(const t of QD){{if(q>=t[0]&&t[1]>best)best=t[1];}} return best;}}
 function fillQty(){{const s=document.getElementById('mqty'); if(s&&!s.options.length){{
   for(let i=1;i<=10;i++){{const o=document.createElement('option');o.value=i;o.text=i;s.add(o);}}}}}}
 function fillSizes(){{const sel=document.getElementById('msize'); if(!sel)return;
   const rows=SIZEMAP[CURFMT]||SIZEMAP[Object.keys(SIZEMAP)[0]]||[];  // never empty
   sel.innerHTML=rows.map(r=>`<option value="${{r.size}}|${{r.price}}">${{r.size}}${{(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL)?'':' in'}} - $${{r.price}}</option>`).join('');
   if(typeof _upd3DBtn==='function') _upd3DBtn();}}    // show 3D for branded bottles/tumblers too
 function addToOrder(){{const sv=(document.getElementById('msize')||{{}}).value; if(!sv)return;
   // Guard: an uploaded photo flagged too low-res would print blurry - confirm first.
   const um=document.getElementById('muploadmsg');
   if(um && um.className.indexOf('upbad')>=0){{
     if(!confirm("Your uploaded photo may be too low-resolution for a sharp print. "
       +"Add anyway? (You can upload a higher-res photo instead.)")) return;
   }}
   const p=sv.split('|'); const qty=parseInt((document.getElementById('mqty')||{{}}).value||'1');
   const title=(DATA[CUR]||{{}}).title||'';
   // Capture the side being viewed, then record which sides carry a design so the
   // order knows the front AND back content (each side is independent).
   if(IS_APPAREL) SIDES[APPLACEMENT]=_captureSide();
   const _has=function(s){{ return !!(s && (((s.quote||'').trim()) || s.photoSrc || _slotsFilled(s.slots) || (s.collage&&s.collage.some(Boolean)))); }};
   const _sides = IS_APPAREL ? {{front:_has(SIDES.front), back:_has(SIDES.back)}} : null;
   CART.push({{fmt:CURFMT,size:p[0],unit:parseFloat(p[1]),qty:qty,title:title,
     placement:(IS_APPAREL?APPLACEMENT:''),
     sides:_sides, wording:_slotWording(),
     layout:((IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL)?CURLAYOUT:''),
     cal:_calMeta(),
     logo:(IS_APPAREL&&LOGO_ON)?'front+back':''}}); renderCart();
   var pa=document.getElementById('postadd'); if(pa){{pa.style.display='flex'; pa.scrollIntoView({{block:'nearest'}});}}
   clearDraft(); if(typeof abConvert==='function') abConvert();
   // In a guided bundle: advance to the next selected design to personalize.
   if(BFLOW){{ BFLOW.idx++; nextBundleStep(); }}}}
 function clearDraft(){{
   try{{localStorage.removeItem('jf_draft');}}catch(e){{}}
   const b=document.getElementById('resumeBar'); if(b)b.style.display='none';
   const email=knownEmail();
   if(email && CUSTOMIZE_API){{
     fetch(CUSTOMIZE_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
       body:JSON.stringify({{email:email, listing:(DATA[CUR]||{{}}).title||'',
         material:CURFMT, status:'converted'}})}}).catch(function(){{}});
   }}
 }}
 function rmLine(i){{CART.splice(i,1);renderCart();}}
 // Bundle discount applies to the TOTAL number of items in the basket (the
 // advertised "buy more, save more" tiers), not per line - each line is qty 1,
 // so the old per-line discount gave 0% and the shown savings never applied.
 function _totalQty(){{ return CART.reduce((s,l)=>s+(l.qty||1),0); }}
 // ONE canonical per-line subtotal (discounted unit rounded to cents, x qty)
 // used by _cartTotal AND every visible row, so the Subtotal always equals the
 // sum of the lines the customer sees (no round-then-sum vs sum-then-round gap).
 function _lineSub(l,d){{ return +(+(l.unit*(1-d)).toFixed(2)*l.qty).toFixed(2); }}
 function _cartTotal(){{const d=qdisc(_totalQty());
   return +CART.reduce((t,l)=>t+_lineSub(l,d),0).toFixed(2);}}
 function renderCart(){{const c=document.getElementById('mcart');
   renderBasket();
   if(!c)return;
   if(!CART.length){{c.innerHTML='<div class="note">No items yet - choose size + qty, then Add.</div>';return;}}
   const d=qdisc(_totalQty());
   let tot=0; c.innerHTML=CART.map((l,i)=>{{
     const unit=+(l.unit*(1-d)).toFixed(2); const sub=_lineSub(l,d); tot+=sub;
     const nm=l.title?`<b>${{l.title.slice(0,26)}}</b> - `:'';
     return `<div class="line"><span>${{nm}}${{l.qty}}x ${{l.fmt}} ${{l.size}}${{d?` (${{Math.round(d*100)}}% off)`:''}}</span>`+
       `<span>$${{sub.toFixed(2)}} <span class="rm" onclick="rmLine(${{i}})">remove</span></span></div>`;}}).join('')+
     `<div class="line tot"><span>Order total</span><span>$${{tot.toFixed(2)}}</span></div>`;}}
 // ── Persistent basket (across designs) ──
 const CHECKOUT_URL = "{etsy_shop_url}";
 const PAY_LINK = "{payment_link_url}";
 const EST_TAX_PCT = {est_tax_pct};   // 0 = tax calculated at checkout
 function toggleNav(){{const m=document.getElementById('navMenu');
   const b=document.querySelector('.navham');if(!m)return;
   const open=m.classList.toggle('open');
   if(b)b.setAttribute('aria-expanded',open?'true':'false');}}
 function closeNav(){{const m=document.getElementById('navMenu');
   const b=document.querySelector('.navham');if(m)m.classList.remove('open');
   if(b)b.setAttribute('aria-expanded','false');}}
 // Department-gated view: products live UNDER their category. The default page
 // shows only the department cards; choosing one reveals that department's pane.
 let DEPT=null;
 function selectDept(d){{
   DEPT=d;
   var w=document.getElementById('deptWall'), a=document.getElementById('deptApparel'),
       br=document.getElementById('deptBranded'), mg=document.getElementById('deptMug'),
       cl=document.getElementById('deptCal');
   var sw=document.getElementById('deptswitch');
   if(w) w.style.display = d==='wall' ? '' : 'none';
   if(a) a.style.display = d==='apparel' ? '' : 'none';
   if(br) br.style.display = d==='branded' ? '' : 'none';
   if(mg) mg.style.display = d==='mug' ? '' : 'none';
   if(cl) cl.style.display = d==='cal' ? '' : 'none';
   if(sw){{ sw.style.display='flex';
     var bw=sw.querySelector('.dswall'), ba=sw.querySelector('.dsapp'),
         bb=sw.querySelector('.dsbranded'), bm=sw.querySelector('.dsmug'),
         bc=sw.querySelector('.dscal');
     if(bw) bw.classList.toggle('on', d==='wall');
     if(ba) ba.classList.toggle('on', d==='apparel');
     if(bb) bb.classList.toggle('on', d==='branded');
     if(bm) bm.classList.toggle('on', d==='mug');
     if(bc) bc.classList.toggle('on', d==='cal'); }}
   var pane = d==='wall' ? w : (d==='apparel' ? a : (d==='branded' ? br : (d==='mug' ? mg : cl)));
   if(pane) pane.scrollIntoView({{behavior:'smooth',block:'start'}});
 }}
 function showAllDepartments(){{
   DEPT=null;
   var w=document.getElementById('deptWall'), a=document.getElementById('deptApparel'),
       br=document.getElementById('deptBranded'), mg=document.getElementById('deptMug'),
       cl=document.getElementById('deptCal');
   var sw=document.getElementById('deptswitch');
   if(w) w.style.display='none'; if(a) a.style.display='none';
   if(br) br.style.display='none'; if(mg) mg.style.display='none';
   if(cl) cl.style.display='none';
   if(sw) sw.style.display='none';
   var d=document.getElementById('depts'); if(d) d.scrollIntoView({{behavior:'smooth',block:'start'}});
 }}
 function toggleBasket(){{const p=document.getElementById('basketPanel');
   const open=p.style.display!=='flex'; renderBasket(); p.style.display=open?'flex':'none';}}
 function clearBasket(){{ if(CART.length && !confirm('Empty your basket?')) return;
   CART=[]; renderCart(); }}
 function renderBasket(){{
   const cnt=document.getElementById('basketCount'); if(cnt)cnt.textContent=CART.length;
   const cntN=document.getElementById('basketCountNav'); if(cntN)cntN.textContent=CART.length;
   // Empty basket = nothing to check out or clear: disable both actions
   // (no native alert popups in the buying flow, ever).
   const co=document.getElementById('bpcobtn'), cl=document.getElementById('bpclearbtn');
   if(co)co.disabled=!CART.length;
   if(cl)cl.disabled=!CART.length;
   // "Add another design" only makes sense once something is in the basket
   // (the empty state has its own Browse designs CTA).
   const mo=document.getElementById('bpmorebtn');
   if(mo)mo.style.display=CART.length?'block':'none';
   const ln=document.getElementById('basketLines'), tt=document.getElementById('basketTotal');
   if(!ln) return;
   if(!CART.length){{ ln.innerHTML='<div class="note">Your basket is empty. '+
       'Tap a design, personalize it, and Add to order.</div>'+
       '<button type="button" class="esecnext" style="width:100%" '+
       'onclick="toggleBasket();location.hash=\\'#shop\\'">Browse designs →</button>';
     if(tt)tt.textContent=''; return; }}
   const dAll=qdisc(_totalQty());
   ln.innerHTML=CART.map((l,i)=>{{const d=dAll;
     const sub=_lineSub(l,d);
     const nm=l.title?`<b>${{l.title.slice(0,30)}}</b><br>`:'';
     return `<div class="bpline"><span>${{nm}}${{l.qty}}x ${{l.fmt}} ${{l.size}}`+
       `${{d?` (${{Math.round(d*100)}}% off)`:''}}</span>`+
       `<span>$${{sub.toFixed(2)}} <span class="rm" onclick="rmLine(${{i}})">remove</span></span></div>`;}}).join('');
   if(tt){{
     const sub=_cartTotal();
     let rows=`<span>Subtotal (${{CART.length}} item${{CART.length>1?'s':''}})</span>`+
       `<span>$${{sub.toFixed(2)}}</span>`;
     if(EST_TAX_PCT>0){{ const tax=sub*EST_TAX_PCT/100;
       rows+=`<span class="bptax">Est. tax (${{EST_TAX_PCT}}%)*</span><span class="bptax">$${{tax.toFixed(2)}}</span>`+
         `<span><b>Est. total</b></span><span><b>$${{(sub+tax).toFixed(2)}}</b></span>`; }}
     tt.innerHTML=rows;
   }}
   const note=document.getElementById('basketTaxNote');
   if(note) note.innerHTML = EST_TAX_PCT>0
     ? "*Estimate only. Tax &amp; shipping are calculated and collected at secure checkout based on your location."
     : "Tax &amp; shipping are calculated at secure checkout based on your location.";
   // In-modal basket bar so customers always see what's in their basket.
   const bar=document.getElementById('mbasketbar');
   if(bar) bar.innerHTML = CART.length
     ? `🛒 <b>${{CART.length}} item${{CART.length>1?'s':''}}</b> &middot; $${{_cartTotal().toFixed(2)}} `+
       `<span class="mbview">Review &amp; checkout &rarr;</span>`
     : '';
 }}
 function checkout(){{
   if(!CART.length) return;                  // button is disabled when empty
   closeBasket(); showFinalProof('final');   // final review of ALL items, then accept all
 }}
 // Customize-panel wizard: one section at a time (1 Design, 2 Photo,
 // 3 Frame & size + add) - finish a section, tap Next. The preview stays
 // visible on the left throughout.
 function editStep(n){{
   for(let i=1;i<=3;i++){{
     const s=document.getElementById('esec'+i);
     if(s) s.style.display=(i===n)?'block':'none';
   }}
   document.querySelectorAll('#esectabs button').forEach(function(b){{
     const e=parseInt(b.dataset.e), cur=e===n;
     b.classList.toggle('sel',cur);
     b.classList.toggle('done', e<n);     // finished sections read as progress
     if(cur) b.setAttribute('aria-current','step');
     else b.removeAttribute('aria-current');
   }});
   ESEC=n;
   if(n>=2) WORD_DONE=true;     // moving on = keeping the shown quote
   if(n===3) promptSizeQty();   // never leave the customer waiting: guide them
   guide();                     // recompute the single beacon for this step
   // On phones the sections sit below the preview - bring them into view.
   const tabs=document.getElementById('esectabs');
   if(tabs && window.matchMedia('(max-width:760px)').matches)
     tabs.scrollIntoView({{behavior:'smooth', block:'start'}});
 }}
 // Spotlight the size & quantity pickers (shown on arrival in Frame & size
 // and again after a frame is chosen) so the path to Add to basket is obvious.
 // ── Guidance engine: ONE beacon at a time walks the customer to checkout.
 // Task order: finish Design -> finish Photo -> pick size & qty -> review
 // the design -> add to basket -> go to checkout. The engine recomputes on
 // every state change, so going Back re-lights that step's beacon until the
 // task is genuinely complete.
 let ESEC=1, REVIEWED=false, ADDED=false, WORD_DONE=false;
 function guide(){{
   document.querySelectorAll('.pulseon').forEach(function(e){{
     e.classList.remove('pulseon'); }});
   document.querySelectorAll('.attn').forEach(function(e){{
     e.classList.remove('attn'); }});
   // The active section tab breathes softly (the strong pulse stays on the
   // ONE action that finishes the current task).
   document.querySelectorAll('#esectabs button').forEach(function(b){{
     b.classList.toggle('tabglow', b.classList.contains('sel')); }});
   // Once frame selection is done (past the design/photo sections, not yet
   // added), the order card becomes the active NEXT STEP - light it up and
   // gently bring it into view the first time it activates.
   const ob=document.getElementById('morderbox');
   if(ob){{
     if(!ADDED && ESEC!==1 && ESEC!==2){{
       if(!ob.classList.contains('stepnow')){{ ob.classList.add('stepnow');
         try{{ ob.scrollIntoView({{behavior:'smooth',block:'center'}}); }}catch(e){{}} }}
     }} else {{ ob.classList.remove('stepnow'); }}
   }}
   const on=function(id){{ const e=document.getElementById(id);
     if(e) e.classList.add('pulseon'); }};
   if(ADDED){{ const pa=document.querySelector('#postadd .pacheckout');
     if(pa) pa.classList.add('pulseon'); return; }}
   if(ESEC===1){{
     // First task: their own words. The wording box blinks until they start
     // typing; moving on counts as keeping the shown quote.
     on(WORD_DONE?'esec1next':'mwordbox'); return; }}
   if(ESEC===2){{ on('esec2next'); return; }}
   const sv=((document.getElementById('msize')||{{}}).value)||'';
   if(!sv){{ const row=document.querySelector('#morderbox .orow');
     if(row) row.classList.add('pulseon');
     ['msize','mqty','sizeprompt'].forEach(function(id){{
       const s=document.getElementById(id); if(s) s.classList.add('attn'); }});
     return; }}
   if(!REVIEWED){{ on('mreviewbtn'); on('seefinalbtn'); return; }}
   on('maddbtn');
 }}
 function promptSizeQty(){{
   const p=document.getElementById('sizeprompt'); if(p)p.style.display='block';
   guide();
 }}
 function closeBasket(){{ const p=document.getElementById('basketPanel'); if(p)p.style.display='none'; }}
 function openBasketFromModal(){{ toggleBasket(); }}
 function pulseBasket(){{ const b=document.getElementById('basketBtnNav'); if(!b)return;
   b.classList.add('pulse'); setTimeout(()=>b.classList.remove('pulse'),1000); }}
 // Primary action: add the current personalized design to the basket.
 // Default quotes carry literal [Name]/[Your name] tokens - never let one
 // reach production unnoticed. Returns true when the wording is safe (or the
 // buyer explicitly confirms it as-is).
 function _placeholderOk(){{
   const w=((document.getElementById('mtext')||{{}}).value||'').trim()||CURQUOTE||'';
   if(!/\\[(your\\s+)?name\\]/i.test(w)) return true;
   return confirm('Your wording still contains "[Name]". Tap Cancel to type '+
     'the real name (recommended), or OK to print it exactly as shown.');
 }}
 function addToBasket(){{
   const sv=(document.getElementById('msize')||{{}}).value;
   if(!sv){{
     // Inline guidance instead of a browser alert: spotlight the size row.
     const p=document.getElementById('sizeprompt');
     if(p){{ p.style.display='block';
       p.innerHTML='⚠️ <b>Choose a size first</b> - then tap Add to basket'; }}
     promptSizeQty(); return;
   }}
   if(!_placeholderOk()) return;
   const before=CART.length; addToOrder();
   if(CART.length>before){{
     // Item added: the beacon moves to "Go to checkout" on the post-add bar.
     ADDED=true; REVIEWED=true; guide();
     const p=document.getElementById('sizeprompt'); if(p)p.style.display='none';
     pulseBasket();
     const bar=document.getElementById('mbasketbar');
     if(bar){{ bar.classList.add('added'); setTimeout(()=>bar.classList.remove('added'),1400); }}
   }}
 }}
 // ── Design state, Save, and final-proof Accept ──
 function _designState(){{
   return {{listing:(DATA[CUR]||{{}}).title||'', fmt:CURFMT, bg:SELBG, txt:SELTXT,
     font:SELFONT, wall:SELWALL, wording:_slotWording(),
     layout:((IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL)?CURLAYOUT:''), slots:((IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL)?JSON.parse(JSON.stringify(SLOTS)):null),
     size:((document.getElementById('msize')||{{}}).value||'').split('|')[0],
     tpos:TPOS, tsize:TSIZE, trot:TROT,
     cal:_calMeta(),
     photo:{{has:!!PHOTO, zoom:PHOTO_ZOOM, fx:PHOTO_FX, fy:PHOTO_FY}}}};
 }}
 function _toast(t){{ const n=document.getElementById('maicheck');
   if(n){{ n.innerHTML='💾 '+t; }} }}
 function saveDesign(){{
   const s=_designState();
   try{{localStorage.setItem('jf_design', JSON.stringify(s));}}catch(e){{}}
   const email=knownEmail();
   if(email && DESIGN_API){{
     fetch(DESIGN_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
       body:JSON.stringify({{email:email, design:s,
         summary:`${{s.fmt}} ${{s.size}} - "${{(s.wording||CURQUOTE).slice(0,60)}}"`}})}})
       .then(()=>_toast('Your design preferences are saved.'))
       .catch(()=>_toast('Saved on this device.'));
   }} else {{ _toast('Saved on this device. (Sign up to save to your order.)'); }}
 }}
 function _taxLine(sub){{
   if(EST_TAX_PCT>0){{ const tax=sub*EST_TAX_PCT/100;
     return `Subtotal: $${{sub.toFixed(2)}}\\nEst. tax (${{EST_TAX_PCT}}%): $${{tax.toFixed(2)}}*\\n`+
       `Est. total: $${{(sub+tax).toFixed(2)}}\\n(*Tax & shipping finalized at checkout)`;
   }}
   return `Subtotal: $${{sub.toFixed(2)}}\\n(Tax & shipping calculated at checkout)`;
 }}
 function _currentDesignSummary(){{
   const s=_designState();
   const price=parseFloat((((document.getElementById('msize')||{{}}).value||'').split('|')[1])||'0');
   const cal=s.cal?`12-month calendar · ${{s.cal.year}} · ${{s.cal.photos}}/12 monthly photos added\\n`:'';
   return `${{s.fmt}} ${{s.size}} - "${{(s.wording||CURQUOTE).slice(0,60)}}"\\n`+cal+_taxLine(price);
 }}
 function _basketSummary(){{
   if(!CART.length) return '(your basket is empty)';
   return CART.map((l,i)=>`${{i+1}}. ${{l.qty}}x ${{l.fmt}} ${{l.size}}`+
     (l.title?` - ${{l.title}}`:'')).join('\\n')+'\\n'+_taxLine(_cartTotal());
 }}
 let PROOFMODE='item';
 // Order-progress stepper: 1 Customize, 2 Review, 3 Approve, 4 Checkout.
 function setStep(n){{ document.querySelectorAll('#mstepper li').forEach(function(li){{
   const s=parseInt(li.dataset.s);
   li.classList.toggle('cur',s===n); li.classList.toggle('done',s<n);
   if(s===n) li.setAttribute('aria-current','step');
   else li.removeAttribute('aria-current'); }}); }}
 // Client-side upload cap (the server enforces the same limit).
 const MAX_UPLOAD_MB=25;
 // Photos already used in basket items (name|bytes) - powers the gentle
 // duplicate-upload heads-up without ever blocking an intentional reuse.
 let USED_PHOTOS=[], PHOTO_META=null;
 function dupPhotoNote(f){{ const k=f.name+'|'+f.size; PHOTO_META=k;
   return USED_PHOTOS.indexOf(k)>=0
     ? "<br>&#8505;&#65039; Heads up: this looks like the <b>same photo</b> used in another basket item - totally fine if intentional."
     : ""; }}
 // Proof image = the GARMENT photo (the #mgarment layer behind the transparent
 // canvas) WITH the design composited on top - so the proof shows the whole piece,
 // not just the wording on white. Falls back to the canvas alone for wall art (no
 // garment layer) or a cross-origin mockup that would taint the canvas.
 let _CLEAN=false;   // when true, drawArt omits the editor chrome (frame/handles)
 function _composedProofURL(){{
   const cv=document.getElementById('mcanvas'); if(!cv) return '';
   const mg=document.getElementById('mgarment');
   _SNAPPING=true;                       // internal redraws are a READ, not an edit
   _CLEAN=true; drawArt();               // redraw the design WITHOUT the editor chrome
   let url='';
   if(!mg || mg.style.display==='none' || !mg.complete || !mg.naturalWidth){{
     try{{ url=cv.toDataURL('image/png'); }}catch(e){{ url=''; }}
   }} else {{
     const tc=document.createElement('canvas'); tc.width=cv.width; tc.height=cv.height;
     const tx=tc.getContext('2d');
     tx.fillStyle='#ffffff'; tx.fillRect(0,0,tc.width,tc.height);
     // object-fit:contain mapping of the garment image into the canvas box
     const ir=mg.naturalWidth/mg.naturalHeight, cr=tc.width/tc.height;
     let dw,dh; if(ir>cr){{ dw=tc.width; dh=dw/ir; }} else {{ dh=tc.height; dw=dh*ir; }}
     tx.drawImage(mg,(tc.width-dw)/2,(tc.height-dh)/2,dw,dh);
     tx.drawImage(cv,0,0);               // the design (transparent canvas) on top
     try{{ url=tc.toDataURL('image/png'); }}
     catch(e){{ try{{ url=cv.toDataURL('image/png'); }}catch(e2){{ url=''; }} }}
   }}
   _CLEAN=false; drawArt();              // restore the editor view (chrome back)
   _SNAPPING=false;
   return url;
 }}
 // ── Final preview: rotate the garment front<->back so the buyer reviews BOTH
 // sides before approving. Reuses the editor's per-side designs (setPlacement
 // swaps in each side's own wording + photo) and recomposes the proof image.
 // Apparel only - wall art has a single face.
 function _syncProofFlip(){{
   var l=document.getElementById('proofFlipLbl');
   if(l) l.textContent=(APPLACEMENT==='back')?'See the front':'See the back';
 }}
 function _proofRenderSide(side){{
   if(!IS_APPAREL) return;
   setPlacement(side);                        // swap the editor to that side's design
   var img=document.getElementById('proofImg');
   var paint=function(){{ var du=_composedProofURL(); if(du&&img){{ img.src=du; }} }};
   paint();                                   // show now (blank back if photo still loading)
   if(PHOTO && PHOTO.src && !PHOTO.complete){{ // repaint once the side's photo arrives
     PHOTO.addEventListener('load',paint,{{once:true}});
     PHOTO.addEventListener('error',paint,{{once:true}}); }}
   _syncProofFlip();
 }}
 function proofFlip(){{ _proofRenderSide(APPLACEMENT==='back'?'front':'back'); }}
 // Drag the proof image sideways to spin it (mirrors the editor's garment spin).
 let _PROOFDRAG=null;
 function _proofDown(ev){{ if(!IS_APPAREL||PROOFMODE!=='item') return;
   var x=(ev.touches&&ev.touches[0])?ev.touches[0].clientX:ev.clientX;
   _PROOFDRAG={{last:x,acc:0}}; }}
 function _proofMove(ev){{ if(!_PROOFDRAG) return;
   var x=(ev.touches&&ev.touches[0])?ev.touches[0].clientX:ev.clientX;
   _PROOFDRAG.acc+=Math.abs(x-_PROOFDRAG.last); _PROOFDRAG.last=x;
   if(_PROOFDRAG.acc>55){{ proofFlip(); _PROOFDRAG=null; }} }}
 function _proofUp(){{ _PROOFDRAG=null; }}
 // ── Cross-department cross-sell ─────────────────────────────────────
 // At the final-design step, offer the SAME design on products from OTHER
 // departments ("make it a gift set"), carrying the wording across so the buyer
 // never retypes. The single biggest order-value lever in a multi-category shop.
 let CARRY_DESIGN='';
 function _applyCarry(){{
   if(!CARRY_DESIGN) return;
   var t=CARRY_DESIGN; CARRY_DESIGN='';
   try{{ if(typeof SLOTS!=='undefined') SLOTS.headline=t;
     var ta=document.getElementById('mtext'); if(ta) ta.value=t;
     if(typeof renderSlotInputs==='function') renderSlotInputs();
     drawArt(); }}catch(e){{}}
 }}
 function _xsFrom(formats,name){{
   var ps=(formats||[]).filter(function(f){{ return f.name===name||f.name.indexOf(name+' - ')===0; }})
     .map(function(f){{ return f.price; }}).filter(function(p){{ return p>0; }});
   return ps.length?Math.min.apply(null,ps):0;
 }}
 function _crossSellHTML(){{
   var cur = IS_MUG?'mug':IS_BRANDED?'branded':IS_CAL?'cal':IS_APPAREL?'apparel':'wall';
   var ALL=[
     {{kind:'mug',emoji:'🍵',label:'Mug',name:"Classic Ceramic Mug (11oz)",fmts:(typeof MUG_FORMATS!=='undefined'?MUG_FORMATS:[])}},
     {{kind:'branded',emoji:'🎁',label:'Tote',name:"Organic Cotton Tote Bag",fmts:(typeof BRANDED_FORMATS!=='undefined'?BRANDED_FORMATS:[])}},
     {{kind:'cal',emoji:'📅',label:'Calendar',name:"Wall Calendar",fmts:(typeof CAL_FORMATS!=='undefined'?CAL_FORMATS:[])}},
     {{kind:'apparel',emoji:'👕',label:'T-Shirt',name:"Men's T-Shirt",fmts:(typeof APPAREL_FORMATS!=='undefined'?APPAREL_FORMATS:[])}}
   ];
   var picks=ALL.filter(function(x){{ return x.kind!==cur && x.fmts.length; }}).slice(0,3);
   if(!picks.length) return '';
   var words=(typeof _slotWording==='function'?_slotWording():'')||'';
   var lead=words?`Put &ldquo;${{words.slice(0,36).replace(/</g,'')}}&rdquo; on more`:'Add this design to more';
   var btns=picks.map(function(x){{
     var p=_xsFrom(x.fmts,x.name);
     var color=(x.fmts[0]&&x.fmts[0].name.split(' - ')[1])||'White';
     return `<button type="button" class="xsbtn" onclick="crossSellTo('${{x.kind}}','${{x.name}}','${{color}}')">${{x.emoji}} ${{x.label}}${{p?` &middot; $${{p}}`:''}}</button>`;
   }}).join('');
   return `<div class="xshead">✨ Make it a gift set</div>`+
     `<div class="xssub">${{lead}} &mdash; same design, fresh ways to gift:</div>`+
     `<div class="xsrow">${{btns}}</div>`;
 }}
 function crossSellTo(kind,name,color){{
   CARRY_DESIGN=(typeof _slotWording==='function'?_slotWording():'')||((document.getElementById('mtext')||{{}}).value||'');
   closeProof();
   if(kind==='mug') shopMug(name,color);
   else if(kind==='branded') shopBranded(name,color);
   else if(kind==='cal') shopCalendar(name,color);
   else if(kind==='apparel') shopApparel(name,color);
 }}
 // ── Homepage gift sets & occasions ──────────────────────────────────
 // Occasion -> a sensible default product + a starter line. Opens that editor
 // pre-filled so the buyer starts from gift intent (the highest-converting entry).
 const OCCASIONS=[
   {{label:'Birthday', kind:'mug', name:"Classic Ceramic Mug (11oz)", color:'Navy', quote:'Happy Birthday [Name]!'}},
   {{label:'Anniversary', kind:'cal', name:"Wall Calendar", color:'White', quote:'Our Year Together'}},
   {{label:'For Mom', kind:'mug', name:"Accent Mug", color:'Dusty Rose', quote:'Best Mom Ever'}},
   {{label:'For Dad', kind:'mug', name:"Classic Ceramic Mug (11oz)", color:'Navy', quote:'Best Dad Ever'}},
   {{label:'Wedding', kind:'cal', name:"Wall Calendar", color:'White', quote:'Mr & Mrs [Name]'}},
   {{label:'New Baby', kind:'branded', name:"Organic Cotton Tote Bag", color:'Natural', quote:'Welcome Baby [Name]'}},
   {{label:'Graduation', kind:'apparel', name:"Men's T-Shirt", color:'White', quote:'Class of 2025'}},
   {{label:'Corporate', kind:'branded', name:"Organic Cotton Tote Bag", color:'Black', quote:'[Your Company]'}},
   {{label:'Memorial', kind:'mug', name:"Classic Ceramic Mug (11oz)", color:'White', quote:'In Loving Memory'}},
   {{label:'Just Because', kind:'branded', name:"Organic Cotton Tote Bag", color:'Sage', quote:'Just Because'}}
 ];
 // Curated cross-department sets. Combined from-price = sum of each item's from-price.
 const GIFTSETS=[
   {{key:'family', name:'Family Memory Set', items:[{{kind:'cal',name:"Wall Calendar",color:'White'}},{{kind:'mug',name:"Classic Ceramic Mug (11oz)",color:'Navy'}},{{kind:'branded',name:"Organic Cotton Tote Bag",color:'Natural'}}]}},
   {{key:'corporate', name:'Corporate Welcome Kit', items:[{{kind:'branded',name:"Organic Cotton Tote Bag",color:'Black'}},{{kind:'branded',name:"Insulated Stainless Water Bottle",color:'White'}},{{kind:'branded',name:"Hardcover Journal",color:'Black'}},{{kind:'mug',name:"Classic Ceramic Mug (11oz)",color:'White'}}]}},
   {{key:'newhome', name:'New Home Set', items:[{{kind:'mug',name:"Classic Ceramic Mug (11oz)",color:'Forest Green'}},{{kind:'branded',name:"Organic Cotton Tote Bag",color:'Sage'}},{{kind:'cal',name:"Wall Calendar",color:'White'}}]}},
   {{key:'celebration', name:'Celebration Set', items:[{{kind:'apparel',name:"Men's T-Shirt",color:'White'}},{{kind:'mug',name:"Classic Ceramic Mug (11oz)",color:'Red'}}]}}
 ];
 function _fmtFor(kind){{ return kind==='mug'?(typeof MUG_FORMATS!=='undefined'?MUG_FORMATS:[]):kind==='branded'?(typeof BRANDED_FORMATS!=='undefined'?BRANDED_FORMATS:[]):kind==='cal'?(typeof CAL_FORMATS!=='undefined'?CAL_FORMATS:[]):(typeof APPAREL_FORMATS!=='undefined'?APPAREL_FORMATS:[]); }}
 function _prodFrom(kind,name){{ var ps=_fmtFor(kind).filter(function(f){{return f.name===name||f.name.indexOf(name+' - ')===0;}}).map(function(f){{return f.price;}}).filter(function(p){{return p>0;}}); return ps.length?Math.min.apply(null,ps):0; }}
 function _openProduct(kind,name,color){{ if(kind==='mug')shopMug(name,color); else if(kind==='branded')shopBranded(name,color); else if(kind==='cal')shopCalendar(name,color); else shopApparel(name,color); }}
 function shopOccasion(i){{ var o=OCCASIONS[i]; if(!o)return; CARRY_DESIGN=o.quote; _openProduct(o.kind,o.name,o.color); }}
 function startGiftSet(i){{ var s=GIFTSETS[i]; if(!s||!s.items.length)return; var it=s.items[0]; _openProduct(it.kind,it.name,it.color); }}
 function renderGiftSets(){{
   var oc=document.getElementById('occrow');
   if(oc) oc.innerHTML=OCCASIONS.map(function(o,i){{ return `<button type="button" class="occchip" onclick="shopOccasion(${{i}})">${{o.label}}</button>`; }}).join('');
   var sg=document.getElementById('setgrid');
   if(sg) sg.innerHTML=GIFTSETS.map(function(s,i){{
     var from=s.items.reduce(function(t,it){{ return t+_prodFrom(it.kind,it.name); }},0);
     var items=s.items.map(function(it){{ return it.name.replace(/ \\(.*\\)/,''); }}).join(' + ');
     return `<div class="setcard"><div class="setname">${{s.name}}</div><div class="setitems">${{items}}</div>`+
       `<div class="setfrom">${{from?`from $${{from.toFixed(2)}}`:''}}</div>`+
       `<button type="button" class="setcta" onclick="startGiftSet(${{i}})">Build this set &rarr;</button></div>`;
   }}).join('');
 }}
 function showFinalProof(mode){{
   PROOFMODE=(mode==='final')?'final':'item';
   setStep(PROOFMODE==='final'?3:2);
   const cv=document.getElementById('mcanvas'), img=document.getElementById('proofImg');
   const title=document.getElementById('proofTitle'), sub=document.getElementById('proofSub');
   const acc=document.getElementById('proofAcceptBtn'), sum=document.getElementById('proofSummary');
   const st=document.getElementById('proofStatus'); if(st)st.textContent='';
   ACCEPTED=false;
   const edit=document.querySelector('#proofPop .pedit'); if(edit)edit.style.display='';
   if(acc){{ acc.disabled=false; acc.onclick=proofAccept; }}
   const _fl=document.getElementById('proofFlip');
   const _xc=document.getElementById('proofCross');
   if(PROOFMODE==='final'){{
     if(img)img.style.display='none';
     if(_fl)_fl.style.display='none';
     if(_xc)_xc.style.display='none';
     _loadContact(); finalStep(1);
   }} else {{
     REVIEWED=true; guide();              // review opened: that task is done
     if(cv&&img){{ const _du=IS_MUG?_mugMockupURL():_composedProofURL();  // mugs: wrap on a real mug
       if(_du){{ img.src=_du; img.style.display='block'; }} }}
     // Apparel: let the buyer spin the garment to review the BACK too before approving.
     if(_fl)_fl.style.display=IS_APPAREL?'flex':'none';
     if(img)img.classList.toggle('spinnable',IS_APPAREL);
     _syncProofFlip();
     if(title)title.textContent='Your final design';
     if(sub)sub.textContent="This is how your piece will look. Add it to your basket - you can edit it any time before checkout.";
     if(sum)sum.innerHTML=_currentDesignSummary().replace(/\\n/g,'<br>');
     if(acc)acc.textContent='✓ Add to basket';
     if(_xc){{ var _xh=_crossSellHTML(); _xc.innerHTML=_xh; _xc.style.display=_xh?'block':'none'; }}
   }}
   document.getElementById('proofPop').style.display='flex';
 }}
 // ── Final checkout wizard: 1 review basket -> 2 your details -> 3 confirm ──
 let FSTEP=1, CONTACT={{}};
 function _loadContact(){{
   try{{ CONTACT=JSON.parse(localStorage.getItem('jf_contact')||'{{}}'); }}
   catch(e){{ CONTACT={{}}; }}
   if(!CONTACT.email){{ const e=knownEmail(); if(e) CONTACT.email=e; }}
 }}
 function _saveContact(){{
   try{{ localStorage.setItem('jf_contact', JSON.stringify(CONTACT));
     if(CONTACT.email) localStorage.setItem('jf_email', CONTACT.email);
   }}catch(e){{}}
 }}
 function _fv(v){{ return (v||'').replace(/"/g,'&quot;'); }}
 function _trustStripHTML(){{
   // Reassurance at the highest-anxiety steps (address + pay): security, the
   // free-proof promise, and accepted payment methods. No supplier/marketplace name.
   return '<div class="trustband">'+
     '<span>🔒 Secure checkout - your card details never touch this site</span>'+
     '<span>💚 Free proof before we print</span>'+
     '<span class="paylogos">Card &middot; PayPal &middot; Apple&nbsp;Pay &middot; Google&nbsp;Pay</span>'+
     '</div>';
 }}
 function _contactFormHTML(){{ const c=CONTACT;
   return '<div class="fcform">'+
    '<label>Full name *<input id="fc_name" value="'+_fv(c.name)+'" autocomplete="name"></label>'+
    '<label>Email *<input id="fc_email" type="email" value="'+_fv(c.email)+'" autocomplete="email"></label>'+
    '<label>Phone <span class="fcopt">(optional - delivery questions only)</span><input id="fc_phone" value="'+_fv(c.phone)+'" autocomplete="tel"></label>'+
    '<label>Street address *<input id="fc_addr" value="'+_fv(c.addr)+'" autocomplete="street-address"></label>'+
    '<div class="fcrow">'+
    '<label>City *<input id="fc_city" value="'+_fv(c.city)+'" autocomplete="address-level2"></label>'+
    '<label>State/Region<input id="fc_state" value="'+_fv(c.state)+'" autocomplete="address-level1"></label>'+
    '<label>ZIP/Postcode *<input id="fc_zip" value="'+_fv(c.zip)+'" autocomplete="postal-code"></label>'+
    '</div>'+
    '<label>Country *<input id="fc_country" value="'+_fv(c.country||'United States')+'" autocomplete="country-name"></label>'+
    '<div id="fcerr" class="upbad" role="status" aria-live="polite"></div></div>';
 }}
 function _readContact(){{
   const g=function(id){{ return ((document.getElementById(id)||{{}}).value||'').trim(); }};
   CONTACT={{name:g('fc_name'), email:g('fc_email'), phone:g('fc_phone'),
     addr:g('fc_addr'), city:g('fc_city'), state:g('fc_state'),
     zip:g('fc_zip'), country:g('fc_country')}};
   const err=document.getElementById('fcerr');
   const need=[['name','full name'],['email','email address'],
     ['addr','street address'],['city','city'],['zip','ZIP/postcode'],
     ['country','country']];
   for(let i=0;i<need.length;i++){{
     if(!CONTACT[need[i][0]]){{ if(err)err.textContent='Please add your '+need[i][1]+'.'; return false; }}
   }}
   if(CONTACT.email.indexOf('@')<1){{ if(err)err.textContent='Please enter a valid email address.'; return false; }}
   _saveContact(); return true;
 }}
 function _shipToHTML(){{ const c=CONTACT;
   return c.name+'<br>'+c.addr+'<br>'+c.city+(c.state?', '+c.state:'')+' '+c.zip+
     '<br>'+c.country+'<br>'+c.email+(c.phone?' &middot; '+c.phone:'');
 }}
 function finalStep(n){{ FSTEP=n;
   const title=document.getElementById('proofTitle'), sub=document.getElementById('proofSub');
   const sum=document.getElementById('proofSummary'), acc=document.getElementById('proofAcceptBtn');
   const st=document.getElementById('proofStatus'); if(st)st.textContent='';
   if(n===1){{
     if(title)title.textContent='Step 1 of 3 - Review your basket ('+CART.length+')';
     if(sub)sub.textContent="Here's everything you picked. Remove anything you don't want (Edit), then continue.";
     if(sum)sum.innerHTML=_basketSummary().replace(/\\n/g,'<br>');
     if(acc){{ acc.textContent='Next: your details →'; acc.disabled=false;
       acc.onclick=function(){{ finalStep(2); }}; }}
   }} else if(n===2){{
     if(title)title.textContent='Step 2 of 3 - Your details';
     if(sub)sub.textContent='Shipping address verification and final confirmation.';
     if(sum)sum.innerHTML=_trustStripHTML()+_contactFormHTML()+
       '<div class="fcback" role="button" tabindex="0" onclick="finalStep(1)">&larr; Back to basket</div>';
     if(acc){{ acc.textContent='Next: confirm →'; acc.disabled=false;
       acc.onclick=function(){{ if(_readContact()) finalStep(3); }}; }}
   }} else {{
     if(title)title.textContent='Step 3 of 3 - Confirm & complete';
     if(sub)sub.textContent='Confirm your design below, then tap Complete order.';
     if(sum)sum.innerHTML=_trustStripHTML()+_basketSummary().replace(/\\n/g,'<br>')+
       '<div class="fcship"><b>Ship to</b><br>'+_shipToHTML()+'</div>'+
       _confirmChecklistHTML()+
       '<div class="fcback" role="button" tabindex="0" onclick="finalStep(2)">&larr; Edit details</div>';
     if(acc){{ acc.textContent='Complete order ✓';
       acc.onclick=acceptProof; }}
     _syncConfirmGate();
   }}
 }}
 // Final confirmation: the buyer actively verifies their photo, the wording,
 // and that it is made to order before Complete order unlocks. This is the
 // record that protects against "wrong text/photo" disputes - while transit
 // damage stays on us (free replacement).
 function _confirmChecklistHTML(){{
   var bx='display:block;margin:.45rem 0;font-size:.93rem;line-height:1.45;cursor:pointer;';
   return '<div style="margin:.8rem 0;padding:.85rem 1rem;border:1px solid #d9cdf2;'+
     'border-radius:12px;background:#faf8ff">'+
     '<div style="font-weight:700;margin-bottom:.5rem">Final approval - please check each box</div>'+
     '<label style="'+bx+'"><input type="checkbox" id="vchk_img" onchange="_syncConfirmGate()"> '+
       'My uploaded photo and frame choice are correct and good quality</label>'+
     '<label style="'+bx+'"><input type="checkbox" id="vchk_text" onchange="_syncConfirmGate()"> '+
       'The spelling &amp; wording are exactly how I want them</label>'+
     '<label style="'+bx+'"><input type="checkbox" id="vchk_made" onchange="_syncConfirmGate()"> '+
       'I approve this print exactly as shown and authorize it to proceed to production. '+
       'I understand it is made to order and final.</label>'+
     '<div style="margin-top:.55rem;font-size:.85rem;color:#5b3fa0">'+
       'Arrives damaged in transit? That is on us - we send a free replacement, '+
       'just message a photo within 7 days.</div></div>';
 }}
 function _syncConfirmGate(){{
   var a=document.getElementById('proofAcceptBtn');
   var ids=['vchk_img','vchk_text','vchk_made'];
   var ok=true;
   for(var i=0;i<ids.length;i++){{ var e=document.getElementById(ids[i]);
     if(!e||!e.checked){{ ok=false; }} }}
   if(a){{ a.disabled=!ok; a.style.opacity=ok?'':'0.5';
     a.style.cursor=ok?'':'not-allowed'; }}
   var st=document.getElementById('proofStatus');
   if(st)st.textContent=ok?'':'Please confirm all three boxes to complete your order.';
 }}
 function restartCheckout(){{
   // Undo the acceptance and walk back to Step 1 so the customer can change
   // anything (items, details) and approve again - nothing is lost.
   ACCEPTED=false; setStep(3);
   const edit=document.querySelector('#proofPop .pedit');
   if(edit) edit.style.display='';
   finalStep(1);
 }}
 function closeProof(){{ document.getElementById('proofPop').style.display='none';
   if(PROOFMODE!=='final') setStep(1); }}
 function proofEdit(){{ closeProof(); }}                 // back to the open design / basket
 function proofAccept(){{ if(PROOFMODE==='final') acceptProof(); else addFromProof(); }}
 function addFromProof(){{
   if(!_placeholderOk()) return;
   const before=CART.length; addToOrder(); closeProof(); pulseBasket();
   if(CART.length>before){{
     if(PHOTO&&PHOTO_META&&USED_PHOTOS.indexOf(PHOTO_META)<0) USED_PHOTOS.push(PHOTO_META);
     toggleBasket();    // open the basket so they see it landed
   }}
 }}
 let ACCEPTED=false;
 function acceptProof(){{
   if(ACCEPTED) return;            // guard against double-accept
   const email=(CONTACT&&CONTACT.email)||knownEmail();
   // Ship-to/contact rides with the summary AND inside the design payload so
   // the saved order record carries everything needed to fulfil it.
   const summary=_basketSummary()
     +(CONTACT&&CONTACT.name?('\\nShip to: '+CONTACT.name+', '+CONTACT.addr+', '
       +CONTACT.city+(CONTACT.state?', '+CONTACT.state:'')+' '+CONTACT.zip+', '
       +CONTACT.country+(CONTACT.phone?(' · '+CONTACT.phone):'')):'');
   const acc=document.getElementById('proofAcceptBtn');
   if(acc){{ acc.textContent='Confirming…'; acc.disabled=true; }}
   const done=function(emailed){{
     ACCEPTED=true; setStep(4); abConvert && abConvert();
     const st=document.getElementById('proofStatus');
     const edit=document.querySelector('#proofPop .pedit');
     if(edit) edit.style.display='none';
     let msg, label, action;
     if(emailed){{
       msg='✅ Accepted &amp; saved - <b>this is your final approval</b>. A '+
         'confirmation email is on its way.';
     }} else {{
       msg='✅ Accepted &amp; saved - <b>this is your final approval</b>.';
     }}
     if(PAY_LINK){{
       // Same-flow payment: hosted secure checkout opens on THIS click -
       // the customer never has to wait for an email to pay.
       label='Pay now - secure checkout →';
       action=function(){{ window.open(PAY_LINK,'_blank'); }};
       msg+=' <b>Tap below to pay now</b> on our secure checkout - card, '+
         'PayPal, Apple Pay or Google Pay. You never enter card details on '+
         'this site.'+
         '<div class="nextsteps"><b>What happens next</b><ol>'+
         '<li>Pay securely (the checkout opens when you tap below).</li>'+
         '<li>We print &amp; ship with tracking.</li></ol></div>';
     }} else if(CHECKOUT_URL){{ label='Continue to secure checkout →';
       action=function(){{ window.open(CHECKOUT_URL,'_blank'); }};
       msg+=' Tap below to pay via our secure checkout - card, PayPal, '+
         'Apple Pay or Google Pay. You never enter card details on this site.';
     }} else {{
       // No live shop yet (preview/UAT): never strand the customer on a bare
       // 'Done' - spell out the path to payment and capture their email.
       label='Got it ✓'; action=function(){{ closeProof(); }};
       const em=(CONTACT&&CONTACT.email)||knownEmail();
       msg+='<div class="nextsteps"><b>What happens next</b><ol>'+
         '<li>We send your <b>secure payment link</b> - card, PayPal, Apple Pay or Google Pay. You never enter card details on this site.</li>'+
         '<li>We print &amp; ship with tracking.</li></ol>'+
         // No backend reachable: give a channel that WORKS RIGHT NOW instead
         // of a promise this static preview can't keep.
         (CONFIRM_API?'':('<a class="esecnext ordmail" href="'+_orderMailto()+'">'+
           '📧 Email us your order now</a>'+
           '<div class="note">One tap opens an email with your full order - '+
           'send it and we take it from there.</div>'))+
         (em?`We\\'ll send your secure payment link to <b>${{em}}</b>.`
           :'<div class="pfemail"><label for="pfemail">Where should we send your secure payment link?</label> '+
            '<input id="pfemail" type="email" placeholder="you@email.com"> '+
            '<button type="button" onclick="saveProofEmail()">Save</button> '+
            '<span id="pfemailok" role="status" aria-live="polite"></span></div>')+
         '</div>';
     }}
     // Always offer a way back: changed your mind AFTER accepting? Start over.
     msg+='<div class="fcback" role="button" tabindex="0" onclick="restartCheckout()">'+
       '&#8617; Need to change something? Start over</div>';
     if(st) st.innerHTML=msg;
     if(acc){{ acc.textContent=label; acc.disabled=false; acc.onclick=action; }}
   }};
   if(email && CONFIRM_API){{
     const dsn=_designState(); dsn.contact=CONTACT;
     // Record the BASKET (total, item count, line items) so the order books
     // real revenue + a correct count - not sale_price=None / one flat row.
     dsn.cart={{ subtotal:+_cartTotal().toFixed(2),
       items:CART.reduce((s,l)=>s+(l.qty||1),0),
       lines:CART.map(l=>({{title:l.title||'',fmt:l.fmt,size:l.size,
         unit:l.unit,qty:l.qty}})) }};
     fetch(CONFIRM_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
       body:JSON.stringify({{email:email, summary:summary, design:dsn,
         design_id:'cart-'+Date.now(), proof:_composedProofURL()}})}})
       .then(r=>r.json()).then(d=>done(d&&d.ok)).catch(()=>done(false));
   }} else {{ done(false); }}
 }}
 // Prefilled order email to the owner - the always-works completion channel.
 function _orderMailto(){{
   const c=CONTACT||{{}};
   const body=_basketSummary()
     +'\\n\\nShip to: '+[c.name,c.addr,c.city,c.state,c.zip,c.country].filter(Boolean).join(', ')
     +(c.phone?'\\nPhone: '+c.phone:'')+(c.email?'\\nEmail: '+c.email:'');
   return 'mailto:'+OWNER+'?subject='+encodeURIComponent('New order - '+(c.name||'website'))
     +'&body='+encodeURIComponent(body);
 }}
 // Save the proof/payment-link email captured on the 'What happens next' panel.
 function saveProofEmail(){{
   const i=document.getElementById('pfemail'), ok=document.getElementById('pfemailok');
   const v=((i&&i.value)||'').trim();
   if(v.indexOf('@')<1){{ if(ok)ok.textContent='Please enter a valid email.'; return; }}
   try{{ localStorage.setItem('jf_email', v); }}catch(e){{}}
   if(CONFIRM_API){{
     fetch(CONFIRM_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
       body:JSON.stringify({{email:v, summary:_basketSummary(), design:_designState()}})}})
       .catch(function(){{}});
   }}
   if(ok)ok.textContent=CONFIRM_API
     ?'✓ Saved - watch your inbox for the proof.'
     :'✓ Saved on this device - please also tap "Email us your order now" above so we receive it.';
 }}
 let PHOTO=null, PHOTO_ZOOM=1, PHOTO_FX=0.5, PHOTO_FY=0.5, PHOTO_RECT=null;
 function _showPhotoCtl(on){{
   var c=document.getElementById('mphotoctl'); if(c)c.style.display=on?'block':'none';
 }}
 // Apparel can SHRINK the photo (size 0.2x); wall art fills the frame (min 1x).
 function setPhotoZoom(v){{
   const lo=(typeof IS_APPAREL!=='undefined' && (IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL))?0.2:1;
   PHOTO_ZOOM=Math.max(lo, parseFloat(v)||1); drawArt(); }}
 function nudgePhoto(dx,dy){{ PHOTO_FX=Math.min(1,Math.max(0,PHOTO_FX+dx));
   PHOTO_FY=Math.min(1,Math.max(0,PHOTO_FY+dy)); drawArt(); }}
 function resetPhoto(){{ PHOTO_ZOOM=1; PHOTO_FX=0.5; PHOTO_FY=0.5;
   var z=document.getElementById('mphotozoom'); if(z)z.value=1; drawArt(); }}
 function applyFocal(f){{ if(!f) return;
   if(typeof f.x==='number') PHOTO_FX=Math.min(1,Math.max(0,f.x));
   if(typeof f.y==='number') PHOTO_FY=Math.min(1,Math.max(0,f.y)); drawArt();
   var n=document.getElementById('maicheck');
   if(n && f.source==='ai') n.innerHTML+=" <span style='color:#0a6b3b'>· subject auto-centered</span>";
 }}
 // Client fallback auto-center (no server): center the photo; AI refines via /upload.
 function autoCenterPhoto(){{ PHOTO_FX=0.5; PHOTO_FY=0.5; drawArt(); }}
 function removePhoto(){{
   if(PHOTO&&PHOTO.src&&PHOTO.src.indexOf('blob:')===0) URL.revokeObjectURL(PHOTO.src);
   PHOTO=null; PHOTO_ZOOM=1; PHOTO_FX=0.5; PHOTO_FY=0.5;
   const inp=document.getElementById('mupload'); if(inp)inp.value='';
   const msg=document.getElementById('muploadmsg'); if(msg){{msg.className='note';msg.textContent='';}}
   setDragMode('text'); _showPhotoCtl(false); drawArt();
 }}
 function checkUpload(){{const inp=document.getElementById('mupload'),msg=document.getElementById('muploadmsg');
   const f=inp.files&&inp.files[0]; if(!f){{removePhoto();return;}}
   if(!/(jpe?g|png|pdf|tiff?)$/i.test(f.name)){{msg.className='note upbad';
     msg.textContent='Unsupported format. Use JPG, PNG, PDF or TIFF.';return;}}
   if(f.size>MAX_UPLOAD_MB*1048576){{msg.className='note upbad';
     msg.textContent='That file is '+(f.size/1048576).toFixed(1)+' MB - too large (max '
       +MAX_UPLOAD_MB+' MB). Tip: export the photo as a JPG and try again.';
     inp.value='';return;}}
   if(/pdf$/i.test(f.name)){{PHOTO=null;drawArt();
     msg.className='note upok';msg.innerHTML="PDF received - we'll verify print quality. "
       +"<span class='rmphoto' onclick='removePhoto()'>remove</span>";aiCheckPhoto(f);return;}}
   const inches=((document.getElementById('msize')||{{}}).value||'18x24|0').split('|')[0].split('x').map(parseFloat);
   // Only wall-art sizes are an inch pair (e.g. 18x24). Mug/apparel/calendar/branded
   // sizes are '11oz'/'M'/'A4'/'One size' - never print a bogus "11xundefined" size.
   const isInch=(inches.length>=2 && isFinite(inches[0]) && isFinite(inches[1]));
   const img=new Image();
   img.onload=function(){{const nw=isInch?inches[0]*150:1500, nh=isInch?inches[1]*150:1500;
     const big=Math.max(img.width,img.height), small=Math.min(img.width,img.height);
     const rm=" <span class='rmphoto' onclick='removePhoto()'>remove</span>";
     const dup=dupPhotoNote(f);
     const forSz=isInch?(' for '+inches[0]+'x'+inches[1]+'"'):'';
     const okRes=isInch?(big>=Math.max(nw,nh)&&small>=Math.min(nw,nh)):(big>=1500);
     renderPhotoReview(msg, img.width, img.height);   // 🤖 AI Smart photo review card
     if(dup){{ msg.innerHTML+=dup; }}
     PHOTO=img; PHOTO_ZOOM=1; PHOTO_FX=0.5; PHOTO_FY=0.5;
     var z=document.getElementById('mphotozoom'); if(z)z.value=1;
     setDragMode('photo');                    // dragging now moves the PHOTO
     _showPhotoCtl(true); drawArt(); aiCheckPhoto(f);
     // Photo landed: make Next explicit (the guidance engine keeps it
     // blinking until the customer actually moves on).
     const nx=document.getElementById('esec2next');
     if(nx) nx.innerHTML='Photo added ✓ - Next: '
       +(IS_APPAREL?'garment':'frame')+' &amp; size →';
     guide(); }};
   img.onerror=function(){{PHOTO=null;msg.className='note upbad';msg.textContent='Could not read image - try another file.';}};
   img.src=URL.createObjectURL(f);}}
 let SELBG=BGCOLORS[0], SELTXT=TXTCOLORS[0], SELFONT=FONTS[0][1], CURQUOTE="";
 let TXT_USER_SET=false;   // true once the buyer picks a text colour (stops auto-contrast)
 let APPLACEMENT='front';  // which side is being designed: front | back
 // Layout Studio: the selected preset layout + structured text slots. 'freeform'
 // keeps today's single-text-block behaviour; any other key auto-arranges the
 // logo + the slots below into a professional composition (see LAYOUTS).
 let CURLAYOUT='freeform';
 let SLOTS={{headline:'',secondary:'',arcTop:'',arcBottom:'',tagline:'',monogram:''}};
 function _slot(k){{ return (SLOTS&&SLOTS[k])||''; }}
 function _emptySlots(){{ return {{headline:'',secondary:'',arcTop:'',arcBottom:'',tagline:'',monogram:''}}; }}
 function _slotsFilled(sl){{ if(!sl) return false; for(var k in sl) if((sl[k]||'').trim()) return true; return false; }}
 // Photo Collage: up to 4 uploaded photos (Image objects) filling the 2x2 grid.
 let COLLAGE=[null,null,null,null];
 function _collageFilled(){{ return COLLAGE.some(function(im){{ return !!im; }}); }}
 function collageUpload(i, inp){{
   var f=inp.files&&inp.files[0]; if(!f) return;
   if(!/(jpe?g|png)$/i.test(f.name)){{ toast('Use a JPG or PNG photo.'); inp.value=''; return; }}
   if(f.size>MAX_UPLOAD_MB*1048576){{ toast('That photo is too large (max '+MAX_UPLOAD_MB+' MB).'); inp.value=''; return; }}
   var r=new FileReader();
   r.onload=function(e){{ var img=new Image();
     img.onload=function(){{ COLLAGE[i]=img; drawArt(); }}; img.src=e.target.result; }};
   r.readAsDataURL(f);
 }}
 // Readable wording from the active layout's slots (for the summary + the order).
 function _slotWording(){{
   if(CURLAYOUT==='freeform') return ((document.getElementById('mtext')||{{}}).value||'');
   var L=_layout(CURLAYOUT), seen={{}}, out=[];
   (L.slots||[]).forEach(function(s){{ var v=_slot(s.slot);
     if(v && !seen[s.slot]){{ seen[s.slot]=1; out.push(v); }} }});
   return out.join(' / ');
 }}
 let LOGO_ON=false;        // optional shop-logo overlay on front & back
 // Apparel DESIGN FRAME the buyer can move + resize anywhere on the garment: the
 // dashed print area. centre (x,y as a fraction of the canvas) + scale.
 let BOX={{x:0.50,y:0.35,s:1.0}};
 function _clampBox(){{ BOX.x=Math.min(0.84,Math.max(0.16,BOX.x));
   BOX.y=Math.min(0.62,Math.max(0.18,BOX.y)); BOX.s=Math.min(1.7,Math.max(0.45,BOX.s)); }}
 function setFrameSize(v){{ BOX.s=parseFloat(v)||1; _clampBox(); drawArt(); }}
 function moveFrame(dx,dy){{ BOX.x+=dx; BOX.y+=dy; _clampBox(); drawArt(); }}
 function resetFrame(){{ BOX={{x:0.50,y:0.35,s:1.0}};
   var s=document.getElementById('mframesize'); if(s)s.value=1; drawArt(); }}
 const _PLACE_LBL={{front:'Front',back:'Back'}};
 // Front and back hold INDEPENDENT designs (different wording + photo + frame).
 // Snapshot the current side before flipping, then restore the other side's design.
 let SIDES={{front:null,back:null}};
 function _captureSide(){{
   const ta=document.getElementById('mtext');
   return {{ quote:(ta?ta.value:'')||'', cq:CURQUOTE, photoSrc:(PHOTO&&PHOTO.src)?PHOTO.src:'',
     pz:PHOTO_ZOOM, pfx:PHOTO_FX, pfy:PHOTO_FY, tpos:{{x:TPOS.x,y:TPOS.y}},
     tsize:TSIZE, trot:TROT, box:{{x:BOX.x,y:BOX.y,s:BOX.s}}, font:SELFONT, txt:SELTXT,
     layout:CURLAYOUT, slots:JSON.parse(JSON.stringify(SLOTS)),
     loff:JSON.parse(JSON.stringify(LOFF)),
     collage:COLLAGE.map(function(im){{ return (im&&im.src)||''; }}) }};
 }}
 function _restoreSide(s){{
   const ta=document.getElementById('mtext');
   if(s){{
     if(ta) ta.value=s.quote||''; CURQUOTE=s.cq||'';
     PHOTO_ZOOM=s.pz; PHOTO_FX=s.pfx; PHOTO_FY=s.pfy;
     TPOS={{x:s.tpos.x,y:s.tpos.y}}; TSIZE=s.tsize; TROT=s.trot;
     BOX={{x:s.box.x,y:s.box.y,s:s.box.s}};
     if(s.font) SELFONT=s.font; if(s.txt) SELTXT=s.txt;
     CURLAYOUT=s.layout||'freeform'; SLOTS=s.slots?JSON.parse(JSON.stringify(s.slots)):_emptySlots();
     LOFF=s.loff?JSON.parse(JSON.stringify(s.loff)):{{}};
     COLLAGE=(s.collage||[]).map(function(src){{ if(!src) return null;
       var ci=new Image(); ci.onload=function(){{drawArt();}}; ci.src=src; return ci; }});
     while(COLLAGE.length<4) COLLAGE.push(null);
     if(s.photoSrc){{ var im=new Image(); im.onload=function(){{drawArt();}}; im.src=s.photoSrc;
       PHOTO=im; _showPhotoCtl(true); }}
     else {{ PHOTO=null; _showPhotoCtl(false); }}
   }} else {{                                    // a fresh, empty side
     if(ta) ta.value=''; CURQUOTE='';
     PHOTO=null; PHOTO_ZOOM=1; PHOTO_FX=0.5; PHOTO_FY=0.5;
     TPOS={{x:0.5,y:0.5}}; TSIZE=0; TROT=0; BOX={{x:0.50,y:0.35,s:1.0}}; _showPhotoCtl(false);
     CURLAYOUT='freeform'; SLOTS=_emptySlots(); COLLAGE=[null,null,null,null]; LOFF={{}};
   }}
   const _sync=function(id,v){{ var e=document.getElementById(id); if(e) e.value=v; }};
   _sync('mphotozoom',PHOTO_ZOOM); _sync('mframesize',BOX.s); _sync('mtsize',TSIZE); _sync('mtrot',TROT);
   var cc=document.getElementById('mcc'); if(cc&&ta) cc.textContent=ta.value.length+' / '+MAXCHARS;
   renderLayoutGallery(); renderSlotInputs();   // reflect the restored side's layout
 }}
 function setPlacement(p){{
   if(p!=='back') p='front';
   const prev=APPLACEMENT;
   if(IS_APPAREL && p!==prev) SIDES[prev]=_captureSide();   // save the side we're leaving
   APPLACEMENT=p;
   document.querySelectorAll('#mplacement .plbtn').forEach(function(b){{
     b.classList.toggle('sel', b.dataset.p===p); }});
   const _bh=document.getElementById('mbackhint');
   if(_bh) _bh.style.display=(p==='back')?'block':'none';
   if(IS_APPAREL && p!==prev) _restoreSide(SIDES[p]);       // load the side we moved to
   drawArt();
 }}
 // Toggle the shop-logo overlay (added to BOTH the front and the back).
 function toggleLogo(){{
   const cb=document.getElementById('mlogo');
   LOGO_ON=!!(cb&&cb.checked);
   drawArt();
 }}
 // Print-safe boundary = the movable design FRAME (front or back). Silhouette mode
 // is relative to the garment box; mockup mode is relative to the whole canvas.
 function _placeBound(x,y,w,h){{
   return {{x:x+w*0.22,y:y+h*0.22,w:w*0.56,h:h*0.50}};   // front + back (generous)
 }}
 function _placeBoundMock(W,H){{
   // Front/back: the design FRAME the buyer can move + resize. Base size 0.42x0.32
   // of the canvas x BOX.s, centred at (BOX.x,BOX.y), then clamped so the frame
   // stays on the garment's torso (never onto the collar or the lower body).
   const bw=W*0.42*BOX.s, bh=H*0.32*BOX.s;
   let bx=W*BOX.x-bw/2, by=H*BOX.y-bh/2;
   bx=Math.min(Math.max(bx,W*0.06),W*0.94-bw);
   by=Math.min(Math.max(by,H*0.07),H*0.66-bh);
   return {{x:bx,y:by,w:bw,h:bh}};
 }}
 // Draggable text (position fractions) + manual size (0=auto) + rotation + drag mode.
 let TPOS={{x:0.5, y:0.5}}, TSIZE=0, TROT=0, ART={{x:0,y:0,w:1,h:1}}, DRAGMODE='text';
 // Per-element nudge offsets for a LAYOUT (badge/emblem): {{slotName:{{dx,dy}}}} in box
 // fractions, so the buyer can drag each word off its template spot. Reset per layout.
 let LOFF={{}};
 function _loff(k){{ return LOFF[k]||{{dx:0,dy:0}}; }}
 function setTextRot(v){{ TROT=parseInt(v)||0;
   const lbl=document.getElementById('mtrotlbl'); if(lbl)lbl.textContent=TROT+'°'; drawArt(); }}
 function setRot(deg){{ const s=document.getElementById('mtrot'); if(s)s.value=deg; setTextRot(deg); }}
 function setDragMode(m){{ DRAGMODE=m;
   document.querySelectorAll('.dmbtn').forEach(b=>b.classList.toggle('sel',b.dataset.m===m)); }}
 // Explicit MOVE controls for the wording (besides dragging it on the preview), so
 // placement is obvious and works on any device.
 function nudgeText(dx,dy){{ TPOS.x=_clamp(TPOS.x+dx,0.04,0.96);
   TPOS.y=_clamp(TPOS.y+dy,0.04,0.96); drawArt(); }}
 function centerText(){{ TPOS.x=0.5; TPOS.y=0.5; drawArt(); }}
 function setTextSize(v){{ TSIZE=parseInt(v)||0;
   const lbl=document.getElementById('mtsizelbl');
   if(lbl) lbl.textContent = TSIZE===0 ? 'Auto' : TSIZE+'%'; drawArt(); }}
 function resetTextPos(){{ TPOS={{x:0.5,y:0.5}}; TSIZE=0;
   const s=document.getElementById('mtsize'); if(s)s.value=0; setTextSize(0); }}
 // Drag the wording anywhere on the art.
 function _canvasPt(ev){{
   const cv=document.getElementById('mcanvas'); const r=cv.getBoundingClientRect();
   const t=(ev.touches&&ev.touches[0])||ev;
   return {{x:(t.clientX-r.left)*(cv.width/r.width),
            y:(t.clientY-r.top)*(cv.height/r.height)}};
 }}
 let DRAGGING=false, DRAGLAST=null, DRAGPX=null, ROT_ACC=0;
 function _frac(ev){{ const p=_canvasPt(ev);
   return {{x:(p.x-ART.x)/ART.w, y:(p.y-ART.y)/ART.h}}; }}
 function _clamp(v,a,b){{ return Math.min(b,Math.max(a,v)); }}
 let DRAGTARGET='text';   // what THIS gesture moves (decided at pointer-down)
 // Spin the garment between its front and back (it only has those two real views).
 function _flipSide(){{ setPlacement(APPLACEMENT==='back'?'front':'back'); }}
 // Apparel: decide by WHERE you grab - a corner handle resizes, the wording/photo
 // moves that element, INSIDE the frame moves the frame, OUTSIDE it (on the bare
 // garment) spins the shirt front<->back.
 function _hitTarget(px){{
   const b=APPAREL_BOUND, near=function(hx,hy){{ return Math.abs(px.x-hx)<26 && Math.abs(px.y-hy)<26; }};
   if(PHOTO && PHOTO_RECT && near(PHOTO_RECT.x+PHOTO_RECT.w, PHOTO_RECT.y+PHOTO_RECT.h)) return 'photoresize';
   if(b && near(b.x, b.y+b.h)) return 'resize';
   if(b && (px.x<b.x-8 || px.x>b.x+b.w+8 || px.y<b.y-8 || px.y>b.y+b.h+8)) return 'rotate';
   const fx=(px.x-ART.x)/ART.w, fy=(px.y-ART.y)/ART.h;
   const typed=((document.getElementById('mtext')||{{}}).value||'').trim();
   if((typed||CURQUOTE) && Math.abs(fx-TPOS.x)<0.24 && Math.abs(fy-TPOS.y)<0.17) return 'text';
   if(PHOTO && PHOTO_RECT && px.x>=PHOTO_RECT.x && px.x<=PHOTO_RECT.x+PHOTO_RECT.w
      && px.y>=PHOTO_RECT.y && px.y<=PHOTO_RECT.y+PHOTO_RECT.h) return 'photo';
   // Layout mode: grabbing near a wording slot moves THAT element (per-element nudge).
   if(CURLAYOUT && CURLAYOUT!=='freeform' && b){{
     var L=_layout(CURLAYOUT), R=Math.min(b.w,b.h), ss=(L&&L.slots)||[];
     for(var i=0;i<ss.length;i++){{ var s=ss[i]; if(!_slot(s.slot)) continue;
       var o=_loff(s.slot);
       var hx=b.x+b.w*((s.kind==='arc'?s.cx:(s.x==null?0.5:s.x))+o.dx);
       var hy=b.y+b.h*((s.kind==='arc'?s.cy:s.y)+o.dy);
       if(s.kind==='arc'){{ var ang=((s.midAngle||0))*Math.PI/180;   // text sits on the radius
         hx+=R*(s.r||0.5)*Math.cos(ang); hy+=R*(s.r||0.5)*Math.sin(ang); }}
       if(Math.abs(px.x-hx)<R*0.30 && Math.abs(px.y-hy)<R*0.16) return 'slot:'+s.slot;
     }}
   }}
   return 'frame';
 }}
 function _startDrag(ev){{ DRAGGING=true; DRAGPX=_canvasPt(ev); DRAGLAST=_frac(ev);
   if(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL){{ DRAGTARGET=_hitTarget(DRAGPX);
     // Branded has no front/back to spin - grabbing outside just moves the frame.
     if((IS_BRANDED||IS_MUG) && DRAGTARGET==='rotate') DRAGTARGET='frame'; }}
   else {{
     // wall art: smart-grab the wording, else follow the Photo toggle (pan).
     const nearText = Math.abs(DRAGLAST.x-TPOS.x)<0.22 && Math.abs(DRAGLAST.y-TPOS.y)<0.16;
     DRAGTARGET = (DRAGMODE==='photo' && PHOTO && !nearText) ? 'photo' : 'text';
     if(DRAGTARGET==='text'){{ TPOS.x=_clamp(DRAGLAST.x,0.04,0.96);
       TPOS.y=_clamp(DRAGLAST.y,0.04,0.96); drawArt(); }}
   }}
   ev.preventDefault&&ev.preventDefault(); }}
 function _moveDrag(ev){{ if(!DRAGGING) return;
   const px=_canvasPt(ev), f=_frac(ev);
   const cv=document.getElementById('mcanvas'), W=cv.width, H=cv.height;
   if(DRAGTARGET==='rotate'){{                                  // spin the garment front<->back
     if(DRAGPX){{ ROT_ACC+=(px.x-DRAGPX.x);
       if(Math.abs(ROT_ACC)>60){{ _flipSide(); ROT_ACC=0; }} }}
     DRAGPX=px; ev.preventDefault&&ev.preventDefault(); return;
   }} else if(DRAGTARGET==='frame'){{                            // drag the whole design
     if(DRAGPX){{ BOX.x+=(px.x-DRAGPX.x)/W; BOX.y+=(px.y-DRAGPX.y)/H; _clampBox(); }}
   }} else if(DRAGTARGET==='resize'){{                           // drag the corner to resize the FRAME
     const cx=BOX.x*W, cy=BOX.y*H;
     BOX.s=Math.max(2*Math.abs(px.x-cx)/(0.42*W), 2*Math.abs(px.y-cy)/(0.32*H));
     _clampBox();
   }} else if(DRAGTARGET==='photoresize'){{                       // drag the corner to resize the PHOTO
     if(PHOTO_RECT && PHOTO_RECT.w>2 && PHOTO_RECT.h>2){{
       const pcx=PHOTO_RECT.x+PHOTO_RECT.w/2, pcy=PHOTO_RECT.y+PHOTO_RECT.h/2;
       const r=Math.max(Math.abs(px.x-pcx)/(PHOTO_RECT.w/2), Math.abs(px.y-pcy)/(PHOTO_RECT.h/2));
       PHOTO_ZOOM=Math.max(0.2, Math.min(3, PHOTO_ZOOM*r));
       const z=document.getElementById('mphotozoom'); if(z) z.value=PHOTO_ZOOM;
     }}
   }} else if(DRAGTARGET && DRAGTARGET.indexOf('slot:')===0){{    // nudge ONE layout element
     var k=DRAGTARGET.slice(5), bb=APPAREL_BOUND;
     if(DRAGLAST && bb){{ var o=_loff(k);
       o.dx=_clamp((o.dx||0)+(f.x-DRAGLAST.x)*W/Math.max(1,bb.w),-0.6,0.6);
       o.dy=_clamp((o.dy||0)+(f.y-DRAGLAST.y)*H/Math.max(1,bb.h),-0.6,0.6);
       LOFF[k]=o; }}
   }} else if(DRAGTARGET==='photo'){{
     if(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL){{ PHOTO_FX=_clamp(f.x,0,1); PHOTO_FY=_clamp(f.y,0,1); }}
     else if(DRAGLAST){{ PHOTO_FX=_clamp(PHOTO_FX-(f.x-DRAGLAST.x),0,1);
       PHOTO_FY=_clamp(PHOTO_FY-(f.y-DRAGLAST.y),0,1); }}
   }} else {{                                                    // move the wording
     TPOS.x=_clamp(f.x,0.04,0.96); TPOS.y=_clamp(f.y,0.04,0.96);
   }}
   DRAGLAST=f; DRAGPX=px; drawArt(); ev.preventDefault&&ev.preventDefault();
 }}
 function _endDrag(){{ DRAGGING=false; DRAGLAST=null; DRAGPX=null; ROT_ACC=0; }}
 function initTextDrag(){{
   const cv=document.getElementById('mcanvas'); if(!cv||cv.dataset.drag) return;
   cv.dataset.drag='1'; cv.style.cursor='move';
   cv.addEventListener('mousedown',_startDrag); cv.addEventListener('mousemove',_moveDrag);
   window.addEventListener('mouseup',_endDrag);
   cv.addEventListener('touchstart',_startDrag,{{passive:false}});
   cv.addEventListener('touchmove',_moveDrag,{{passive:false}});
   window.addEventListener('touchend',_endDrag);
 }}
 function renderFonts(){{
   document.getElementById('mfonts').innerHTML = FONTS.map((f,k)=>
     `<span class="fchip ${{f[1]===SELFONT?'sel':''}}" tabindex="0" role="button" aria-label="${{f[0]}} font" style="font-family:${{f[1]}}" onclick="pickFont(${{k}})">${{f[0]}}</span>`).join('');
 }}
 function pickFont(k){{ SELFONT=FONTS[k][1];
   document.querySelectorAll('#mfonts .fchip').forEach((e,m)=>e.classList.toggle('sel',m===k)); drawArt(); }}
 function onText(){{
   const v=(document.getElementById('mtext').value||'');
   document.getElementById('mcc').textContent = v.length + ' / ' + MAXCHARS;
   if(!WORD_DONE && v.trim()){{ WORD_DONE=true; guide(); }}  // typing started
   drawArt();
 }}
 function onSizeChange(){{ drawArt(); updateReview(); recheckPhotoRes();
   // Size picked: clear any "choose a size first" warning back to the default,
   // and move the guidance blink along to the next task (review).
   const p=document.getElementById('sizeprompt');
   if(p) p.innerHTML='👇 Pick your <b>size</b> &amp; <b>quantity</b>, then tap <b>Add to basket</b>';
   guide();
 }}
 // Re-check the uploaded photo's resolution against the CURRENTLY selected size.
 function recheckPhotoRes(){{
   const msg=document.getElementById('muploadmsg');
   if(!PHOTO || !PHOTO.naturalWidth || !msg) return;
   const inch=((document.getElementById('msize')||{{}}).value||'18x24|0').split('|')[0]
     .split('x').map(parseFloat);
   const isInch=(inch.length>=2 && isFinite(inch[0]) && isFinite(inch[1]));
   const nw=isInch?inch[0]*150:1500, nh=isInch?inch[1]*150:1500;
   const big=Math.max(PHOTO.naturalWidth,PHOTO.naturalHeight),
         small=Math.min(PHOTO.naturalWidth,PHOTO.naturalHeight);
   const rm=" <span class='rmphoto' onclick='removePhoto()'>remove</span>";
   const forSz=isInch?(' for '+inch[0]+'x'+inch[1]+'"'):'';
   const okRes=isInch?(big>=Math.max(nw,nh)&&small>=Math.min(nw,nh)):(big>=1500);
   if(okRes){{ msg.className='note upok';
     msg.innerHTML='Great - '+PHOTO.naturalWidth+'x'+PHOTO.naturalHeight+'px works'+forSz+'.'+rm; }}
   else {{ msg.className='note upbad';
     msg.innerHTML='Only '+PHOTO.naturalWidth+'x'+PHOTO.naturalHeight+'px - a bit low for a sharp'+forSz+' print. Try a larger size or a higher-res photo.'+rm; }}
 }}
 function renderBg(){{
   const box=document.getElementById('mbg'); if(!box) return;
   if(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL){{   // Step-1 row = product/garment colour swatches
     var fmts=IS_CAL?calFormatsFor():(IS_MUG?mugFormatsFor():(IS_BRANDED?brandedFormatsFor():apparelFormatsFor()));
     box.innerHTML=fmts.map(function(f){{
       var cn=(f.name.split(' - ')[1]||'');
       var hex=(typeof APPARELCOLOR!=='undefined'&&APPARELCOLOR[cn])||'#bbb';
       var ring=(cn==='White'||cn==='Sand'||cn==='Heather Grey'||cn==='Light Blue')
         ?'box-shadow:inset 0 0 0 1px #cfcabb':'';
       return `<span style="background:${{hex}};${{ring}}" class="${{CURFMT===f.name?'sel':''}}" onclick="pickShirt('${{cn}}',this)" title="${{cn}}"></span>`;
     }}).join('');
   }} else {{
     box.innerHTML = BGCOLORS.map((c,k)=>
       `<span style="background:${{c}}" class="${{c===SELBG?'sel':''}}" onclick="pickBg('${{c}}',this)" title="${{c}}"></span>`).join('');
   }}
 }}
 function renderTxt(){{
   document.getElementById('mtxt').innerHTML = TXTCOLORS.map((c,k)=>
     `<span style="background:${{c}}" class="${{c===SELTXT?'sel':''}}" onclick="pickTxt('${{c}}',this)" title="${{c}}"></span>`).join('');
 }}
 // AI Room Designer: preview the framed art against the customer's wall color
 const WALLS = [["#ece7dd","Warm white"],["#d9d2c4","Greige"],["#cfd6d2","Sage"],
   ["#c3cdd6","Soft blue"],["#e3d3cb","Blush"],["#3a3f3b","Charcoal"],
   ["#2b3a30","Forest"],["#1f2733","Navy"]];
 let SELWALL = WALLS[0][0];
 function renderWall(){{
   const el=document.getElementById('mwall'); if(!el)return;
   el.innerHTML = WALLS.map(w=>
     `<span style="background:${{w[0]}}" class="${{w[0]===SELWALL?'sel':''}}" onclick="pickWall('${{w[0]}}',this)" title="${{w[1]}}"></span>`).join('');
 }}
 function pickWall(c,el){{ SELWALL=c;
   document.querySelectorAll('#mwall span').forEach(e=>e.classList.toggle('sel',e===el)); drawArt(); }}
 function pickBg(c,el){{ SELBG=c;
   document.querySelectorAll('#mbg span').forEach(e=>e.classList.toggle('sel',e===el)); drawArt(); }}
 function pickTxt(c,el){{ SELTXT=c; TXT_USER_SET=true;   // buyer chose -> stop auto-contrast
   document.querySelectorAll('#mtxt span').forEach(e=>e.classList.toggle('sel',e===el)); drawArt(); }}
 // Apparel: Step-1 colour row picks the SHIRT colour (recolors the garment live).
 function pickShirt(cn,el){{
   selectApparelColor(cn);
   document.querySelectorAll('#mbg span').forEach(e=>e.classList.toggle('sel',e===el)); }}
 // Default the text colour to contrast the shirt, unless the buyer set one.
 function autoContrastText(cn){{
   if(TXT_USER_SET) return;
   // Mugs print on a WHITE ceramic body (the chosen colour is the handle/rim/
   // interior ACCENT, not the print field), so text must contrast the light body
   // - always dark, regardless of the accent colour.
   if((typeof IS_MUG!=='undefined'&&IS_MUG)||(typeof IS_CAL!=='undefined'&&IS_CAL)){{ SELTXT='#1b1b1f'; renderTxt(); drawArt(); return; }}
   var dark={{'Black':1,'Charcoal':1,'Navy':1,'Royal Blue':1,'Red':1,'Maroon':1,
     'Forest Green':1,'Purple':1,'Brown':1}};
   SELTXT = dark[cn] ? '#ffffff' : '#1b1b1f';
   renderTxt(); drawArt(); }}
 const FRAMECOLOR = {{"Premium Solid Oak":"#b28e60","Premium Walnut":"#5c4030",
   "Gallery Gold":"#c6a052","Classic Black Wood":"#1c1c1e",
   "Classic White Wood":"#f4f3ef","Slim Black":"#1c1c1e"}};
 const APPARELCOLOR = {{"White":"#f4f3ef","Sand":"#d8c9a8","Heather Grey":"#b9bdc2",
   "Light Blue":"#a7c7e7","Black":"#1c1c1e","Charcoal":"#3a3f43","Navy":"#26324a",
   "Royal Blue":"#2f4ba0","Red":"#b3322c","Maroon":"#5e2a32","Forest Green":"#2e4a39",
   "Sage":"#7f9b78","Mustard":"#cda434","Purple":"#5b4b8a","Dusty Rose":"#c98a9a",
   "Brown":"#5a4334","Natural":"#e7ddc7","Cream":"#f3ecd9","Silver":"#c9ccce"}};
 // Data-driven apparel layouts. Each slot: kind 'arc'|'line', position as a
 // FRACTION of the print bound b={{x,y,w,h}}, weight = font size as a fraction of
 // min(w,h), font + caps. logo.frame names a decoration; r/midAngle/sweep drive
 // arcs (sweep +1 top, -1 bottom). More layouts are appended in a later step.
 const LAYOUTS=[
  {{key:'freeform',name:'Freeform'}},
  {{key:'badge',name:'Circular Badge',logo:{{cx:0.5,cy:0.5,scale:0.42,frame:'doublering'}},
    decor:['doublering','waves'],defaultFont:"'Oswald',sans-serif",
    slots:[
     {{slot:'arcTop',kind:'arc',cx:0.5,cy:0.5,r:0.40,midAngle:-90,sweep:1,weight:0.085,caps:true}},
     {{slot:'arcBottom',kind:'arc',cx:0.5,cy:0.5,r:0.40,midAngle:90,sweep:-1,weight:0.06,caps:true}}
    ]}}
  ,{{key:'emblem',name:'Vintage Emblem',logo:{{cx:0.5,cy:0.46,scale:0.34,frame:'border'}},
    decor:['border'],defaultFont:"'Cormorant Garamond',serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.16,weight:0.10,caps:true}},
           {{slot:'secondary',kind:'line',x:0.5,y:0.535,weight:0.045,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.88,weight:0.04,caps:true}}]}}
  ,{{key:'minimal',name:'Modern Minimalist',logo:{{cx:0.5,cy:0.36,scale:0.24,frame:'none'}},
    decor:['rule'],defaultFont:"'Montserrat',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.60,weight:0.08,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.74,weight:0.035,caps:true}}]}}
  ,{{key:'street',name:'Oversized Streetwear',logo:{{cx:0.5,cy:0.40,scale:0.62,frame:'none'}},
    decor:[],defaultFont:"'Bebas Neue',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.62,weight:0.20,caps:true}},
           {{slot:'secondary',kind:'line',x:0.5,y:0.82,weight:0.07,caps:true}}]}}
  ,{{key:'vstack',name:'Vertical Stack',logo:{{cx:0.5,cy:0.5,scale:0.34,frame:'none'}},
    decor:['rule'],defaultFont:"'Bebas Neue',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.18,weight:0.12,caps:true}},
           {{slot:'secondary',kind:'line',x:0.5,y:0.80,weight:0.06,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.90,weight:0.04,caps:true}}]}}
  ,{{key:'hbanner',name:'Horizontal Banner',logo:{{cx:0.28,cy:0.5,scale:0.30,frame:'none'}},
    decor:[],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.62,y:0.44,weight:0.10,caps:true}},
           {{slot:'secondary',kind:'line',x:0.62,y:0.58,weight:0.05,caps:true}}]}}
  ,{{key:'chest',name:'Left-Chest Logo',logo:{{cx:0.32,cy:0.34,scale:0.18,frame:'none'}},
    decor:[],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.32,y:0.47,weight:0.04,caps:true}}]}}
  ,{{key:'backprint',name:'Back Print',logo:{{cx:0.5,cy:0.55,scale:0.5,frame:'none'}},
    decor:[],defaultFont:"'Bebas Neue',sans-serif",
    slots:[{{slot:'arcTop',kind:'arc',cx:0.5,cy:0.40,r:0.34,midAngle:-90,sweep:1,weight:0.07,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.88,weight:0.07,caps:true}}]}}
  ,{{key:'wrap',name:'Wraparound',logo:{{cx:0.5,cy:0.5,scale:0.46,frame:'none'}},
    decor:[],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'arcTop',kind:'arc',cx:0.5,cy:0.5,r:0.46,midAngle:-90,sweep:1,weight:0.055,caps:true}}]}}
  ,{{key:'collage',name:'Photo Collage',logo:{{cx:0.5,cy:0.46,scale:0.22,frame:'none'}},
    decor:['collage'],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.965,weight:0.055,caps:true}}]}}
  ,{{key:'adventure',name:'Adventure Badge',logo:{{cx:0.5,cy:0.5,scale:0.30,frame:'shield'}},
    decor:['shield'],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'arcTop',kind:'arc',cx:0.5,cy:0.5,r:0.33,midAngle:-90,sweep:1,weight:0.06,caps:true}},
           {{slot:'arcBottom',kind:'arc',cx:0.5,cy:0.5,r:0.33,midAngle:90,sweep:-1,weight:0.05,caps:true}}]}}
  ,{{key:'monogram',name:'Luxury Monogram',logo:{{cx:0.5,cy:0.42,scale:0.0,frame:'monogram'}},
    decor:['monogram'],defaultFont:"'Cormorant Garamond',serif",
    slots:[{{slot:'monogram',kind:'line',x:0.5,y:0.42,weight:0.26,caps:true}},
           {{slot:'headline',kind:'line',x:0.5,y:0.74,weight:0.05,caps:true}}]}}
 ];
 // Plain-English "what this style does" + which products it suits (f). No f = all
 // products. Drives the gallery caption + per-product filtering so a mug never shows
 // an apparel-only style (Back Print / Left-Chest / Streetwear).
 const LAYOUT_META = {{
   freeform:{{d:'Place your words & photo anywhere'}},
   badge:{{d:'Name curved around a round photo'}},
   emblem:{{d:'Classic crest — text top & bottom'}},
   minimal:{{d:'Clean — small photo, simple text'}},
   street:{{d:'Big bold front graphic',f:['apparel']}},
   vstack:{{d:'Photo with stacked lines of text'}},
   hbanner:{{d:'Photo on the left, text banner'}},
   chest:{{d:'Small logo on the left chest',f:['apparel']}},
   backprint:{{d:'Large design across the back',f:['apparel']}},
   wrap:{{d:'Design wraps all the way around',f:['apparel','mug','branded']}},
   collage:{{d:'Up to 4 photos in a grid'}},
   adventure:{{d:'Shield badge with your text'}},
   monogram:{{d:'Elegant initials monogram'}}
 }};
 function _layout(k){{ for(var i=0;i<LAYOUTS.length;i++) if(LAYOUTS[i].key===k) return LAYOUTS[i]; return LAYOUTS[0]; }}
 // Layout gallery: a thumbnail per LAYOUTS entry; picking one swaps the visible
 // text-slot inputs and redraws. Customer-facing slot labels (no design jargon).
 const SLOT_LABELS={{headline:'Main words',secondary:'Second line',arcTop:'Top curved line',
   arcBottom:'Bottom curved line',tagline:'Small line (date / place)',monogram:'Initials'}};
 // A TRUE mini-preview of each layout, drawn from its real geometry (logo spot +
 // frame + text bars/arcs) so the gallery shows what each arrangement looks like -
 // not the same generic icon. Mark = the logo; bars = text lines; dashed arcs =
 // curved text.
 function _thumbSVG(L){{
   if(L.key==='freeform') return '<svg viewBox="0 0 60 60"><rect x="8" y="20" width="44" height="6" rx="2" fill="#1c1c1e"/><rect x="16" y="31" width="28" height="4" rx="2" fill="#9aa39c"/><rect x="21" y="39" width="18" height="3" rx="1.5" fill="#c2cac3"/></svg>';
   var S=60, p='', lg=L.logo||{{cx:0.5,cy:0.5,scale:0.3,frame:'none'}};
   var lx=lg.cx*S, ly=lg.cy*S, lr=Math.max(3,(lg.scale||0.3)*S*0.5);
   if(lg.frame==='doublering'){{ p+='<circle cx="'+lx+'" cy="'+ly+'" r="'+(lr*1.32)+'" fill="none" stroke="#1c1c1e" stroke-width="1.3"/><circle cx="'+lx+'" cy="'+ly+'" r="'+(lr*1.08)+'" fill="none" stroke="#1c1c1e" stroke-width="0.6"/>'; }}
   else if(lg.frame==='border'){{ p+='<rect x="'+(lx-lr*1.35)+'" y="'+(ly-lr*1.35)+'" width="'+(lr*2.7)+'" height="'+(lr*2.7)+'" fill="none" stroke="#1c1c1e" stroke-width="0.9"/>'; }}
   else if(lg.frame==='shield'){{ var t=lr*1.25; p+='<path d="M'+(lx-t)+','+(ly-t)+' H'+(lx+t)+' V'+(ly+t*0.2)+' Q'+(lx+t)+','+(ly+t*1.1)+' '+lx+','+(ly+t*1.4)+' Q'+(lx-t)+','+(ly+t*1.1)+' '+(lx-t)+','+(ly+t*0.2)+' Z" fill="none" stroke="#1c1c1e" stroke-width="0.9"/>'; }}
   if((L.decor||[]).indexOf('collage')>=0){{ var g=13; p+='<g fill="#cfd6d0"><rect x="'+(29-g)+'" y="'+(25-g)+'" width="'+g+'" height="'+g+'"/><rect x="31" y="'+(25-g)+'" width="'+g+'" height="'+g+'"/><rect x="'+(29-g)+'" y="27" width="'+g+'" height="'+g+'"/><rect x="31" y="27" width="'+g+'" height="'+g+'"/></g>'; }}
   if(lg.frame!=='monogram' && (lg.scale||0)>0.02){{ var m=lr*0.78; p+='<path d="M'+(lx-m)+','+(ly+m*0.62)+' L'+(lx-m*0.28)+','+(ly-m*0.45)+' L'+(lx+m*0.12)+','+(ly+m*0.05)+' L'+(lx+m*0.5)+','+(ly-m*0.62)+' L'+(lx+m)+','+(ly+m*0.62)+' Z" fill="#1c1c1e"/>'; }}
   (L.slots||[]).forEach(function(s){{
     if(s.kind==='arc'){{ var cx=s.cx*S, cy=s.cy*S, r=Math.max(6,s.r*S);
       var sw=(s.midAngle<0)?1:0, wt=(s.midAngle<0)?2:1.6;
       p+='<path d="M'+(cx-r)+','+cy+' A'+r+','+r+' 0 0 '+sw+' '+(cx+r)+','+cy+'" fill="none" stroke="#1c1c1e" stroke-width="'+wt+'" stroke-linecap="round" stroke-dasharray="2.2 1.8"/>';
     }} else {{ var bx=s.x*S, by=s.y*S, h=Math.max(1.8,(s.weight||0.05)*S*0.8);
       if(s.slot==='monogram'){{ p+='<text x="'+bx+'" y="'+(by+h*0.9)+'" font-size="'+(h*1.7)+'" font-family="serif" font-weight="700" text-anchor="middle" fill="#1c1c1e">AB</text>'; }}
       else {{ var w=Math.max(8,Math.min(S*0.72,(s.weight||0.05)*S*3.6+9)); p+='<rect x="'+(bx-w/2)+'" y="'+(by-h/2)+'" width="'+w+'" height="'+h+'" rx="1" fill="#1c1c1e"/>'; }}
     }}
   }});
   return '<svg viewBox="0 0 60 60">'+p+'</svg>';
 }}
 function renderLayoutGallery(){{
   var box=document.getElementById('mlayouts'); if(!box) return;
   var pk=(typeof _pk==='function')?_pk():'wallart';
   box.innerHTML=LAYOUTS.filter(function(L){{ var m=LAYOUT_META[L.key]||{{}};
       return !m.f || m.f.indexOf(pk)>=0; }})              // only styles that suit this product
     .map(function(L){{ var m=LAYOUT_META[L.key]||{{}};
       return `<div class="layoutthumb${{L.key===CURLAYOUT?' sel':''}}" role="button" tabindex="0" title="${{m.d||L.name}}" `+
       `onclick="pickLayout('${{L.key}}')" onkeydown="if(event.key==='Enter')pickLayout('${{L.key}}')">`+
       `${{_thumbSVG(L)}}<span>${{L.name}}</span><small>${{m.d||''}}</small></div>`; }}).join('');
 }}
 function renderSlotInputs(){{
   var box=document.getElementById('mslots'); if(!box) return;
   var L=_layout(CURLAYOUT);
   var keys=(L.slots||[]).map(s=>s.slot);
   var uniq=keys.filter((k,i)=>keys.indexOf(k)===i);
   box.innerHTML=uniq.map(k=>
     `<label>${{SLOT_LABELS[k]}}</label>`+
     `<input id="slot_${{k}}" maxlength="40" value="${{_slot(k).replace(/"/g,'&quot;')}}" oninput="onSlot('${{k}}',this.value)">`).join('');
   // Photo Collage adds up to 4 photo uploads that fill the 2x2 grid.
   if(CURLAYOUT==='collage'){{
     box.innerHTML += `<label>Collage photos (up to 4)</label>`+
       [0,1,2,3].map(i=>`<input type="file" accept="image/png,image/jpeg" class="collageup" `+
         `aria-label="Collage photo ${{i+1}}" onchange="collageUpload(${{i}},this)">`).join('');
   }}
   // Freeform uses the textarea; a layout swaps it for the per-line slot inputs -
   // BOTH live in Step 1 (the Design step) so there is always a visible text field.
   var wb=document.getElementById('mwordbox'); if(wb) wb.style.display=(CURLAYOUT==='freeform')?'':'none';
   var sb=document.getElementById('mslotbox'); if(sb) sb.style.display=(CURLAYOUT==='freeform')?'none':'';
 }}
 function onSlot(k,v){{ SLOTS[k]=v; if(k==='headline'){{ var ta=document.getElementById('mtext'); if(ta) ta.value=v; }} drawArt(); }}
 function pickLayout(k){{ CURLAYOUT=k; LOFF={{}}; renderLayoutGallery(); renderSlotInputs(); drawArt(); }}
 // Put every nudged element back to its template position.
 function resetPlacement(){{ LOFF={{}}; TPOS={{x:0.5,y:0.5}}; drawArt(); toast('Placement reset.'); }}
 function swatchDot(name){{
   // Small colour cue on each frame/material pill - keeps the familiar pill
   // layout while making the picker visual. Framed swatches get a thin white mat
   // ring (inset) so a dark frame still reads as "frame around a print".
   const n=name||''; let c='#efe9dc', ring='';
   if(n.indexOf('Framed - ')===0){{ c=FRAMECOLOR[n.slice(9)]||'#1c1c1e';
     ring='box-shadow:inset 0 0 0 2px #fff'; }}
   else if(n.indexOf('Canvas')===0) c='#f0ece1';
   else if(n.indexOf('Acrylic')===0) c='#bfe0ea';
   else if(n.indexOf('Metal')===0) c='#9aa3a8';
   else if(n.indexOf('T-Shirt - ')===0||n.indexOf('Hoodie - ')===0||n.indexOf('Sweatshirt - ')===0){{
     const cn=n.split(' - ')[1]||''; c=APPARELCOLOR[cn]||'#bbbbbb';
     if(cn==='White'||cn==='Sand'||cn==='Heather Grey'||cn==='Light Blue') ring='box-shadow:inset 0 0 0 1px #cfcabb'; }}
   return `<span class="fdot" style="background:${{c}};${{ring}}"></span>`;
 }}
 let CURFMT="";
 let APPAREL_BOUND=null;
 function frameSpec(){{
   if(CURFMT.indexOf('Framed - ')===0){{
     const n=CURFMT.slice(9);
     return {{t:(n==='Slim Black'?0.028:0.06), color:FRAMECOLOR[n]||'#1c1c1e', mat:true}};
   }}
   if(CURFMT.indexOf('Acrylic')===0||CURFMT.indexOf('Metal')===0)
     return {{t:0.014, color:'#c9ccce', mat:false}};
   return null;  // Poster / Canvas = unframed
 }}
 function _printAR(){{  // width/height ratio of the selected print size (e.g. 8x10 -> 0.8)
   if(IS_CAL){{                  // PORTRAIT white-paper cover - aspect from print bound dims
     var _cd=CAL_DIMS[CAL_PID[CURGARMENT]];
     if(_cd && _cd[0]>0 && _cd[1]>0) return _cd[0]/_cd[1];
     return 0.77;               // sensible portrait default (e.g. A4-ish cover)
   }}
   if(IS_MUG){{                  // white ceramic body - aspect from the print bound dims
     var _md=MUG_DIMS[MUG_PID[CURGARMENT]];
     if(_md && _md[0]>0 && _md[1]>0) return _md[0]/_md[1];
     return 1.0;                // sensible square default
   }}
   if(IS_BRANDED){{              // flat product field - aspect from the print bound dims
     var _d=BRANDED_DIMS[BRANDED_PID[CURGARMENT]];
     if(_d && _d[0]>0 && _d[1]>0) return _d[0]/_d[1];
     return 1.0;                // sensible square default
   }}
   if(IS_APPAREL) return 0.86;   // garment field aspect (shirt body in the canvas)
   const sv=((document.getElementById('msize')||{{}}).value||'').split('|')[0];
   const m=sv.match(/(\\d+(?:\\.\\d+)?)\\s*[xX]\\s*(\\d+(?:\\.\\d+)?)/);
   if(m){{ const a=parseFloat(m[1]), b=parseFloat(m[2]); if(a>0&&b>0) return a/b; }}
   return 0.8;  // default 4:5 portrait
 }}
 function _garmentType(){{
   var g=(CURGARMENT||'').toLowerCase();
   if(g.indexOf('tank')>=0) return 'tank';
   if(g.indexOf('long sleeve')>=0) return 'longsleeve';
   if(g.indexOf('3/4')>=0||g.indexOf('raglan')>=0) return 'raglan';
   if(g.indexOf('polo')>=0) return 'polo';
   if(g.indexOf('hoodie')>=0) return 'hoodie';
   if(g.indexOf('sweatshirt')>=0) return 'sweatshirt';
   return 'tshirt';
 }}
 // Draw a recognizable garment silhouette (by type) in the chosen colour, fit to
 // the box - so the preview looks like the actual tee/hoodie/tank/etc. picked.
 function _garmentShape(ctx,x,y,w,h,type,col){{
   const longS=(type==='longsleeve'||type==='hoodie'||type==='sweatshirt');
   const tank=(type==='tank');
   const P=(u,v)=>[x+u*w, y+v*h];
   const sTopO=0.24, cuffV=longS?0.82:0.42, cuffO=longS?0.11:0.16, cuffI=longS?0.215:0.275;
   const body=new Path2D();
   const M=(u,v)=>body.moveTo(x+u*w,y+v*h);
   const L=(u,v)=>body.lineTo(x+u*w,y+v*h);
   const Q=(cu,cv,u,v)=>body.quadraticCurveTo(x+cu*w,y+cv*h,x+u*w,y+v*h);
   const nDip = tank?0.125:0.175;
   M(0.40,0.085);
   if(tank){{ L(0.36,0.06); L(0.305,0.235); L(0.30,0.95); L(0.70,0.95); L(0.695,0.235); L(0.64,0.06); }}
   else {{
     L(0.25,0.105); L(0.07,sTopO); L(cuffO,cuffV); L(cuffI,cuffV); L(0.27,0.31);
     L(0.25,0.95); L(0.75,0.95);
     L(0.73,0.31); L(1-cuffI,cuffV); L(1-cuffO,cuffV); L(0.93,sTopO); L(0.75,0.105);
   }}
   L(0.60,0.085);
   Q(0.50,nDip,0.40,0.085);
   body.closePath();
   ctx.fillStyle=col; ctx.fill(body);
   const light=['#f4f3ef','#b9bdc2','#d8c9a8','#a7c7e7'].includes((col||'').toLowerCase());
   if(light){{ ctx.strokeStyle='rgba(0,0,0,.16)'; ctx.lineWidth=1.4; ctx.stroke(body); }}
   if(type==='raglan'){{
     ctx.fillStyle=APPARELCOLOR['Heather Grey'];
     const sl=new Path2D();
     sl.moveTo(...P(0.25,0.105)); sl.lineTo(...P(0.07,sTopO)); sl.lineTo(...P(cuffO,cuffV));
     sl.lineTo(...P(cuffI,cuffV)); sl.lineTo(...P(0.30,0.22)); sl.closePath(); ctx.fill(sl);
     const sr=new Path2D();
     sr.moveTo(...P(0.75,0.105)); sr.lineTo(...P(0.93,sTopO)); sr.lineTo(...P(1-cuffO,cuffV));
     sr.lineTo(...P(1-cuffI,cuffV)); sr.lineTo(...P(0.70,0.22)); sr.closePath(); ctx.fill(sr);
   }}
   ctx.lineWidth=Math.max(1.6,w*0.012); ctx.lineJoin='round';
   if(type==='polo'){{
     ctx.strokeStyle='rgba(0,0,0,.34)';
     ctx.beginPath(); ctx.moveTo(...P(0.41,0.085)); ctx.lineTo(...P(0.46,0.19));
     ctx.lineTo(...P(0.50,0.135)); ctx.lineTo(...P(0.54,0.19)); ctx.lineTo(...P(0.59,0.085)); ctx.stroke();
     ctx.beginPath(); ctx.moveTo(...P(0.50,0.135)); ctx.lineTo(...P(0.50,0.30)); ctx.stroke();
     ctx.fillStyle='rgba(0,0,0,.34)';
     [0.20,0.26].forEach(p=>{{ctx.beginPath();ctx.arc(...P(0.50,p),Math.max(2,w*0.013),0,7);ctx.fill();}});
   }} else if(type==='hoodie'){{
     ctx.fillStyle=col; const hood=new Path2D();
     hood.moveTo(...P(0.39,0.09)); hood.quadraticCurveTo(...P(0.50,-0.03),...P(0.61,0.09));
     hood.quadraticCurveTo(...P(0.50,0.05),...P(0.39,0.09)); hood.closePath(); ctx.fill(hood);
     if(light){{ctx.strokeStyle='rgba(0,0,0,.16)';ctx.stroke(hood);}}
     ctx.strokeStyle='rgba(0,0,0,.24)'; ctx.beginPath();
     ctx.moveTo(...P(0.41,0.10)); ctx.quadraticCurveTo(...P(0.50,0.17),...P(0.59,0.10)); ctx.stroke();
     ctx.strokeStyle='rgba(0,0,0,.18)'; ctx.strokeRect(x+0.345*w,y+0.58*h,0.31*w,0.20*h);
     ctx.strokeStyle='rgba(0,0,0,.30)'; ctx.beginPath();
     ctx.moveTo(...P(0.47,0.11)); ctx.lineTo(...P(0.47,0.30));
     ctx.moveTo(...P(0.53,0.11)); ctx.lineTo(...P(0.53,0.30)); ctx.stroke();
   }} else if(!tank){{
     ctx.strokeStyle='rgba(0,0,0,.22)'; ctx.beginPath();
     ctx.moveTo(...P(0.40,0.095)); ctx.quadraticCurveTo(...P(0.50,0.18),...P(0.60,0.095)); ctx.stroke();
   }}
   if(type==='sweatshirt'||type==='hoodie'){{
     ctx.strokeStyle='rgba(0,0,0,.16)'; ctx.lineWidth=Math.max(3,w*0.03);
     ctx.beginPath(); ctx.moveTo(...P(0.25,0.93)); ctx.lineTo(...P(0.75,0.93)); ctx.stroke();
   }}
 }}
 function drawGarment(ctx,x,y,w,h){{
   const cn=(CURFMT.split(' - ')[1]||'Black'); const col=APPARELCOLOR[cn]||'#1c1c1e';
   _garmentShape(ctx,x,y,w,h,_garmentType(),col);
 }}
 // Draw a recognizable SILHOUETTE of the actual branded product (flat, 2D) in the
 // selected colour, so the buyer designs on the real thing - a keychain reads as a
 // keychain, a tote as a tote - instead of a mystery grey rectangle. Mirrors the
 // apparel garment silhouette. The design (print frame) is composited on top.
 function _drawBrandedShape(ctx,x,y,w,h,col,g){{
   ctx.save(); ctx.fillStyle=col; ctx.strokeStyle='rgba(0,0,0,.20)'; ctx.lineWidth=2;
   ctx.lineJoin='round';
   function rr(rx,ry,rw,rh,r){{ r=Math.min(r,rw/2,rh/2); ctx.beginPath();
     ctx.moveTo(rx+r,ry); ctx.lineTo(rx+rw-r,ry); ctx.quadraticCurveTo(rx+rw,ry,rx+rw,ry+r);
     ctx.lineTo(rx+rw,ry+rh-r); ctx.quadraticCurveTo(rx+rw,ry+rh,rx+rw-r,ry+rh);
     ctx.lineTo(rx+r,ry+rh); ctx.quadraticCurveTo(rx,ry+rh,rx,ry+rh-r);
     ctx.lineTo(rx,ry+r); ctx.quadraticCurveTo(rx,ry,rx+r,ry); ctx.closePath(); }}
   if(g.indexOf('keychain')>=0){{
     var rr2=h*0.055, cx=x+w/2, ry=y+h*0.10;                 // split ring at the top
     ctx.save(); ctx.strokeStyle='#9a9a9a'; ctx.lineWidth=Math.max(3,h*0.02);
     ctx.beginPath(); ctx.arc(cx,ry,rr2,0,7); ctx.stroke(); ctx.restore();
     var tw=w*0.58, th=h*0.66, tx=cx-tw/2, ty=ry+rr2;        // the tag
     rr(tx,ty,tw,th,tw*0.10); ctx.fill(); ctx.stroke();
     // little hole that the ring passes through
     ctx.save(); ctx.fillStyle='rgba(0,0,0,.30)'; ctx.beginPath(); ctx.arc(cx,ty+th*0.07,tw*0.03,0,7); ctx.fill(); ctx.restore();
   }} else if(g.indexOf('tote')>=0||g.indexOf('bag')>=0){{
     var bw=w*0.64, bh=h*0.70, bx=x+(w-bw)/2, by=y+h*0.24;
     ctx.lineWidth=Math.max(3,bw*0.028);                      // slim handles (behind the body)
     ctx.beginPath(); ctx.arc(bx+bw*0.31,by+2,bh*0.22,Math.PI,2*Math.PI); ctx.stroke();
     ctx.beginPath(); ctx.arc(bx+bw*0.69,by+2,bh*0.22,Math.PI,2*Math.PI); ctx.stroke();
     ctx.lineWidth=2; rr(bx,by,bw,bh,bw*0.03); ctx.fill(); ctx.stroke();
   }} else if(g.indexOf('phone')>=0){{
     var pw=w*0.44, ph=h*0.84, px=x+(w-pw)/2, py=y+h*0.08;
     rr(px,py,pw,ph,pw*0.16); ctx.fill(); ctx.stroke();
     ctx.save(); ctx.fillStyle='rgba(0,0,0,.22)';            // camera bump
     ctx.beginPath(); ctx.arc(px+pw*0.24,py+ph*0.11,pw*0.075,0,7); ctx.fill(); ctx.restore();
   }} else if(g.indexOf('journal')>=0||g.indexOf('notebook')>=0){{
     var jw=w*0.56, jh=h*0.74, jx=x+(w-jw)/2, jy=y+h*0.13;
     rr(jx,jy,jw,jh,jw*0.04); ctx.fill(); ctx.stroke();
     ctx.save(); ctx.strokeStyle='rgba(0,0,0,.22)';
     ctx.beginPath(); ctx.moveTo(jx+jw*0.13,jy); ctx.lineTo(jx+jw*0.13,jy+jh); ctx.stroke();   // spine
     ctx.strokeStyle='rgba(0,0,0,.32)'; ctx.lineWidth=Math.max(3,jw*0.035);
     ctx.beginPath(); ctx.moveTo(jx+jw*0.82,jy); ctx.lineTo(jx+jw*0.82,jy+jh); ctx.stroke();   // elastic band
     ctx.restore();
   }} else if(g.indexOf('mouse')>=0){{
     var mw=w*0.80, mh=h*0.52, mx=x+(w-mw)/2, my=y+(h-mh)/2;
     rr(mx,my,mw,mh,mh*0.16); ctx.fill(); ctx.stroke();
   }} else if(g.indexOf('sticker')>=0){{
     var sw=w*0.62, sh=h*0.62, sx=x+(w-sw)/2, sy=y+(h-sh)/2, pad=Math.max(5,sw*0.05);
     ctx.save(); ctx.fillStyle='#fff'; rr(sx-pad,sy-pad,sw+2*pad,sh+2*pad,sh*0.18); ctx.fill();
     ctx.strokeStyle='rgba(0,0,0,.12)'; ctx.stroke(); ctx.restore();           // die-cut white border
     rr(sx,sy,sw,sh,sh*0.15); ctx.fill(); ctx.stroke();
   }} else {{
     rr(x+w*0.06,y+h*0.06,w*0.88,h*0.88,Math.min(w,h)*0.04); ctx.fill(); ctx.stroke();
   }}
   ctx.restore();
 }}
 // Branded mode now previews on the ACTUAL product silhouette (selected colour),
 // so the design reads on the real product instead of a plain grey card.
 function _drawBrandedField(ctx,x,y,w,h){{
   var cn=(CURFMT.split(' - ')[1]||'White'); var col=(typeof APPARELCOLOR!=='undefined'&&APPARELCOLOR[cn])||'#f2efe9';
   _drawBrandedShape(ctx,x,y,w,h,col,(typeof CURGARMENT!=='undefined'?CURGARMENT:'').toLowerCase()); }}
 // A MUG prints on its WHITE ceramic body; the colour variant is the rim/handle
 // ACCENT (not the print field). Fill a light ceramic body with a thin accent
 // band along the TOP edge as the rim cue, keeping auto-contrast text dark-on-light.
 function _drawMugField(ctx,x,y,w,h){{
   var cn=(CURFMT.split(' - ')[1]||'White'); var acc=(typeof APPARELCOLOR!=='undefined'&&APPARELCOLOR[cn])||'#bbb';
   ctx.save(); ctx.fillStyle='#f4f3ef'; ctx.fillRect(x,y,w,h);
   ctx.fillStyle=acc; ctx.fillRect(x,y,w,Math.max(6,h*0.06));            // accent rim band
   ctx.strokeStyle='rgba(0,0,0,.12)'; ctx.lineWidth=2; ctx.strokeRect(x,y,w,h); ctx.restore(); }}
 // Mug WRAP preview: draw a realistic white mug (body + handle + accent rim) and
 // wrap the buyer's design (the print panel `b`) around the body with a cylinder
 // warp (compress toward the edges) + soft shading, so the final proof shows the
 // design ON a mug, not on a flat panel. The #1 mug conversion lever.
 function _drawMugMockup(octx,src,b,W,H,acc){{
   octx.save(); octx.fillStyle='#efece4'; octx.fillRect(0,0,W,H);        // studio
   var bw=W*0.50, bh=H*0.40, bx=W*0.42-bw/2, by=H*0.30, cx=bx+bw/2;
   octx.fillStyle='rgba(0,0,0,.12)';                                     // contact shadow
   octx.beginPath(); octx.ellipse(cx,by+bh+12,bw*0.42,9,0,0,7); octx.fill();
   octx.lineWidth=Math.max(10,bw*0.11); octx.strokeStyle='#f1efe9';      // handle (behind)
   octx.beginPath(); octx.arc(bx+bw-2,by+bh*0.50,bh*0.27,-1.15,1.15); octx.stroke();
   octx.strokeStyle='rgba(0,0,0,.10)'; octx.lineWidth=2;
   octx.beginPath(); octx.arc(bx+bw-2,by+bh*0.50,bh*0.27+bw*0.055,-1.05,1.05); octx.stroke();
   function bodyPath(){{ var r=bw*0.11; octx.beginPath();
     octx.moveTo(bx+r,by); octx.lineTo(bx+bw-r,by); octx.quadraticCurveTo(bx+bw,by,bx+bw,by+r);
     octx.lineTo(bx+bw,by+bh-r); octx.quadraticCurveTo(bx+bw,by+bh,bx+bw-r,by+bh);
     octx.lineTo(bx+r,by+bh); octx.quadraticCurveTo(bx,by+bh,bx,by+bh-r);
     octx.lineTo(bx,by+r); octx.quadraticCurveTo(bx,by,bx+r,by); octx.closePath(); }}
   bodyPath(); octx.fillStyle='#f4f3ef'; octx.fill();                    // warm-white ceramic body (matches the print panel)
   octx.save(); bodyPath(); octx.clip();                                 // wrap design onto body
   // Gentler cylinder curve, and PRESERVE the design's true aspect ratio: the wide
   // wrap panel renders as a wide-but-short band centred on the mug (what actually
   // prints), instead of being stretched to fill a near-square body.
   var span=1.9, N=Math.max(48,Math.round(bw)), rimInset=bh*0.10;
   function sx(u){{ var th=(u-0.5)*span; return cx+Math.sin(th)/Math.sin(span/2)*(bw/2)*0.92; }}
   var screenW=sx(1)-sx(0);
   var ar=(b.w>0&&b.h>0)?(b.h/b.w):0.5;
   var drawnH=Math.min(bh-2*rimInset, screenW*ar);                       // aspect-true height
   var dy=by+(bh-drawnH)/2;                                              // vertical centre
   for(var i=0;i<N;i++){{
     var u0=i/N,u1=(i+1)/N,x0=sx(u0),x1=sx(u1),th=(((u0+u1)/2)-0.5)*span;
     octx.drawImage(src,b.x+u0*b.w,b.y,Math.max(0.5,(u1-u0)*b.w),b.h,x0,dy,(x1-x0)+1.0,drawnH);
     var shade=0.20*(1-Math.cos(th));
     if(shade>0.01){{ octx.fillStyle='rgba(0,0,0,'+shade.toFixed(3)+')'; octx.fillRect(x0,dy,(x1-x0)+1.2,drawnH); }}
   }}
   octx.restore();
   octx.save(); bodyPath(); octx.clip();                                 // cylinder sheen
   var g=octx.createLinearGradient(bx,0,bx+bw,0);
   g.addColorStop(0,'rgba(0,0,0,.13)'); g.addColorStop(0.2,'rgba(255,255,255,.12)');
   g.addColorStop(0.5,'rgba(255,255,255,.05)'); g.addColorStop(1,'rgba(0,0,0,.15)');
   octx.fillStyle=g; octx.fillRect(bx,by,bw,bh); octx.restore();
   octx.fillStyle='#ffffff'; octx.beginPath(); octx.ellipse(cx,by,bw/2,bh*0.06,0,0,7); octx.fill();
   octx.fillStyle='rgba(0,0,0,.16)'; octx.beginPath(); octx.ellipse(cx,by,bw/2*0.84,bh*0.046,0,0,7); octx.fill();
   octx.strokeStyle=acc; octx.lineWidth=Math.max(4,bh*0.022);            // accent rim ring
   octx.beginPath(); octx.ellipse(cx,by,bw/2,bh*0.06,0,0,7); octx.stroke();
   octx.strokeStyle='rgba(0,0,0,.16)'; octx.lineWidth=2; octx.stroke();
   octx.restore();
 }}
 function _mugMockupURL(){{
   var cv=document.getElementById('mcanvas'); if(!cv) return '';
   _SNAPPING=true;
   _CLEAN=true; drawArt();
   var b=APPAREL_BOUND||{{x:cv.width*0.2,y:cv.height*0.2,w:cv.width*0.6,h:cv.height*0.5}};
   var cn=(CURFMT.split(' - ')[1]||'White'); var acc=(typeof APPARELCOLOR!=='undefined'&&APPARELCOLOR[cn])||'#c9a14a';
   var oc=document.createElement('canvas'); oc.width=cv.width; oc.height=cv.height;
   try{{ _drawMugMockup(oc.getContext('2d'),cv,b,oc.width,oc.height,acc); }}catch(e){{}}
   _CLEAN=false; drawArt(); _SNAPPING=false;
   try{{ return oc.toDataURL('image/png'); }}catch(e){{ return ''; }}
 }}
 // ── Real product-photo mockups (owner-supplied; auto-upgrade) ────────────────
 // When a real product photo is registered for the current product we composite
 // the LIVE design into its print area and show a REAL product picture in the
 // preview. Empty until photos are dropped in -> the editor's generated mockup
 // is used. No supplier/marketplace names are emitted (customer-safe).
 var _MOCKCACHE={{}};
 // When the design changes, the OPEN spin re-renders so editing text/photo/colour
 // is reflected live (it used to show a frozen snapshot -> looked like you "cannot
 // change" anything). drawArt sets _SPIN_DIRTY; the read-design helpers set
 // _SNAPPING so their internal drawArt calls don't falsely flag a change.
 var _SPIN_DIRTY=false, _SNAPPING=false;
 function _mockKey(){{ var g=(typeof CURGARMENT!=='undefined'&&CURGARMENT)?CURGARMENT:'';
   if(g) return g; var f=(typeof CURFMT!=='undefined'?CURFMT:'')||''; return f.split(' - ')[0]||''; }}
 // Resolve the real-photo mockup base for the current product, in priority order:
 //   1) brand/mockups/<id> manual override (keyed by product NAME)
 //   2) the real tile photo already in the pipeline (mug/branded/cal) or the
 //      apparel per-colour / front+back photos
 //   3) null -> the editor uses its generated body/field.
 // Returns {{src, front, back, area:[x,y,w,h frac], cyl, span}} or null.
 function _mockBase(){{
   var k=_mockKey();
   if(k && typeof MOCKUP_PHOTOS!=='undefined' && MOCKUP_PHOTOS[k]) return MOCKUP_PHOTOS[k];
   // The grid's tile-<id>.jpg are MARKETING photos with a SAMPLE design baked in,
   // so they are deliberately NOT used as a compositing base for mug/branded/
   // calendar - that would show the sample art, not the buyer's design. Those
   // products use the generated CLEAN body unless the owner drops a genuine BLANK
   // photo into brand/mockups/. Only apparel resolves a real photo here.
   var url='', cyl=false, back=null;
   var fmt=(typeof CURFMT!=='undefined'?CURFMT:'')||'';
   if(typeof IS_APPAREL!=='undefined' && IS_APPAREL){{
     var gid=(typeof APPGID!=='undefined'&&APPGID[k])||'';
     // The single per-garment side photo is colour-AGNOSTIC (one white studio
     // shot), so it may only stand in when real PER-COLOUR photos exist - else a
     // black shirt would show as white. Mirrors the editor's drawArt guard.
     var hasColor=!!(typeof APPAREL_COLOR_IMG!=='undefined'&&APPAREL_COLOR_IMG[gid]
       &&Object.keys(APPAREL_COLOR_IMG[gid]).length);
     if(!hasColor) return null;
     url=(typeof _tileColorUrl==='function')?_tileColorUrl(gid,(fmt.split(' - ')[1]||'')):'';
     var sm=(typeof APPAREL_SIDE_IMG!=='undefined')?(APPAREL_SIDE_IMG[gid]||APPAREL_SIDE_IMG[gid.replace(/_(value|premium)$/,'')]):null;
     if(!url && sm) url=sm.front||'';
     back=(sm&&sm.back)||null; cyl=false;
   }}
   if(!url) return null;
   var area=cyl?[0.33,0.34,0.34,0.34]:[0.28,0.26,0.44,0.50];
   // `src` follows the side the buyer is reviewing, so front/back resolve to their
   // own real photo (apparel). Cylinders/flat goods have no back -> always front.
   var side=(typeof APPLACEMENT!=='undefined'&&APPLACEMENT==='back'&&back)?'back':'front';
   return {{src:(side==='back')?back:url, front:url, back:back, area:area, cyl:cyl, span:1.9}};
 }}
 function _mockSpec(){{ return (typeof _mockBase==='function')?_mockBase():null; }}
 // NOTE: mockup photos are re-hosted SAME-ORIGIN by the build (_emit -> data-URI or
 // assets/<file>), so crossOrigin + toDataURL() never taint the canvas. If photos
 // are ever served from a third-party CDN, set CORS headers there (and on the
 // editor's _mockupImg loader too) or the spin's _photoMockupURL would silently
 // return '' while the flat editor preview still works.
 function _preloadOne(u){{ if(!u||_MOCKCACHE[u]) return; _MOCKCACHE[u]='loading';
   var im=new Image(); im.crossOrigin='anonymous';
   im.onload=function(){{ _MOCKCACHE[u]=im; }}; im.onerror=function(){{ _MOCKCACHE[u]=null; }}; im.src=u; }}
 // URL-keyed cache so a product's FRONT and BACK photos preload + resolve
 // independently (the buyer can rotate to either side).
 function _preloadMock(){{ var s=_mockSpec(); if(!s) return;
   _preloadOne(s.front||s.src); if(s.back) _preloadOne(s.back); }}
 function _mockImg(){{ var s=_mockSpec(); if(!s||!s.src) return null;
   var im=_MOCKCACHE[s.src]; return (im&&im!=='loading'&&im.naturalWidth)?im:null; }}
 // Snapshot the CLEAN design (no editor chrome) from #mcanvas into an offscreen
 // canvas, so the wrap/composite never picks up the editor overlay.
 function _designSnap(){{ var cv=document.getElementById('mcanvas'); if(!cv) return null;
   _SNAPPING=true;                       // snapshotting is a READ, not an edit
   _CLEAN=true; if(typeof drawArt==='function') drawArt();
   var s=document.createElement('canvas'); s.width=cv.width; s.height=cv.height;
   try{{ s.getContext('2d').drawImage(cv,0,0); }}catch(e){{}}
   _CLEAN=false; if(typeof drawArt==='function') drawArt(); _SNAPPING=false; return s; }}
 // Wrap a design panel `b` (src px) onto a cylinder's print `area` ([x,y,w,h] px).
 // span=visible front arc (rad); arc=barrel arc the print covers; rot=spin offset.
 // Columns outside the print arc are left bare (body/photo shows through), so a
 // spin reveals a clean back - and the design always faces front at rest.
 function _wrapInto(ctx,src,b,area,opts){{
   opts=opts||{{}}; var ax=area[0],ay=area[1],aw=area[2],ah=area[3];
   var span=opts.span||1.9, rot=opts.rot||0, arc=opts.arc||1.7;
   var cx=ax+aw/2, N=Math.max(48,Math.round(aw));
   var ar=(b.w>0&&b.h>0)?(b.h/b.w):0.5;
   var drawnH=Math.min(ah, aw*ar), dy=ay+(ah-drawnH)/2, hs=Math.sin(span/2)||1;
   for(var i=0;i<N;i++){{
     var s0=i/N,s1=(i+1)/N,th0=(s0-0.5)*span,th1=(s1-0.5)*span,thm=(th0+th1)/2;
     var x0=cx+Math.sin(th0)/hs*(aw/2), x1=cx+Math.sin(th1)/hs*(aw/2);
     var rel=thm-rot; while(rel>Math.PI) rel-=2*Math.PI; while(rel<-Math.PI) rel+=2*Math.PI;
     if(Math.abs(rel)<=arc/2){{
       var v=(rel+arc/2)/arc, sw=Math.max(0.5,(span/(N*arc))*b.w);
       try{{ ctx.drawImage(src, b.x+v*b.w, b.y, sw, b.h, x0, dy, (x1-x0)+1.0, drawnH); }}catch(e){{}}
     }}
     if(opts.shade){{ var sh=0.20*(1-Math.cos(thm));
       if(sh>0.01){{ ctx.fillStyle='rgba(0,0,0,'+sh.toFixed(3)+')'; ctx.fillRect(x0,dy,(x1-x0)+1.2,drawnH); }} }}
   }}
 }}
 // A clean generated cylinder body (warm-white mug w/ handle, or steel tumbler/
 // bottle w/ lid) + accent rim, used when no real photo is registered yet.
 // Returns the front print area [x,y,w,h] px.
 function _drawCylBody(ctx,W,H,acc,opts){{
   opts=opts||{{}}; var handle=!!opts.handle;
   var bw=handle?W*0.46:W*0.34, bh=handle?H*0.46:H*0.66;
   var bx=(W-bw)/2-(handle?W*0.04:0), by=(H-bh)/2+H*0.02, cx=bx+bw/2, r=Math.min(bw*0.16,18);
   ctx.save(); ctx.fillStyle='rgba(0,0,0,.12)';
   ctx.beginPath(); ctx.ellipse(cx,by+bh+8,bw*0.46,8,0,0,7); ctx.fill(); ctx.restore();
   if(handle){{ ctx.lineWidth=Math.max(10,bw*0.12); ctx.strokeStyle='#efece4';
     ctx.beginPath(); ctx.arc(bx+bw+2,by+bh*0.5,bh*0.26,-1.15,1.15); ctx.stroke();
     ctx.strokeStyle='rgba(0,0,0,.10)'; ctx.lineWidth=2;
     ctx.beginPath(); ctx.arc(bx+bw+2,by+bh*0.5,bh*0.26+bw*0.05,-1.05,1.05); ctx.stroke(); }}
   function body(){{ ctx.beginPath();
     ctx.moveTo(bx+r,by); ctx.lineTo(bx+bw-r,by); ctx.quadraticCurveTo(bx+bw,by,bx+bw,by+r);
     ctx.lineTo(bx+bw,by+bh-r); ctx.quadraticCurveTo(bx+bw,by+bh,bx+bw-r,by+bh);
     ctx.lineTo(bx+r,by+bh); ctx.quadraticCurveTo(bx,by+bh,bx,by+bh-r);
     ctx.lineTo(bx,by+r); ctx.quadraticCurveTo(bx,by,bx+r,by); ctx.closePath(); }}
   body(); var g=ctx.createLinearGradient(bx,0,bx+bw,0);
   if(handle){{ g.addColorStop(0,'#e7e4dc'); g.addColorStop(0.5,'#fbfaf7'); g.addColorStop(1,'#e2dfd6'); }}
   else {{ g.addColorStop(0,'#c5cacf'); g.addColorStop(0.5,'#f4f6f7'); g.addColorStop(1,'#c0c5cb'); }}
   ctx.fillStyle=g; ctx.fill();
   ctx.save(); body(); ctx.clip();
   ctx.fillStyle=handle?'#ffffff':'#dfe3e6'; ctx.fillRect(bx,by,bw,Math.max(6,bh*0.05));
   ctx.restore();
   ctx.strokeStyle=acc; ctx.lineWidth=Math.max(3,bh*0.018);
   ctx.beginPath(); ctx.moveTo(bx,by+Math.max(3,bh*0.03)); ctx.lineTo(bx+bw,by+Math.max(3,bh*0.03)); ctx.stroke();
   if(!handle){{ ctx.fillStyle=acc; var cw=bw*0.5,ch=H*0.05; ctx.fillRect(cx-cw/2,by-ch,cw,ch); }}
   var pad=bw*0.12; return [bx+pad,by+bh*0.22,bw-2*pad,bh*0.56];
 }}
 function _setMockTitle(isPhoto){{
   var t=document.getElementById('mock3dttl'), s=document.getElementById('mock3dsub');
   if(t) t.innerHTML=isPhoto?'&#128444;&#65039; Your design on the real product'
     :'&#128260; Drag to spin your product';
   if(s) s.textContent='Your approved flat proof is exactly what prints.'; }}
 // Realistic 2D spin for cylindrical products (mug / bottle / tumbler): real photo
 // when registered, else a clean generated body. Drag to rotate; never blank.
 function _openCylSpin(){{
   if(_3d&&_3d.on) _3d.on=false;            // stop any prior render loop (re-entrancy guard)
   _setMockTitle(false);
   var mount=document.getElementById('mug3d'); if(!mount){{ _showFlatPhoto(_composedProofURL()); return; }}
   mount.innerHTML='';
   var W=Math.max(240,mount.clientWidth||360), H=mount.clientHeight||340;
   var dpr=Math.min(2.5,window.devicePixelRatio||1);
   var c=document.createElement('canvas'); c.width=W*dpr; c.height=H*dpr;
   c.style.width='100%'; c.style.height='100%'; c.style.display='block'; c.style.cursor='grab';
   mount.appendChild(c);
   var ctx=c.getContext('2d'); if(!ctx){{ _showFlatPhoto(_composedProofURL()); return; }}
   ctx.scale(dpr,dpr);
   var cv=document.getElementById('mcanvas');
   var snap=_designSnap(); if(!snap){{ _showFlatPhoto(_composedProofURL()); return; }}
   var b=(typeof APPAREL_BOUND!=='undefined'&&APPAREL_BOUND)?APPAREL_BOUND
     :{{x:cv.width*0.2,y:cv.height*0.2,w:cv.width*0.6,h:cv.height*0.5}};
   var spec=_mockSpec();
   var handle=(typeof IS_MUG!=='undefined'&&IS_MUG);
   var cn=((typeof CURFMT!=='undefined'?CURFMT:'').split(' - ')[1])||'White';
   var acc=(typeof APPARELCOLOR!=='undefined'&&APPARELCOLOR[cn])||'#c9a14a';
   var rot=0,drag=false,lx=0,dirty=true,hadPhoto=false,tick=0;
   function frame(){{
     ctx.clearRect(0,0,W,H);
     var photo=_mockImg(), area;
     if(photo&&spec){{
       var ir=photo.naturalWidth/photo.naturalHeight, cr=W/H, dw,dh;
       if(ir>cr){{ dw=W; dh=dw/ir; }} else {{ dh=H; dw=dh*ir; }}
       var px=(W-dw)/2, py=(H-dh)/2; ctx.drawImage(photo,px,py,dw,dh);
       area=[px+spec.area[0]*dw, py+spec.area[1]*dh, spec.area[2]*dw, spec.area[3]*dh];
       _wrapInto(ctx,snap,b,area,{{span:spec.span||1.9,rot:rot,arc:1.7,shade:false}});
     }} else {{
       area=_drawCylBody(ctx,W,H,acc,{{handle:handle}});
       _wrapInto(ctx,snap,b,area,{{span:1.9,rot:rot,arc:1.7,shade:true}});
     }}
   }}
   c.addEventListener('mousedown',function(e){{drag=true;lx=e.clientX;c.style.cursor='grabbing';}});
   window.addEventListener('mouseup',function(){{drag=false;c.style.cursor='grab';}});
   c.addEventListener('mousemove',function(e){{ if(drag){{ rot+=(e.clientX-lx)*0.01; lx=e.clientX; dirty=true; }} }});
   c.addEventListener('touchmove',function(e){{ if(e.touches[0]){{ if(lx){{ rot+=(e.touches[0].clientX-lx)*0.01; dirty=true; }} lx=e.touches[0].clientX; }} }},{{passive:true}});
   c.addEventListener('touchend',function(){{ lx=0; }});
   _3d={{on:true}};
   // Gently ROCK the product around the front (not a full spin) so it visibly moves
   // - the cue that it's a 3D preview - while the design STAYS facing the buyer
   // (a full auto-rotate hid the design on the bare back most of the time). Drag
   // still gives full manual control; a late-loading real photo upgrades in place.
   (function loop(){{ if(!_3d.on) return; var hp=!!_mockImg();
     if(hp!==hadPhoto){{ hadPhoto=hp; dirty=true; }}
     if(_SPIN_DIRTY){{ var ns=_designSnap(); if(ns) snap=ns; _SPIN_DIRTY=false; dirty=true; }}  // live edit
     if(!drag){{ tick++; rot=0.42*Math.sin(tick*0.022); dirty=true; }}
     if(dirty){{ frame(); dirty=false; }} requestAnimationFrame(loop); }})();
 }}
 // Real front/back review (apparel): show the composed proof of the CURRENT side
 // and flip to the other side's OWN design on drag/tap. Uses _composedProofURL so
 // it works on the real garment photo OR the recolouring silhouette - independent
 // of whether per-colour mockup photos exist (the old path fell to a WebGL panel
 // that merely MIRRORED the front design as the back). This is the proof's flip,
 // shown inline on the product.
 function _openFlipReview(){{
   var mount=document.getElementById('mug3d');
   if(!mount){{ _build3D(_composedProofURL()); return; }}
   mount.innerHTML=''; _3d={{on:false}};
   var im=document.createElement('img'); im.alt='Your product - front and back';
   im.draggable=false;                  // stop the browser's native image drag-ghost (it ate the flip drag)
   im.style.cssText='width:100%;height:100%;object-fit:contain;display:block;border-radius:8px;cursor:pointer;-webkit-user-drag:none;user-select:none';
   im.addEventListener('dragstart',function(e){{ e.preventDefault(); }});
   mount.appendChild(im);
   // Explicit, obvious flip control so the buyer never has to discover tap/drag.
   var fb=document.createElement('button'); fb.type='button';
   fb.style.cssText='position:absolute;left:50%;top:8px;transform:translateX(-50%);z-index:3;background:#103d2e;color:#fff;border:none;border-radius:20px;padding:8px 16px;font-size:13px;font-weight:700;cursor:pointer;box-shadow:0 2px 9px rgba(0,0,0,.28)';
   mount.appendChild(fb);
   var ttl=document.getElementById('mock3dttl'), sub=document.getElementById('mock3dsub');
   if(sub) sub.textContent='Your approved flat proof is exactly what prints.';
   function _isBack(){{ return (typeof APPLACEMENT!=='undefined'&&APPLACEMENT==='back'); }}
   function _render(){{ var u=(typeof _composedProofURL==='function')?_composedProofURL():''; if(u) im.src=u;
     if(ttl) ttl.innerHTML='&#128085; '+(_isBack()?'Back':'Front')+' &mdash; drag or tap to flip';
     fb.innerHTML='&#8635; See the '+(_isBack()?'front':'back'); }}
   function _flip(){{ if(typeof setPlacement==='function') setPlacement(_isBack()?'front':'back'); _render(); }}
   _render();
   fb.addEventListener('click',function(e){{ e.stopPropagation(); _flip(); }});
   var lx=0,drag=false,moved=false;
   im.addEventListener('mousedown',function(e){{drag=true;moved=false;lx=e.clientX;}});
   window.addEventListener('mouseup',function(){{drag=false;}});
   im.addEventListener('mousemove',function(e){{ if(drag&&Math.abs(e.clientX-lx)>50){{ moved=true; _flip(); drag=false; }} }});
   im.addEventListener('click',function(){{ if(moved){{ moved=false; return; }} _flip(); }});
   im.addEventListener('touchstart',function(e){{ moved=false; lx=(e.touches[0]||{{}}).clientX||0; }},{{passive:true}});
   im.addEventListener('touchmove',function(e){{ var x=(e.touches[0]||{{}}).clientX||0; if(lx&&Math.abs(x-lx)>50){{ moved=true; _flip(); lx=0; }} }},{{passive:true}});
   _SPIN_DIRTY=false; _3d={{on:true}};   // live-update when the buyer edits while reviewing
   (function _w(){{ if(!_3d.on) return; if(_SPIN_DIRTY){{ _SPIN_DIRTY=false; _render(); }} requestAnimationFrame(_w); }})();
 }}
 function _showFlatPhoto(url){{
   _setMockTitle(true);
   var mount=document.getElementById('mug3d'); if(!mount||!url) return;
   mount.innerHTML='';
   var im=document.createElement('img'); im.src=url; im.alt='Realistic product preview';
   im.style.cssText='width:100%;height:100%;object-fit:contain;display:block;border-radius:8px';
   mount.appendChild(im); _SPIN_DIRTY=false; _3d={{on:true}};
   (function _w(){{ if(!_3d.on) return; if(_SPIN_DIRTY){{ _SPIN_DIRTY=false; var u=_photoMockupURL(); if(u) im.src=u; }} requestAnimationFrame(_w); }})();
 }}
 // Flat real-photo mockup (poster / tee / tote): design composited into the
 // photo's print area. '' when no usable photo is registered/loaded.
 function _photoMockupURL(){{
   var spec=_mockSpec(); if(!spec||spec.cyl) return '';
   var base=_mockImg(); if(!base) return '';
   var cv=document.getElementById('mcanvas'); if(!cv) return '';
   var snap=_designSnap(); if(!snap) return '';
   var b=(typeof APPAREL_BOUND!=='undefined'&&APPAREL_BOUND)?APPAREL_BOUND
     :{{x:cv.width*0.2,y:cv.height*0.2,w:cv.width*0.6,h:cv.height*0.5}};
   var W=base.naturalWidth,H=base.naturalHeight;
   var oc=document.createElement('canvas'); oc.width=W; oc.height=H;
   var x=oc.getContext('2d'); x.drawImage(base,0,0,W,H);
   var ax=spec.area[0]*W, ay=spec.area[1]*H, aw=spec.area[2]*W, ah=spec.area[3]*H;
   var dar=(b.w>0&&b.h>0)?(b.w/b.h):1, car=aw/ah, dw,dh;
   if(dar>car){{ dw=aw; dh=dw/dar; }} else {{ dh=ah; dw=dh*dar; }}
   try{{ x.drawImage(snap,b.x,b.y,b.w,b.h, ax+(aw-dw)/2, ay+(ah-dh)/2, dw, dh); }}catch(e){{}}
   try{{ return oc.toDataURL('image/png'); }}catch(e){{ return ''; }}
 }}
 function _drawCalField(ctx,x,y,w,h){{
   ctx.save(); ctx.fillStyle='#fbfaf7'; ctx.fillRect(x,y,w,h);
   ctx.strokeStyle='rgba(0,0,0,.12)'; ctx.lineWidth=2; ctx.strokeRect(x,y,w,h);
   ctx.fillStyle='rgba(0,0,0,.28)';                                   // spiral-binding cue (top)
   for(var i=0;i<10;i++){{ var cxp=x+w*(0.08+i*0.092); ctx.beginPath(); ctx.arc(cxp,y+Math.max(6,h*0.02),Math.max(2,w*0.012),0,7); ctx.fill(); }}
   ctx.restore(); }}
 function _isLight(c){{ c=(c||'').replace('#',''); if(c.length===3) c=c[0]+c[0]+c[1]+c[1]+c[2]+c[2];
   var n=parseInt(c||'0',16), r=(n>>16)&255, g=(n>>8)&255, b=n&255;
   return (0.299*r+0.587*g+0.114*b)>150; }}
 // Curved-text engine: draw `text` along a circle centred (cx,cy), radius r,
 // centred on midDeg. sweep=+1 -> top arc (reads clockwise, glyphs upright
 // outside the ring); sweep=-1 -> bottom arc (glyphs rotated 180 to read upright
 // below). Advances the angle per glyph by its measured width. Powers the badge,
 // wraparound, adventure and back-print layouts.
 function drawArcText(ctx,text,cx,cy,r,midDeg,sweep,font,size,color,ls){{
   text=(text||'').toString(); if(!text||r<=0) return; ls=ls||0;
   ctx.save(); ctx.fillStyle=color; ctx.textAlign='center'; ctx.textBaseline='middle';
   ctx.font='700 '+size+'px '+font;
   var widths=[],total=0,i;
   for(i=0;i<text.length;i++){{ var w=ctx.measureText(text[i]).width+ls; widths.push(w); total+=w; }}
   var totalAngle=total/r;                        // radians the word subtends
   var a=(midDeg*Math.PI/180) - sweep*totalAngle/2;
   for(var j=0;j<text.length;j++){{
     var aw=widths[j]/r; a+=sweep*aw/2;
     var x=cx+Math.cos(a)*r, y=cy+Math.sin(a)*r;
     ctx.save(); ctx.translate(x,y);
     ctx.rotate(a + (sweep>0?Math.PI/2:-Math.PI/2));
     ctx.fillText(text[j],0,0); ctx.restore();
     a+=sweep*aw/2;
   }}
   ctx.restore();
 }}
 // Render the selected layout inside the print bound b={{x,y,w,h}}: decorations,
 // then each text slot (arc via drawArcText, else a centred/aligned line) sized by
 // the slot weight. The logo (PHOTO) is already composited by drawArt above.
 // Photo Collage: cover-fit each uploaded photo into its quadrant of the 2x2 grid
 // (same geometry as the 'collage' decoration frames, which overlay as borders).
 function _drawCollage(ctx,b){{
   const cx=b.x+b.w/2, cy=b.y+b.h/2, R=Math.min(b.w,b.h), g=R*0.02;
   const quad=[[0,0],[1,0],[0,1],[1,1]];
   for(var i=0;i<4;i++){{ var im=COLLAGE[i]; if(!im||!im.complete||!im.naturalWidth) continue;
     var p=quad[i];
     var rx=(p[0]?cx+g:b.x+b.w*0.10), ry=(p[1]?cy+g:b.y+b.h*0.10), rw=b.w*0.40-g, rh=b.h*0.40-g;
     ctx.save(); ctx.beginPath(); ctx.rect(rx,ry,rw,rh); ctx.clip();
     var cover=Math.max(rw/im.naturalWidth, rh/im.naturalHeight);
     var dw=im.naturalWidth*cover, dh=im.naturalHeight*cover;
     ctx.drawImage(im, rx+(rw-dw)/2, ry+(rh-dh)/2, dw, dh); ctx.restore();
   }}
 }}
 function _drawLayout(ctx,b){{
   if(!b) return; const L=_layout(CURLAYOUT); if(!L||L.key==='freeform') return;
   const R=Math.min(b.w,b.h), ink=SELTXT||'#1c1c1e', font=L.defaultFont||SELFONT;
   if(L.key==='collage') _drawCollage(ctx,b);     // photos first; frames overlay them
   (L.decor||[]).forEach(function(d){{ _decor(ctx,d,b,ink); }});
   // EDITOR-ONLY drop-zone: when a layout reserves a spot for the buyer's photo/logo
   // and none is added yet, SAY so - so the centre never reads as a mystery empty
   // box. Drawn under the wording, and skipped in the clean/proof render so it NEVER
   // prints. (Monogram uses initials, not a logo, so it has no drop-zone.)
   var _lg=L.logo, _clearCentre = _lg && (_lg.scale||0)>=0.2 && (L.slots||[]).every(function(s){{
     if(s.kind!=='line') return true;                 // arcs hug the rim, never the centre
     var sy=(s.y==null?0.5:s.y), sx=(s.x==null?0.5:s.x);
     return (Math.abs(sy-_lg.cy) > _lg.scale*0.6) || (Math.abs(sx-_lg.cx) > _lg.scale*0.6);
   }});
   if(!_CLEAN && L.key!=='collage' && _clearCentre
       && !(PHOTO&&PHOTO.complete&&PHOTO.naturalWidth)){{
     var pr=R*(L.logo.scale||0.3)*0.6, pcx=b.x+b.w*L.logo.cx, pcy=b.y+b.h*L.logo.cy;
     ctx.save(); ctx.strokeStyle='rgba(120,120,120,.9)'; ctx.fillStyle='rgba(110,110,110,.95)';
     ctx.lineWidth=Math.max(1.4,R*0.006); ctx.setLineDash([Math.max(3,R*0.024),Math.max(2,R*0.018)]);
     ctx.strokeRect(pcx-pr,pcy-pr,pr*2,pr*2); ctx.setLineDash([]);
     ctx.beginPath();                                    // little photo glyph
     ctx.moveTo(pcx-pr*0.36,pcy+pr*0.04); ctx.lineTo(pcx-pr*0.06,pcy-pr*0.34);
     ctx.lineTo(pcx+pr*0.14,pcy-pr*0.08); ctx.lineTo(pcx+pr*0.34,pcy-pr*0.30);
     ctx.lineTo(pcx+pr*0.36,pcy+pr*0.04); ctx.stroke();
     ctx.beginPath(); ctx.arc(pcx-pr*0.20,pcy-pr*0.30,pr*0.08,0,7); ctx.stroke();
     ctx.font='600 '+Math.max(9,pr*0.22)+"px 'Montserrat',sans-serif";
     ctx.textAlign='center'; ctx.textBaseline='middle';
     ctx.fillText('Add your photo',pcx,pcy+pr*0.52);
     ctx.fillText('or logo here',pcx,pcy+pr*0.52+Math.max(10,pr*0.26));
     ctx.restore();
   }}
   (L.slots||[]).forEach(function(s){{
     var txt=_slot(s.slot); if(!txt) return;
     var size=Math.max(11, R*(s.weight||0.07));
     var t=s.caps?txt.toUpperCase():txt;
     var o=_loff(s.slot);                              // buyer's per-element nudge
     if(s.kind==='arc'){{
       drawArcText(ctx,t, b.x+b.w*(s.cx+o.dx), b.y+b.h*(s.cy+o.dy), R*s.r, s.midAngle, s.sweep, font, size, ink, size*0.06);
     }} else {{
       ctx.save(); ctx.fillStyle=ink; ctx.font='700 '+size+'px '+font;
       ctx.textAlign=s.align||'center'; ctx.textBaseline='middle';
       ctx.fillText(t, b.x+b.w*((s.x==null?0.5:s.x)+o.dx), b.y+b.h*(s.y+o.dy)); ctx.restore();
     }}
   }});
 }}
 // Decorations drawn in the ink colour inside the print bound b. Kept simple and
 // print-safe (everything stays within b).
 function _decor(ctx,kind,b,ink){{
   const cx=b.x+b.w/2, cy=b.y+b.h/2, R=Math.min(b.w,b.h);
   ctx.save(); ctx.strokeStyle=ink; ctx.fillStyle=ink; ctx.lineWidth=Math.max(2,R*0.012);
   if(kind==='ring'){{ ctx.beginPath(); ctx.arc(cx,cy,R*0.47,0,7); ctx.stroke(); }}
   else if(kind==='doublering'){{ ctx.beginPath(); ctx.arc(cx,cy,R*0.47,0,7); ctx.stroke();
     ctx.lineWidth=Math.max(1,R*0.006); ctx.beginPath(); ctx.arc(cx,cy,R*0.42,0,7); ctx.stroke(); }}
   else if(kind==='border'){{ ctx.strokeRect(b.x+b.w*0.06,b.y+b.h*0.06,b.w*0.88,b.h*0.88); }}
   else if(kind==='rule'){{ ctx.beginPath(); ctx.moveTo(b.x+b.w*0.3,cy); ctx.lineTo(b.x+b.w*0.7,cy); ctx.stroke(); }}
   else if(kind==='waves'){{ ctx.lineWidth=Math.max(2,R*0.01);
     for(var k=0;k<2;k++){{ var yy=cy+R*(0.14+k*0.07); ctx.beginPath();
       for(var wx=b.x+b.w*0.30;wx<=b.x+b.w*0.70;wx+=2){{ var yo=Math.sin((wx-b.x)/(b.w*0.05))*R*0.02;
         (wx===b.x+b.w*0.30)?ctx.moveTo(wx,yy+yo):ctx.lineTo(wx,yy+yo); }} ctx.stroke(); }} }}
   else if(kind==='banner'){{ var bw=b.w*0.5,bh=b.h*0.12,bx=cx-bw/2,by=cy+R*0.18;
     ctx.lineWidth=Math.max(1.5,R*0.01); ctx.strokeRect(bx,by,bw,bh); }}  // ribbon outline, not a solid empty box
   else if(kind==='shield'){{ ctx.beginPath();
     ctx.moveTo(cx,b.y+b.h*0.12); ctx.lineTo(b.x+b.w*0.82,b.y+b.h*0.30);
     ctx.lineTo(b.x+b.w*0.82,b.y+b.h*0.62); ctx.lineTo(cx,b.y+b.h*0.88);
     ctx.lineTo(b.x+b.w*0.18,b.y+b.h*0.62); ctx.lineTo(b.x+b.w*0.18,b.y+b.h*0.30);
     ctx.closePath(); ctx.stroke(); }}
   else if(kind==='hexagon'){{ ctx.beginPath();
     for(var i=0;i<6;i++){{ var ah=Math.PI/180*(60*i-90), hx=cx+Math.cos(ah)*R*0.46, hy=cy+Math.sin(ah)*R*0.46;
       i?ctx.lineTo(hx,hy):ctx.moveTo(hx,hy); }} ctx.closePath(); ctx.stroke(); }}
   else if(kind==='stars'){{ for(var s=-1;s<=1;s++){{ _star(ctx,cx+s*R*0.16,cy+R*0.30,R*0.03,ink); }} }}
   else if(kind==='monogram'){{ ctx.beginPath(); ctx.arc(cx,cy,R*0.34,0,7); ctx.stroke(); }}
   else if(kind==='collage'){{ var g=R*0.02;
     [[0,0],[1,0],[0,1],[1,1]].forEach(function(p){{ ctx.strokeRect(
       (p[0]?cx+g:b.x+b.w*0.10), (p[1]?cy+g:b.y+b.h*0.10), b.w*0.40-g, b.h*0.40-g); }}); }}
   ctx.restore();
 }}
 function _star(ctx,cx,cy,r,ink){{ ctx.save(); ctx.fillStyle=ink; ctx.beginPath();
   for(var i=0;i<10;i++){{ var rr=i%2?r*0.45:r, a=Math.PI/180*(36*i-90);
     var x=cx+Math.cos(a)*rr, y=cy+Math.sin(a)*rr; i?ctx.lineTo(x,y):ctx.moveTo(x,y); }}
   ctx.closePath(); ctx.fill(); ctx.restore(); }}
 // Cache loaded product-mockup images; redraw once a new one finishes loading.
 let _MOCKUP_IMG={{}};
 function _mockupImg(url){{
   if(_MOCKUP_IMG[url]) return _MOCKUP_IMG[url];
   var img=new Image(); img.onload=function(){{ drawArt(); }}; img.onerror=function(){{}};
   img.src=url; _MOCKUP_IMG[url]=img; return img;
 }}
 function drawArt(){{
   const cv=document.getElementById('mcanvas'); if(!cv) return;
   if(!_SNAPPING) _SPIN_DIRTY=true;   // a real edit -> the open spin re-renders live
   if(typeof _preloadMock==='function') _preloadMock();   // warm the real-photo mockup (cheap, idempotent)
   const ctx=cv.getContext('2d'), W=cv.width, H=cv.height;
   // Real product mockup (go-live): show the ACTUAL garment photo in the selected
   // colour as the preview, with the design composited on its chest. Falls back to
   // the recolouring silhouette when no mockup is available (TEST_MODE / not live).
   const _mg=document.getElementById('mgarment');
   let _mock=null;
   if(IS_APPAREL){{
     const _gid=APPGID[CURGARMENT]||'';
     const _bgid=_gid.replace(/_(value|premium)$/,'');   // tiers share the Classic photo
     const _side=(APPLACEMENT==='back')?'back':'front';
     // Go-live per-colour photo wins for the FRONT. The single per-garment side
     // photo is colour-AGNOSTIC (one white studio shot), so it may ONLY stand in
     // when real per-colour photos exist for this garment; otherwise it would show
     // the same white tee for every colour. Without per-colour photos we fall
     // through to the recolouring silhouette (drawGarment) so the colour swatch
     // actually changes the shirt - and the buyer can still design the BACK.
     const _hasColorPhotos=!!(APPAREL_COLOR_IMG[_gid]&&Object.keys(APPAREL_COLOR_IMG[_gid]).length);
     let _u=(_side==='front')?_tileColorUrl(_gid,(CURFMT.split(' - ')[1]||'')):'';
     if(!_u && _hasColorPhotos){{ const _sm=APPAREL_SIDE_IMG[_gid]||APPAREL_SIDE_IMG[_bgid]; _u=(_sm&&_sm[_side])||''; }}
     if(_u){{ const _i=_mockupImg(_u); if(_i&&_i.complete&&_i.naturalWidth) _mock=_u; }}
   }} else if(IS_MUG||IS_BRANDED||IS_CAL){{
     // Same go-live path as apparel, now for mug / branded / calendar: when the
     // real tile photo is available, the design sits on the REAL product (the buyer
     // drags it where they want, exactly like a tee); else the generated field.
     const _bs=(typeof _mockBase==='function')?_mockBase():null;
     if(_bs && _bs.front){{ const _i=_mockupImg(_bs.front);
       if(_i&&_i.complete&&_i.naturalWidth) _mock=_bs.front; }}
   }}
   if(_mock){{
     if(_mg){{ if(_mg.getAttribute('src')!==_mock) _mg.setAttribute('src',_mock); _mg.style.display='block'; }}
     ctx.clearRect(0,0,W,H);                  // transparent so the mockup image shows
   }} else {{
     if(_mg) _mg.style.display='none';
     ctx.fillStyle = (IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL) ? '#e9e6df' : SELWALL; ctx.fillRect(0,0,W,H);  // studio / room
   }}
   const m=16, spec = (IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL) ? null : frameSpec();
   const ar=_printAR(), AW=W-2*m, AH=H-2*m;
   let w,h; if(AW/AH > ar){{ h=AH; w=AH*ar; }} else {{ w=AW; h=AW/ar; }}
   let x=(W-w)/2, y=(H-h)/2;
   if(!_mock){{ ctx.fillStyle="rgba(0,0,0,.18)"; ctx.fillRect(x+5,y+6,w,h); }}  // shadow (not in real-mockup mode)
   if(IS_CAL){{                               // PORTRAIT white-paper cover + movable print frame
     if(!_mock) _drawCalField(ctx,x,y,w,h);   // real photo backdrop wins when present
     const b=_placeBoundMock(W,H); x=b.x; y=b.y; w=b.w; h=b.h; APPAREL_BOUND=b;
   }} else if(IS_MUG){{                         // white ceramic body + movable print frame
     if(!_mock) _drawMugField(ctx,x,y,w,h);
     const b=_placeBoundMock(W,H); x=b.x; y=b.y; w=b.w; h=b.h; APPAREL_BOUND=b;
   }} else if(IS_BRANDED){{                     // flat product field + movable print frame
     if(!_mock) _drawBrandedField(ctx,x,y,w,h);
     const b=_placeBoundMock(W,H); x=b.x; y=b.y; w=b.w; h=b.h; APPAREL_BOUND=b;
   }} else if(IS_APPAREL){{
     if(_mock){{                              // design sits on the real mockup, per placement
       const b=_placeBoundMock(W,H); x=b.x; y=b.y; w=b.w; h=b.h; APPAREL_BOUND=b;
     }} else {{
       drawGarment(ctx,x,y,w,h);
       const b=_placeBound(x,y,w,h); x=b.x; y=b.y; w=b.w; h=b.h; APPAREL_BOUND=b;
     }}
   }} else if(spec){{ const t=spec.t*w;
     ctx.fillStyle=spec.color; ctx.fillRect(x,y,w,h);          // frame
     x+=t; y+=t; w-=2*t; h-=2*t;
     if(spec.mat){{ const mm=0.05*w; ctx.fillStyle="#f7f5ef";
       ctx.fillRect(x,y,w,h); x+=mm; y+=mm; w-=2*mm; h-=2*mm; }}
   }}
   if(!(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL)){{ ctx.fillStyle=SELBG; ctx.fillRect(x,y,w,h); }}  // art background (wall-art only)
   if(PHOTO && PHOTO.complete && PHOTO.naturalWidth){{        // uploaded photo
     const iw=PHOTO.naturalWidth, ih=PHOTO.naturalHeight;
     ctx.save(); ctx.beginPath(); ctx.rect(x,y,w,h); ctx.clip();
     if(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL){{
       // APPAREL/BRANDED/MUG: the photo is a PLACEABLE element - CONTAIN-fit x size, centred at
       // a free position, so the buyer can SHRINK it (PHOTO_ZOOM 0.2..3) and MOVE it
       // anywhere in the print area instead of it always filling the garment.
       const fit=Math.min(w/iw, h/ih)*PHOTO_ZOOM;
       const dw=iw*fit, dh=ih*fit;
       const cxp=x+_clamp(PHOTO_FX,0,1)*w, cyp=y+_clamp(PHOTO_FY,0,1)*h;
       ctx.drawImage(PHOTO, cxp-dw/2, cyp-dh/2, dw, dh);
       PHOTO_RECT={{x:cxp-dw/2,y:cyp-dh/2,w:dw,h:dh}};
     }} else {{
       // WALL ART: a framed print FILLS the frame (cover + bleed + zoom-in pan).
       const cover=Math.max(w/iw, h/ih)*1.25*PHOTO_ZOOM;
       const dw=iw*cover, dh=ih*cover;
       let dx=(x+w/2)-PHOTO_FX*dw, dy=(y+h/2)-PHOTO_FY*dh;
       dx=Math.min(x, Math.max(x+w-dw, dx));                  // keep frame covered
       dy=Math.min(y, Math.max(y+h-dh, dy));
       ctx.drawImage(PHOTO,dx,dy,dw,dh);
       ctx.fillStyle="rgba(0,0,0,.32)"; ctx.fillRect(x,y,w,h);  // scrim for wording
     }}
     ctx.restore();
   }}
   ART={{x:x,y:y,w:w,h:h}};                                    // for drag hit-testing
   // Layout Studio: a chosen preset arranges the slots; freeform keeps the single block.
   if((IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL) && CURLAYOUT!=='freeform'){{ _drawLayout(ctx,APPAREL_BOUND); }} else {{
   const typed=(document.getElementById('mtext')||{{}}).value;
   const text=(typed&&typed.trim())?typed.trim():CURQUOTE;
   ctx.fillStyle=SELTXT; ctx.textAlign='center';
   // When text is rotated sideways (~90/270), wrap to the frame HEIGHT and fit
   // the stacked lines to the WIDTH, so sideways wording reads cleanly.
   const ra=Math.abs(((TROT%180)+180)%180);
   const sideways=(ra>45 && ra<135);
   const wrapDim=sideways?h:w, stackDim=sideways?w:h;
   const maxW=wrapDim*0.84;
   function wrap(f){{ctx.font='600 '+f+'px '+SELFONT;
     const words=text.split(/\\s+/); let lines=[],cur='';
     for(const wd of words){{const tt=(cur+' '+wd).trim();
       if(ctx.measureText(tt).width<=maxW){{cur=tt;}}else{{lines.push(cur);cur=wd;}}}}
     if(cur)lines.push(cur); return lines;}}
   let fs, lines;
   if(TSIZE>0){{ fs=Math.max(9, Math.round(stackDim*TSIZE/100)); lines=wrap(fs);  // manual...
     while((lines.length*fs*1.32)>stackDim*0.96 && fs>9){{fs-=1; lines=wrap(fs);}} }}  // ...but capped to the print area
   else {{ fs=Math.round(stackDim*0.10); lines=wrap(fs);                      // auto-fit
     while((lines.length*fs*1.32)>stackDim*0.82 && fs>9){{fs-=1; lines=wrap(fs);}} }}
   const lh=fs*1.34; const block=lines.length*lh;
   const ax=x+TPOS.x*w, ay=y+TPOS.y*h;                         // anchor (draggable)
   ctx.save(); ctx.translate(ax,ay);
   if(TROT) ctx.rotate(TROT*Math.PI/180);                      // rotate the wording
   let ty=-block/2+fs*0.9;
   // Over a photo, give the wording a contrasting outline so it stays legible on
   // ANY part of the image (a dark scene would otherwise swallow dark text).
   const overPhoto=!!(PHOTO && PHOTO.complete && PHOTO.naturalWidth);
   if(overPhoto){{ ctx.lineJoin='round'; ctx.lineWidth=Math.max(2,fs*0.16);
     ctx.strokeStyle = _isLight(SELTXT) ? 'rgba(0,0,0,.78)' : 'rgba(255,255,255,.92)'; }}
   for(const ln of lines){{ if(overPhoto) ctx.strokeText(ln,0,ty); ctx.fillText(ln,0,ty); ty+=lh; }}
   ctx.restore();
   }}
   // Optional shop-logo overlay (front & back) - a small brand mark below the
   // design. Drawn on whichever side is in view, since the toggle adds it to both.
   if(IS_APPAREL && LOGO_ON && GARMENT_LOGO_SRC){{
     const _lg=_mockupImg(GARMENT_LOGO_SRC);
     if(_lg&&_lg.complete&&_lg.naturalWidth){{
       const _lw=W*0.12, _lh=_lw*(_lg.naturalHeight/_lg.naturalWidth);
       ctx.save(); ctx.globalAlpha=0.96;
       ctx.drawImage(_lg, W/2-_lw/2, H*0.60, _lw, _lh); ctx.restore();
     }}
   }}
   if((IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL) && APPAREL_BOUND && !_CLEAN){{ const b=APPAREL_BOUND;
     ctx.save(); ctx.setLineDash([6,5]); ctx.strokeStyle='rgba(0,0,0,.55)'; ctx.lineWidth=1.5;
     ctx.strokeRect(b.x,b.y,b.w,b.h); ctx.setLineDash([]);
     const hs=9;
     function _handle(cx,cy,col){{ ctx.fillStyle=col; ctx.fillRect(cx-hs,cy-hs,hs*2,hs*2);
       ctx.strokeStyle='#fff'; ctx.lineWidth=2; ctx.strokeRect(cx-hs,cy-hs,hs*2,hs*2); }}
     // FRAME resize handle (green, bottom-LEFT) - sizes the whole design.
     _handle(b.x, b.y+b.h, '#15643c');
     // PHOTO resize handle (blue, bottom-RIGHT of the photo) - sizes just the photo.
     if(PHOTO && PHOTO_RECT){{ _handle(PHOTO_RECT.x+PHOTO_RECT.w, PHOTO_RECT.y+PHOTO_RECT.h, '#1763b8'); }}
     ctx.fillStyle='rgba(0,0,0,.62)'; ctx.font="600 12px 'Montserrat',sans-serif"; ctx.textAlign='center';
     const _cap=IS_CAL ? '📅 Cover area - drag to move · green corner to resize'
       : (IS_MUG ? '🍵 Print area - drag to move · green corner to resize'
       : (IS_BRANDED ? '🎁 Print area - drag to move · green corner to resize'
       : ('👕 '+(_PLACE_LBL[APPLACEMENT]||'Front')+' - drag to move · green corner to resize')));
     ctx.fillText(_cap, b.x+b.w/2, b.y-7); ctx.restore(); }}
   const crop=document.getElementById('mcrop');
   if(crop){{ const sv=((document.getElementById('msize')||{{}}).value||'').split('|')[0];
     crop.textContent = IS_CAL
       ? (sv?`📅 Calendar cover preview - ${{sv}} (your design stays inside the dashed area)`:"📅 Calendar cover preview")
       : (IS_MUG
       ? (sv?`🍵 Mug preview - ${{sv}} (your design stays inside the dashed area)`:"🍵 Mug preview")
       : (IS_BRANDED
       ? (sv?`🎁 Product preview - size ${{sv}} (your design stays inside the dashed area)`:"🎁 Product preview")
       : (IS_APPAREL
       ? (sv?`👕 Garment preview - size ${{sv}} (your design stays inside the dashed area)`:"👕 Garment preview")
       : (sv?`📐 Final print preview - actual ${{sv}}\" crop`+(PHOTO?" (photo auto-fit to frame)":"")
           : "📐 Final print preview")))); }}
   saveDraft(); updateReview();
 }}
 // ── Single-item review: show exactly what you're adding, before you add ──
 function updateReview(){{
   const r=document.getElementById('mreview'); if(!r) return;
   const typed=((document.getElementById('mtext')||{{}}).value||'').trim();
   const words=typed || CURQUOTE || '(your wording)';
   const fmt=CURFMT || ((DATA[CUR]&&DATA[CUR].formats&&DATA[CUR].formats[0])?DATA[CUR].formats[0].name:'');
   const sv=((document.getElementById('msize')||{{}}).value||'').split('|');
   const size=sv[0] ? sv[0]+' in' : 'choose a size';
   const src=typed ? '' : ' <span class="rvtag">suggested wording</span>';
   r.innerHTML=`<div class="rvh">Review before adding:</div>`+
     `<div class="rvbody"><b>${{fmt}}</b> &middot; ${{size}} &middot; `+
     `&ldquo;${{words.slice(0,90)}}${{words.length>90?'&hellip;':''}}&rdquo;${{src}}</div>`;
 }}
 // ── Abandoned-customization save/restore ──
 let DRAFT_T=null;
 function _draftState(){{
   const typed=(document.getElementById('mtext')||{{}}).value||'';
   return {{i:CUR, fmt:CURFMT, bg:SELBG, txt:SELTXT, font:SELFONT, wall:SELWALL,
            wording:typed, photo:!!(document.getElementById('mupload')||{{}}).value}};
 }}
 function saveDraft(){{
   if(document.getElementById('modal').style.display!=='flex') return;
   const s=_draftState();
   if(!s.wording && !s.photo && s.fmt===((DATA[CUR]&&DATA[CUR].formats&&DATA[CUR].formats[0])?DATA[CUR].formats[0].name:'')) {{
     // nothing meaningful customized yet - still remember the open design locally
   }}
   try{{localStorage.setItem('jf_draft', JSON.stringify(s));}}catch(e){{}}
   // debounced server save (only when we know who they are)
   const email=knownEmail();
   if(email && CUSTOMIZE_API){{
     clearTimeout(DRAFT_T);
     DRAFT_T=setTimeout(function(){{
       fetch(CUSTOMIZE_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
         body:JSON.stringify({{email:email, listing:(DATA[s.i]||{{}}).title||'',
           material:s.fmt, wording:s.wording, has_photo:s.photo,
           state_json:s}})}}).catch(function(){{}});
     }}, 1200);
   }}
 }}
 function resumeDraft(){{
   let s=null; try{{s=JSON.parse(localStorage.getItem('jf_draft')||'null');}}catch(e){{}}
   if(!s||typeof s.i!=='number'||!DATA[s.i]) return;
   openM(s.i);
   if(s.fmt && DATA[s.i].formats){{const j=DATA[s.i].formats.findIndex(f=>f.name===s.fmt);
     if(j>=0) pickFmt(s.i,j);}}
   if(s.bg)SELBG=s.bg; if(s.txt)SELTXT=s.txt; if(s.font)SELFONT=s.font; if(s.wall)SELWALL=s.wall;
   const mt=document.getElementById('mtext'); if(mt&&s.wording){{mt.value=s.wording; onText();}}
   renderBg(); renderTxt(); renderWall(); renderFonts(); drawArt();
   const b=document.getElementById('resumeBar'); if(b)b.style.display='none';
 }}
 (function(){{
   let s=null; try{{s=JSON.parse(localStorage.getItem('jf_draft')||'null');}}catch(e){{}}
   if(s && typeof s.i==='number' && DATA[s.i] && (s.wording||s.photo)){{
     window.addEventListener('DOMContentLoaded',function(){{
       const b=document.getElementById('resumeBar'); if(b)b.style.display='flex';}});
   }}
 }})();
 function pickFmt(i,j){{
   const f = curFormats(i)[j];   // apparel colour chips OR wall-art frames
   if(f.price) document.getElementById('mprice').textContent = "from $" + f.price;
   document.querySelectorAll('#mfchips .fchip').forEach((e,k)=>
     e.classList.toggle('sel', k===j));
   CURFMT = f.name; drawArt(); fillSizes();   // update sizes for this format
   promptSizeQty();                  // frame picked -> move them to size & qty
 }}
 function b2bSend(to){{
   const g=id=>(document.getElementById(id)||{{}}).value||'';
   const body=encodeURIComponent(
     "Name: "+g('bz_name')+"\\nCompany: "+g('bz_co')+"\\nEmail: "+g('bz_email')+
     "\\nQuantity: "+g('bz_qty')+"\\n\\nDetails:\\n"+g('bz_msg'));
   window.location.href="mailto:"+to+"?subject="+
     encodeURIComponent("Wholesale / bulk gifting inquiry")+"&body="+body;
 }}
 function continueShopping(){{
   // Close the editor and land the buyer back on the design grid.
   closeM();
   var g=document.getElementById('grid');
   if(g) g.scrollIntoView({{behavior:'smooth',block:'start'}});
 }}
 // Esc closes ONLY the topmost open overlay - never cascade. Cascading lost the
 // editor design behind the proof popup, skipped the flipbook, and (because
 // closeExit() always runs _exitDone) a stray Esc permanently suppressed exit-intent
 // email capture. Close the highest-priority visible overlay and stop.
 document.addEventListener('keydown', function(e){{
   if(e.key!=='Escape') return;
   var _vis=function(id){{ var el=document.getElementById(id); return !!(el && el.style.display && el.style.display!=='none'); }};
   if(_vis('proofPop')){{ try{{ closeProof(); }}catch(_e){{}} return; }}
   if(_vis('flipPop')){{ try{{ closeFlipbook(); }}catch(_e){{}} return; }}
   if(_vis('exitpop')){{ try{{ closeExit(); }}catch(_e){{}} return; }}
   if(_vis('quiz')){{ try{{ closeQuiz(); }}catch(_e){{}} return; }}
   if(_vis('basketPanel')){{ try{{ closeBasket(); }}catch(_e){{}} return; }}
   if(_vis('modal')){{ try{{ closeM(); }}catch(_e){{}} return; }}
 }});
 // Keyboard-operate role=button spans (close x, fchips, step links) with Enter/Space.
 document.addEventListener('keydown', function(e){{
   if(e.key!=='Enter' && e.key!==' ' && e.key!=='Spacebar') return;
   var el=document.activeElement;
   if(!el) return;
   var tag=el.tagName;
   if(tag==='BUTTON'||tag==='A'||tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT') return;
   if(el.classList.contains('fchip') || el.getAttribute('role')==='button'){{
     e.preventDefault(); el.click();
   }}
 }});
 function closeM(){{document.getElementById('modal').style.display='none';
   BFLOW=null; var bb=document.getElementById('bundlebanner'); if(bb)bb.style.display='none';}}
 document.querySelectorAll('#mstars span').forEach(function(el){{
   el.addEventListener('click', function(){{ setRating(parseInt(el.dataset.v)); }});
 }});
 render();

 // ── Gift Finder quiz ──
 const QUIZ = {quiz_json};
 function _fill(id, arr, val, lbl){{
   const s=document.getElementById(id); if(!s)return;
   s.innerHTML=arr.map(o=>{{const v=val?o[val]:o, t=lbl!==undefined?o[lbl]:o;
     return `<option value="${{v}}">${{t}}</option>`;}}).join('');
 }}
 function openQuiz(){{
   _fill('q_rel', QUIZ.relationships); _fill('q_occ', QUIZ.occasions);
   _fill('q_bud', QUIZ.budgets, 0, 1); _fill('q_sty', QUIZ.styles, 0, 1);
   document.getElementById('qresult').style.display='none';
   document.getElementById('quiz').style.display='flex';
 }}
 function closeQuiz(){{document.getElementById('quiz').style.display='none';}}
 function runQuiz(){{
   const rel=document.getElementById('q_rel').value;
   const occ=document.getElementById('q_occ').value;
   const bud=document.getElementById('q_bud').value;
   const sty=document.getElementById('q_sty').value;
   const matMap={{under50:'Poster',"50to100":'Framed',"100plus":'Acrylic'}};
   const material=matMap[bud]||'Framed';
   const styRow=(QUIZ.styles||[]).find(s=>s[0]===sty)||['','Classic','Premium Solid Oak'];
   // best-matching product by relationship + occasion
   let bi=0, bs=-1;
   DATA.forEach((d,i)=>{{let sc=0; const t=(d.full_title||'').toLowerCase();
     if(rel && t.indexOf(rel.toLowerCase())>=0) sc+=2;
     if(occ && t.indexOf(occ.toLowerCase())>=0) sc+=2;
     if(sc>bs){{bs=sc; bi=i;}}}});
   const r=document.getElementById('qresult');
   r.style.display='block';
   r.innerHTML=`<h3>Our pick for your ${{rel}}'s ${{occ}}</h3>`+
     `<p><b>${{DATA[bi].title}}</b><br>Material: ${{material}}`+
     (material==='Framed'?` &middot; Frame: ${{styRow[2]}}`:``)+
     `<br>Style: ${{styRow[1]}} &middot; add your own words at checkout.</p>`+
     `<button class="qgo" onclick="closeQuiz();openM(${{bi}})">View this gift &rarr;</button>`;
 }}

 // ── Bundle builder ──
 const BSEL=new Set();
 function renderBundle(){{
   const g=document.getElementById('bgrid'); if(!g)return;
   g.innerHTML=DATA.map((d,i)=>
     `<div class="bopt ${{BSEL.has(i)?'sel':''}}" onclick="toggleBundle(${{i}})" `+
     `title="Tap to add this design to your gallery set">`+
     `<span class="bcheck">${{BSEL.has(i)?'✓':'+'}}</span>`+
     `<img src="${{d.imgs[0]}}" loading="lazy" alt="${{d.title}}"><div>${{d.title.slice(0,28)}}</div>`+
     `<div class="baddlbl">${{BSEL.has(i)?'✓ In your set':'+ Add to set'}}</div></div>`).join('');
   const n=BSEL.size; const disc=qdisc(n);
   const t=document.getElementById('btot');
   if(n===0){{ t.classList.remove('on');
     t.innerHTML='Tap designs below to build your set (2 = 8% off, 3 = 12%, 4+ = 15%).'; return; }}
   if(n===1){{ t.classList.add('on');
     t.innerHTML='<b>1 selected</b> — add 1 more to unlock 8% off your set.'; return; }}
   let base=0; BSEL.forEach(i=>base+=parseFloat(DATA[i].price));
   const total=(base*(1-disc)).toFixed(2);
   const saved=(base-total).toFixed(2);
   t.classList.add('on');
   t.innerHTML=`<span class="btotline"><b>${{n}} prints selected</b> &middot; `+
     `${{Math.round(disc*100)}}% off &middot; set from <b>$${{total}}</b> `+
     `<span class="bsave">(save $${{saved}})</span></span>`+
     `<button class="bsetbtn" onclick="startBundleFlow()">Personalize &amp; add this set &rarr;</button>`;
 }}
 function toggleBundle(i){{ if(BSEL.has(i))BSEL.delete(i); else BSEL.add(i); renderBundle(); }}
 function toggleBundleSec(){{
   const b=document.getElementById('bundleBody'), t=document.getElementById('bundleToggle');
   const open=b.style.display==='none';
   b.style.display=open?'block':'none';
   if(t)t.innerHTML=open?'Hide set builder':'Build a set &rarr;';
   if(open) b.scrollIntoView({{behavior:'smooth',block:'nearest'}});
 }}
 renderBundle();

 // ── Guided bundle personalization: craft each design BEFORE it goes to cart ──
 let BFLOW=null;
 function startBundleFlow(){{
   if(BSEL.size<2) return;
   BFLOW={{queue:Array.from(BSEL), idx:0}};
   nextBundleStep();
 }}
 function _bundleBanner(){{
   const b=document.getElementById('bundlebanner'); if(!b) return;
   if(!BFLOW){{ b.style.display='none'; return; }}
   const k=BFLOW.idx+1, N=BFLOW.queue.length;
   b.style.display='block';
   b.innerHTML=`🎨 Building your set - <b>design ${{k}} of ${{N}}</b>. `+
     `Personalize the words, frame &amp; colors, then tap <b>Add to basket</b> to continue. `+
     `<span class="bskip" onclick="skipBundleStep()">Skip this one</span>`;
 }}
 function nextBundleStep(){{
   if(!BFLOW) return;
   if(BFLOW.idx>=BFLOW.queue.length){{ finishBundleFlow(); return; }}
   openM(BFLOW.queue[BFLOW.idx]);
   _bundleBanner();
 }}
 function skipBundleStep(){{ if(!BFLOW) return; BFLOW.idx++; nextBundleStep(); }}
 function finishBundleFlow(){{
   BFLOW=null; _bundleBanner();
   const c=document.getElementById('mcart');
   if(c) c.scrollIntoView({{behavior:'smooth',block:'center'}});
   const msg=document.getElementById('mratemsg');
   if(msg) msg.textContent="Your set is ready - review each piece below, then continue to checkout.";
 }}
</script>

<div id="basketPanel" role="dialog" aria-modal="true" aria-label="Your basket" onclick="if(event.target.id==='basketPanel')toggleBasket()">
  <div class="bpbox">
    <span class="qclose" role="button" tabindex="0" aria-label="Close" onclick="toggleBasket()">&times;</span>
    <h2>🛒 Your basket</h2>
    <div id="basketLines"></div>
    <div id="basketTotal" class="bptot"></div>
    <div id="basketTaxNote" class="bptaxnote"></div>
    <button type="button" class="bpmore" id="bpmorebtn"
      onclick="toggleBasket();location.hash='#shop'">← Add another design</button>
    <div class="bpactions">
      <button class="bpclear" id="bpclearbtn" onclick="clearBasket()">Empty basket</button>
      <button class="bpco" id="bpcobtn" onclick="checkout()">Checkout &rarr;</button>
    </div>
    <p class="ftc" id="paynote">💳 <b>You never enter card details on this site.</b>
      Payment is completed via a secure payment link we send you - credit/debit
      card, PayPal, Apple Pay or Google Pay. Your personalization is attached
      to the order automatically.</p>
    <p class="ftc">Items are added as you personalize each design. Personalization &amp;
      exact layout print exactly as previewed.</p>
  </div>
</div>

<button id="toTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" aria-label="Back to top" title="Back to top">&#8593;</button>
<script>
 (function(){{ var b=document.getElementById('toTop');
   if(!b) return;
   var onScroll=function(){{ b.style.display = (window.scrollY>700)?'flex':'none'; }};
   window.addEventListener('scroll',onScroll,{{passive:true}}); onScroll();
 }})();
</script>
<button id="angeBtn" onclick="toggleAnge()">💬 Ask Ange</button>
<div id="angePanel">
  <div class="angehdr">Ask Ange<small>{SHOP_NAME} assistant - quick answers</small></div>
  <div id="angeMsgs"></div>
  <div class="achips" id="angeChips"></div>
  <div class="angein">
    <input id="angeIn" placeholder="Ask about frames, sizes, shipping..."
      onkeydown="if(event.key==='Enter')angeSend()">
    <button onclick="angeSend()">Send</button>
  </div>
</div>
<script>
 const ANGE_KB = {ange_kb_json};
 const ANGE_OWNER = "{owner}";
 const ANGE_API = "{ask_api_url}";
 // ── Exit-intent email capture ──
 const SIGNUP_API = ANGE_API ? ANGE_API.replace(/\\/ask$/,'/signup') : "";
 const CUSTOMIZE_API = ANGE_API ? ANGE_API.replace(/\\/ask$/,'/customization') : "";
 const UPLOAD_API = ANGE_API ? ANGE_API.replace(/\\/ask$/,'/upload') : "";
 const SERVICE_API = ANGE_API ? ANGE_API.replace(/\\/ask$/,'/service-request') : "";
 const DESIGN_API = ANGE_API ? ANGE_API.replace(/\\/ask$/,'/design') : "";
 const CONFIRM_API = ANGE_API ? ANGE_API.replace(/\\/ask$/,'/confirm') : "";
 function knownEmail(){{ try{{return localStorage.getItem('jf_email')||"";}}catch(e){{return "";}} }}
 // Send the photo to the server for an AI quality check + attach to the order.
 // (Server also forwards the approved JPG to the print partner by URL.) No-ops if not hosted.
 function aiCheckPhoto(file){{
   const email=knownEmail(); if(!UPLOAD_API || !email || !file) return;
   const size=((document.getElementById('msize')||{{}}).value||'18x24|0').split('|')[0];
   const fd=new FormData(); fd.append('file',file); fd.append('email',email);
   fd.append('size',size);
   const note=document.getElementById('maicheck');
   if(note)note.innerHTML='<span class="spin"></span> 🤖 AI checking photo quality…';
   fetch(UPLOAD_API,{{method:'POST',body:fd}}).then(r=>r.json()).then(function(d){{
     if(d && d.focal) applyFocal(d.focal);   // AI auto-centers the subject
     if(!note) return;
     if(d.decision==='approve') note.innerHTML='✅ AI quality check passed - good to print.';
     else note.innerHTML='⚠️ '+(d.message||'Please upload a higher-quality photo.');
   }}).catch(function(){{ if(note)note.textContent=''; }});
 }}
 // ── AI design assistant (mirrors quoteforge/ai/design_assistant.py) ──
 // Works for EVERY product, instantly + free (no server) - the deterministic review
 // + auto-arrange. The server AI vision note (aiCheckPhoto) enriches it when live.
 function _pk(){{ return (typeof IS_MUG!=='undefined'&&IS_MUG)?'mug':((typeof IS_APPAREL!=='undefined'&&IS_APPAREL)?'apparel':((typeof IS_BRANDED!=='undefined'&&IS_BRANDED)?'branded':((typeof IS_CAL!=='undefined'&&IS_CAL)?'calendar':'wallart'))); }}
 function _photoReview(w,h){{
   if(!w||!h) return {{score:0,verdict:'No image',tips:['Upload a photo to see a quality review.']}};
   var lng=Math.max(w,h), mp=Math.round(w*h/1e5)/10, score=100, tips=[];
   if(lng<1000){{ score-=45; tips.push('Low resolution ('+w+'×'+h+'px) - use a larger original for a crisp print.'); }}
   else if(lng<1600){{ score-=18; tips.push('Medium resolution - great for small prints; larger files print sharper at big sizes.'); }}
   else {{ tips.push('Sharp resolution ('+w+'×'+h+'px, '+mp+' MP).'); }}
   var PA={{mug:2.4,apparel:0.82,branded:1.0,calendar:1.33}}, tgt=PA[_pk()];
   if(!tgt){{ var iv=(((document.getElementById('msize')||{{}}).value)||'18x24').split('|')[0].split('x').map(parseFloat); if(iv.length>=2&&isFinite(iv[0])&&isFinite(iv[1])) tgt=iv[0]/iv[1]; }}
   if(tgt){{ var ar=w/h, rt=ar/tgt; if(rt>1.35||rt<0.74){{ score-=12; tips.push(ar>tgt?'Wider than the print area - the sides may crop. Zoom out or nudge to keep everyone in.':'Taller than the print area - the top or bottom may crop. Zoom out or nudge to fit.'); }} }}
   score=Math.max(0,Math.min(100,score));
   var verdict=score>=80?'Great photo':(score>=55?'Good - a couple of tips':'Use a higher-quality photo');
   return {{score:score,verdict:verdict,tips:tips}};
 }}
 function renderPhotoReview(el,w,h){{
   if(!el) return; var r=_photoReview(w,h);
   var col=r.score>=80?'#1f7a44':(r.score>=55?'#9a6a00':'#b23b3b');
   var bar='<div style="height:6px;border-radius:6px;background:#e7e3da;overflow:hidden;margin:4px 0"><div style="height:6px;width:'+r.score+'%;background:'+col+'"></div></div>';
   var tips=r.tips.map(function(t){{return '<li>'+t+'</li>';}}).join('');
   el.className='note'; el.innerHTML='<b>🤖 Smart photo review: '+r.verdict+'</b>'+bar+'<ul style="margin:.2em 0 .2em 1.1em;padding:0">'+tips+'</ul><span class="rmphoto" onclick="removePhoto()">remove</span>';
 }}
 // One-click best placement: layout + photo centring + text clear of the subject.
 function autoArrange(){{
   var w=PHOTO?(PHOTO.naturalWidth||PHOTO.width):0, h=PHOTO?(PHOTO.naturalHeight||PHOTO.height):0;
   var nlines=(((document.getElementById('mtext')||{{}}).value)||'').split(/\\n/).filter(function(s){{return s.trim();}}).length;
   if(w&&h){{ if(nlines>=1 && typeof pickLayout==='function'){{ pickLayout(w>h*1.1?'hbanner':'badge'); }}
     if(typeof autoCenterPhoto==='function') autoCenterPhoto(); }}
   else if(typeof pickLayout==='function'){{ pickLayout('freeform'); if(typeof centerText==='function') centerText(); }}
   if(typeof toast==='function') toast('✨ Auto-arranged your design.');
   if(typeof drawArt==='function') drawArt();
 }}
 // ── 3D preview (Three.js, lazy-loaded from CDN; mug/bottle/tumbler) ──────────────
 // Additive bonus view - the approved FLAT proof is still what prints. Never blocks.
 var _3d={{on:false}};
 function view3D(){{
   var wrap=document.getElementById('mug3dwrap'); if(!wrap) return;
   var img=(typeof _composedProofURL==='function')?_composedProofURL():'';
   if(!img){{ if(typeof toast==='function') toast('Add your design first.'); return; }}
   wrap.style.display='flex';
   // Cylindrical products (mug/bottle/tumbler): realistic 2D spin - real photo
   // when registered, else a clean generated body. Never a blank white cylinder.
   if((typeof _isCyl==='function')&&_isCyl()){{ _openCylSpin(); return; }}
   // Apparel has distinct FRONT and BACK designs: flip between them (each side's
   // own design) on the real photo or the silhouette - never the WebGL mirror.
   if(typeof IS_APPAREL!=='undefined' && IS_APPAREL){{ _openFlipReview(); return; }}
   // Flat products with a real photo: show the design on the actual product photo.
   var photo=(typeof _photoMockupURL==='function')?_photoMockupURL():'';
   if(photo){{ _showFlatPhoto(photo); return; }}
   _setMockTitle(false);
   var go=function(){{ _build3D(img); }};
   if(window.THREE){{ go(); return; }}
   var s=document.createElement('script');
   s.src='https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
   s.onload=go; s.onerror=function(){{ close3D(); if(typeof toast==='function') toast('3D view unavailable right now.'); }};
   document.head.appendChild(s);
 }}
 function _build3D(imgURL){{
   var mount=document.getElementById('mug3d'); if(!mount||!window.THREE) return;
   mount.innerHTML=''; var W=mount.clientWidth||340, H=mount.clientHeight||340;
   var cyl=(typeof _isCyl==='function')?_isCyl():false;
   var fmt=(typeof CURFMT!=='undefined'?CURFMT:'')||'';
   var im=new Image(); im.crossOrigin='anonymous';
   im.onerror=function(){{ if(typeof toast==='function') toast('Could not load the design for 3D.'); close3D(); }};
   im.onload=function(){{
     var scene=new THREE.Scene();
     var cam=new THREE.PerspectiveCamera(38,W/H,0.1,100); cam.position.set(0,0,7.2);
     var rnd=new THREE.WebGLRenderer({{antialias:true,alpha:true}});
     rnd.setSize(W,H); rnd.setPixelRatio(Math.min(2.5,window.devicePixelRatio||1));   // crisp on retina
     if(THREE.sRGBEncoding) rnd.outputEncoding=THREE.sRGBEncoding;
     mount.appendChild(rnd.domElement);
     // even studio lighting so the design reads clean + bright
     scene.add(new THREE.HemisphereLight(0xffffff,0x9a9a9a,0.95));
     var key=new THREE.DirectionalLight(0xffffff,0.65); key.position.set(4,5,6); scene.add(key);
     var fill=new THREE.DirectionalLight(0xffffff,0.35); fill.position.set(-4,1,3); scene.add(fill);
     // crisp, non-blurry texture (anisotropy + mipmaps + sRGB)
     var tex=new THREE.Texture(im); tex.needsUpdate=true;
     if(THREE.sRGBEncoding) tex.encoding=THREE.sRGBEncoding;
     try{{ tex.anisotropy=rnd.capabilities.getMaxAnisotropy(); }}catch(e){{ tex.anisotropy=8; }}
     tex.minFilter=THREE.LinearMipmapLinearFilter; tex.magFilter=THREE.LinearFilter; tex.generateMipmaps=true;
     var grp=new THREE.Group();
     if(cyl){{                                            // mug / bottle / tumbler
       tex.wrapS=THREE.RepeatWrapping;
       var mug=IS_MUG, rad=mug?1.35:0.95, ht=mug?2.0:3.1;
       var side=new THREE.MeshStandardMaterial({{map:tex,roughness:0.3,metalness:0.05,color:0xffffff}});
       var cap=new THREE.MeshStandardMaterial({{color:0xffffff,roughness:0.4}});
       grp.add(new THREE.Mesh(new THREE.CylinderGeometry(rad,rad,ht,96,1,false),[side,cap,cap]));
       if(mug){{ var hd=new THREE.Mesh(new THREE.TorusGeometry(0.62,0.13,20,48,Math.PI*1.15),cap);
         hd.position.set(rad+0.22,0,0); hd.rotation.y=Math.PI/2; grp.add(hd); }}
     }} else {{                                           // poster / canvas / apparel / calendar / tote: a panel
       var ar=(im.width&&im.height)?(im.width/im.height):1, S=3.4;
       var pw=ar>=1?S:S*ar, ph=ar>=1?S/ar:S;
       var thick=(IS_CAL||/canvas|frame/i.test(fmt))?0.22:0.05;     // canvas/frame have depth
       var face=new THREE.MeshStandardMaterial({{map:tex,roughness:0.45,metalness:0.02,color:0xffffff}});
       var edge=new THREE.MeshStandardMaterial({{color:/frame/i.test(fmt)?0x262626:0xf2eee5,roughness:0.6}});
       // BACK face: the SAME design, horizontally flipped so it reads correctly from
       // behind - so spinning never shows a blank white back.
       var texB=new THREE.Texture(im); texB.needsUpdate=true;
       if(THREE.sRGBEncoding) texB.encoding=THREE.sRGBEncoding;
       try{{ texB.anisotropy=rnd.capabilities.getMaxAnisotropy(); }}catch(e){{ texB.anisotropy=8; }}
       texB.minFilter=THREE.LinearMipmapLinearFilter; texB.magFilter=THREE.LinearFilter; texB.generateMipmaps=true;
       texB.wrapS=THREE.RepeatWrapping; texB.repeat.x=-1; texB.offset.x=1;
       var back=new THREE.MeshStandardMaterial({{map:texB,roughness:0.45,metalness:0.02,color:0xffffff}});
       grp.add(new THREE.Mesh(new THREE.BoxGeometry(pw,ph,thick),[edge,edge,edge,edge,face,back]));
       if(/frame/i.test(fmt)){{ var fr=new THREE.Mesh(new THREE.BoxGeometry(pw+0.3,ph+0.3,thick*0.8),edge); fr.position.z=-0.03; grp.add(fr); }}
       grp.rotation.x=-0.12;
     }}
     scene.add(grp);
     var drag=false,lx=0; var el=rnd.domElement; el.style.cursor='grab';
     el.addEventListener('mousedown',function(e){{drag=true;lx=e.clientX;el.style.cursor='grabbing';}});
     window.addEventListener('mouseup',function(){{drag=false;el.style.cursor='grab';}});
     el.addEventListener('mousemove',function(e){{ if(drag){{ grp.rotation.y+=(e.clientX-lx)*0.012; lx=e.clientX; }} }});
     el.addEventListener('touchmove',function(e){{ if(e.touches[0]){{ if(lx) grp.rotation.y+=(e.touches[0].clientX-lx)*0.012; lx=e.touches[0].clientX; }} }},{{passive:true}});
     el.addEventListener('touchend',function(){{ lx=0; }});
     _3d={{on:true}};
     (function loop(){{ if(!_3d.on) return; if(!drag) grp.rotation.y+=0.005; rnd.render(scene,cam); requestAnimationFrame(loop); }})();
   }};
   im.src=imgURL;
 }}
 function close3D(){{ var w=document.getElementById('mug3dwrap'); if(w)w.style.display='none'; _3d.on=false; }}
 // 3D suits CYLINDRICAL products: mugs + branded bottles/tumblers. CURFMT carries the
 // selected product name, so a tote/notebook never gets the 3D button.
 // 3D shape: CYLINDER for mugs/bottles/tumblers, a flat (framed) PANEL for everything
 // else. The 3D button now shows on EVERY product/department.
 function _isCyl(){{ var f=(typeof CURFMT!=='undefined'?CURFMT:'')||''; return IS_MUG || (IS_BRANDED && /bottle|tumbler/i.test(f)); }}
 function _is3D(){{ return true; }}
 function _upd3DBtn(){{ var b=document.getElementById('view3dbtn'); if(!b) return;
   b.style.display=_is3D()?'block':'none';
   // Product-accurate label: only apparel has a real front+back to flip; cylinders
   // rotate a single wrap; flat single-face goods just show on the product.
   var lbl=(typeof IS_APPAREL!=='undefined'&&IS_APPAREL)
       ? '&#128260; Spin your product &mdash; front &amp; back'
       : (((typeof _isCyl==='function')&&_isCyl()) ? '&#128260; Spin your product'
                                                   : '&#128444;&#65039; See it on your product');
   b.innerHTML=lbl; }}
 // ── Remove background (client-side, free, private - the photo never leaves the
 // browser). Samples the 4 corners to estimate the backdrop and clears matching
 // pixels - great for logos / solid backdrops. Available on EVERY product's photo. ──
 function removeBg(){{
   if(!PHOTO||!PHOTO.naturalWidth){{ if(typeof toast==='function') toast('Upload a photo or logo first.'); return; }}
   var w=PHOTO.naturalWidth, h=PHOTO.naturalHeight;
   var c=document.createElement('canvas'); c.width=w; c.height=h;
   var x=c.getContext('2d'); x.drawImage(PHOTO,0,0);
   var d; try{{ d=x.getImageData(0,0,w,h); }}catch(e){{ if(typeof toast==='function') toast('Cannot edit this image.'); return; }}
   var p=d.data, at=function(px,py){{ return (py*w+px)*4; }};
   var cs=[at(0,0),at(w-1,0),at(0,h-1),at(w-1,h-1)], br=0,bg=0,bb=0;
   cs.forEach(function(i){{ br+=p[i]; bg+=p[i+1]; bb+=p[i+2]; }}); br/=4; bg/=4; bb/=4;
   var tol=46, cut=0;
   for(var i=0;i<p.length;i+=4){{ var dr=p[i]-br, dg=p[i+1]-bg, db=p[i+2]-bb;
     if(Math.sqrt(dr*dr+dg*dg+db*db)<tol){{ p[i+3]=0; cut++; }} }}
   if(!cut){{ if(typeof toast==='function') toast('No clear background found to remove.'); return; }}
   x.putImageData(d,0,0);
   var ni=new Image(); ni.onload=function(){{ PHOTO=ni; if(typeof drawArt==='function') drawArt();
     if(typeof toast==='function') toast('✂️ Background removed.'); }};
   ni.src=c.toDataURL('image/png');
 }}
 // ── Automated A/B testing ──
 const AB_EXPERIMENTS = {ab_json};
 const AB_API = ANGE_API ? ANGE_API.replace(/\\/ask$/,'/ab') : "";
 function _visitorId(){{ try{{let v=localStorage.getItem('jf_vid');
   if(!v){{v='v'+Math.abs((Date.now()^(performance.now()*1000|0))).toString(36);
     localStorage.setItem('jf_vid',v);}} return v;}}catch(e){{return 'anon';}} }}
 function _abAssign(exp, keys){{
   try{{const sk='jf_ab_'+exp; let v=localStorage.getItem(sk);
     if(v && keys.indexOf(v)>=0) return v;
     v=keys[Math.floor(Math.random()*keys.length)];
     localStorage.setItem(sk,v); return v;}}
   catch(e){{return keys[0];}}
 }}
 function _abSend(exp, variant, event){{
   if(!AB_API) return;
   fetch(AB_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
     body:JSON.stringify({{experiment:exp,variant:variant,event:event,
       visitor:_visitorId()}})}}).catch(function(){{}});
 }}
 const AB_ASSIGNED={{}};
 function applyExperiments(){{
   for(const exp in AB_EXPERIMENTS){{
     const cfg=AB_EXPERIMENTS[exp]; const keys=Object.keys(cfg.variants||{{}});
     if(!keys.length) continue;
     const variant=_abAssign(exp, keys); AB_ASSIGNED[exp]=variant;
     const el=document.querySelector('[data-ab="'+cfg.target+'"]');
     if(el) el.textContent=cfg.variants[variant];
     _abSend(exp, variant, 'impression');
   }}
 }}
 function abConvert(){{ for(const exp in AB_ASSIGNED) _abSend(exp, AB_ASSIGNED[exp], 'conversion'); }}
 window.addEventListener('DOMContentLoaded', applyExperiments);
 window.addEventListener('DOMContentLoaded', function(){{
   if(typeof initApparelSwatches==='function') initApparelSwatches();
   if(typeof renderGiftSets==='function') renderGiftSets();
 }});
 const SIGNUP_URL = "{signup_url}";
 let EXIT_SHOWN = false;
 function _exitDone(){{ try{{localStorage.setItem('jf_exit','1');}}catch(e){{}} }}
 function _exitSeen(){{ try{{return localStorage.getItem('jf_exit')==='1';}}catch(e){{return false;}} }}
 // True while the editor / proof / basket is open - i.e. an active purchase.
 function _overlayOpen(){{
   return ['modal','proofPop','basketPanel'].some(function(id){{
     const e=document.getElementById(id);
     return e && e.style.display && e.style.display!=='none';
   }});
 }}
 function openExit(){{ if(EXIT_SHOWN||_exitSeen())return;
   // Never interrupt someone mid-purchase with a discount popup.
   if(_overlayOpen()||CART.length) return;
   EXIT_SHOWN=true;
   document.getElementById('exitpop').style.display='flex'; }}
 function closeExit(){{ document.getElementById('exitpop').style.display='none'; _exitDone(); }}
 function submitExit(){{
   const v=(document.getElementById('xemail').value||'').trim();
   const msg=document.getElementById('xmsg');
   if(!/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(v)){{
     msg.className='xbad'; msg.textContent='Please enter a valid email.'; return; }}
   try{{localStorage.setItem('jf_email',v);}}catch(e){{}}
   const finish=()=>{{ msg.className='xok';
     msg.innerHTML='🎉 You\\'re in! Use code <b>{promo_code}</b> for {promo_pct}% off your first order.';
     document.getElementById('xform').style.display='none'; _exitDone(); }};
   if(SIGNUP_API){{
     fetch(SIGNUP_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
       body:JSON.stringify({{email:v,source:'exit_intent'}})}}).then(finish).catch(finish);
   }} else if(SIGNUP_URL){{ window.open(SIGNUP_URL,'_blank'); finish();
   }} else {{ finish(); }}
 }}
 // desktop: fire when cursor leaves the top of the viewport
 document.addEventListener('mouseout',function(e){{
   if(!e.relatedTarget && e.clientY<=0) openExit(); }});
 // mobile/fallback: fire after 40s of engagement
 setTimeout(function(){{ if(!_exitSeen()) openExit(); }}, 40000);
 function toggleAnge(){{const p=document.getElementById('angePanel');
   const open=p.style.display!=='block'; p.style.display=open?'block':'none';
   if(open && !document.getElementById('angeMsgs').dataset.init){{
     angeBot("Hi, I'm Ange 👋 Ask me anything about frames, sizes, personalizing, "
       +"shipping or gifts!"); renderChips();
     document.getElementById('angeMsgs').dataset.init='1';}}}}
 function renderChips(){{document.getElementById('angeChips').innerHTML=
   ANGE_KB.slice(0,4).map(e=>`<span class="achip" onclick="angeAsk('${{e.q.replace(/'/g,"")}}')">${{e.q}}</span>`).join('');}}
 function angeMsg(t,who){{const m=document.getElementById('angeMsgs');
   const d=document.createElement('div'); d.className='amsg '+who; d.textContent=t;
   m.appendChild(d); m.scrollTop=m.scrollHeight;}}
 function angeBot(t){{angeMsg(t,'bot');}}
 function angeAsk(q){{document.getElementById('angeIn').value=q; angeSend();}}
 function angeAnswer(q){{const s=q.toLowerCase(); let best=null,bs=0;
   for(const e of ANGE_KB){{let sc=0; for(const k of e.k){{if(s.indexOf(k)>=0)sc++;}}
     if(sc>bs){{bs=sc;best=e;}}}}
   if(best&&bs>=1)return best.a;
   return "Great question! For anything order-specific or a refund/return, the "
     +"best step is to message our team - tap the button below and a real person "
     +"will help. 💚";}}
 function angeMsgUs(){{const m=document.getElementById('angeMsgs');
   const a=document.createElement('a');
   a.href="mailto:"+ANGE_OWNER+"?subject=Question%20for%20{SHOP_NAME}";
   a.textContent="✉ Message us"; a.style="display:inline-block;margin:6px 0;font-size:12px;color:#103d2e";
   m.appendChild(a); m.scrollTop=m.scrollHeight;}}
 function angeSend(){{const inp=document.getElementById('angeIn');
   const q=(inp.value||'').trim(); if(!q)return; angeMsg(q,'me'); inp.value='';
   if(ANGE_API){{
     fetch(ANGE_API,{{method:'POST',headers:{{'Content-Type':'application/json'}},
       body:JSON.stringify({{q:q}})}}).then(r=>r.json())
       .then(d=>{{angeBot(d.answer||angeAnswer(q)); angeMsgUs();}})
       .catch(()=>{{angeBot(angeAnswer(q)); angeMsgUs();}});
   }} else {{ setTimeout(()=>{{angeBot(angeAnswer(q)); angeMsgUs();}},250); }}
 }}
</script>
</body></html>"""
    out.write_text(html, encoding="utf-8")
    # GitHub Pages serves this generated static site via legacy Jekyll, which fails
    # on the storefront's braces/`${...}`. A .nojekyll file next to the page tells
    # Pages to skip Jekyll and serve the files as-is. Emit it on EVERY build so a
    # rebuild can never silently drop it and break the deploy.
    try:
        (out.parent / ".nojekyll").write_text("", encoding="utf-8")
    except OSError:
        pass
    return out


# ── Pro Designer (beta): a Fabric.js free-canvas studio, ADDITIVE to the main editor.
# Customers add text + images on a live product mockup with full drag/resize/rotate/
# layer control, save the design, and export a print-ready file to the SAME /upload +
# /design endpoints the order pipeline already uses. No supplier/marketplace names in
# any customer-facing copy (uses "print partner").
_PRO_STUDIO_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Joffiels - Pro Designer (beta)</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Bebas+Neue&family=Montserrat:wght@400;600;700&family=Cormorant+Garamond:wght@600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
<style>
 :root{--green:#0f3d2e;--green-d:#0b2c21;--gold:#c6a052;--cream:#f7f4ec;--ink:#1b1b1f;--line:#e4ded2;--muted:#6c7570}
 *{box-sizing:border-box}
 body{margin:0;font-family:'Montserrat',system-ui,Arial,sans-serif;background:var(--cream);color:var(--ink)}
 #gate{position:fixed;inset:0;background:linear-gradient(160deg,#103d2e,#0b2c21);display:flex;align-items:center;justify-content:center;z-index:50}
 .gatebox{background:#fff;border-radius:18px;padding:36px 30px;max-width:360px;text-align:center;box-shadow:0 30px 70px rgba(0,0,0,.4)}
 .gatebox h2{color:var(--green);margin:6px 0;font-size:26px}
 .gatebox input{width:100%;padding:12px;border:1px solid var(--line);border-radius:10px;margin:10px 0;font-size:15px}
 .gatebox button{background:var(--green);color:#fff;border:none;padding:12px 0;width:100%;border-radius:10px;font-weight:700;cursor:pointer}
 header{display:flex;align-items:center;gap:14px;padding:12px 18px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
 header .logo{font-weight:800;color:var(--green);font-size:20px;letter-spacing:.3px}
 header .beta{background:var(--gold);color:#3a2c08;font-size:11px;font-weight:800;padding:3px 8px;border-radius:20px}
 header .sp{flex:1}
 .hbtn{border:1px solid var(--green);background:#fff;color:var(--green);font-weight:700;border-radius:10px;padding:9px 14px;cursor:pointer;font-size:14px}
 .hbtn.solid{background:var(--green);color:#fff}
 .wrap{display:flex;gap:0;min-height:calc(100vh - 58px)}
 .tools{width:266px;background:#fff;border-right:1px solid var(--line);padding:14px;overflow:auto}
 .grp{margin-bottom:16px}
 .grp h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted)}
 .prodrow{display:grid;grid-template-columns:1fr 1fr;gap:6px}
 .prodbtn{border:1px solid var(--line);background:#fff;border-radius:10px;padding:9px 6px;font-size:13px;cursor:pointer;text-align:center}
 .prodbtn.on{border-color:var(--green);background:#eef5f0;color:var(--green);font-weight:700}
 .tbtn{display:block;width:100%;border:1px solid var(--line);background:#fff;border-radius:10px;padding:11px;font-size:14px;cursor:pointer;margin-bottom:7px;text-align:left}
 .tbtn:hover{border-color:var(--green)}
 .row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
 .row label{font-size:12px;color:var(--muted)}
 select,.mini{border:1px solid var(--line);border-radius:8px;padding:7px;font-size:13px;background:#fff}
 .mini{width:42px;text-align:center;cursor:pointer}
 input[type=color]{width:36px;height:32px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer;padding:2px}
 .stage{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:22px;background:#efe9dc}
 .board{position:relative;background:#fbfaf7;border-radius:14px;box-shadow:0 18px 44px rgba(0,0,0,.16);display:flex;align-items:center;justify-content:center;padding:16px}
 .board-tshirt{background:linear-gradient(180deg,#fdfdfc,#efeae1)}
 .board-mug{background:linear-gradient(180deg,#fbfaf7,#efece4)}
 .board-tote{background:linear-gradient(180deg,#f3ecd9,#e7ddc7)}
 .board-poster{background:#fff;border:1px solid var(--line)}
 #safe{position:absolute;border:1.5px dashed rgba(15,61,46,.45);border-radius:6px;pointer-events:none}
 .hint{margin-top:12px;font-size:13px;color:var(--muted)}
 #toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--green);color:#fff;padding:11px 18px;border-radius:10px;font-size:14px;opacity:0;transition:opacity .25s;z-index:30}
 #toast.on{opacity:1}
 .note{font-size:12px;color:var(--muted);line-height:1.5;margin-top:8px}
 .disabled{opacity:.4;pointer-events:none}
 .swrow{display:flex;flex-wrap:wrap;gap:7px}
 .sw{width:26px;height:26px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px var(--line);cursor:pointer}
 .sw.on{box-shadow:0 0 0 2px var(--green)}
 .readybox{font-size:12px;line-height:1.5;margin-bottom:8px}
 .readybox .ok{color:#2e7d52}.readybox .warn{color:#b06a00}.readybox .bad{color:#b3322c}
 .cpr{display:flex;gap:8px;align-items:flex-start;font-size:12px;color:#3a4a42;cursor:pointer;margin:4px 0}
 .cpr input{margin-top:2px}
</style></head><body>
<div id="gate"><div class="gatebox">
  <h2>Joffiels Pro Designer</h2>
  <p style="color:#6c7570;font-size:13px">Enter the access word to continue.</p>
  <input id="gpw" type="password" placeholder="Access word" onkeydown="if(event.key==='Enter')tryGate()">
  <button onclick="tryGate()">Enter</button>
</div></div>

<div id="app" style="display:none">
<header>
  <span class="logo">Joffiels</span><span class="beta">PRO DESIGNER · BETA</span>
  <span class="sp"></span>
  <button class="hbtn" title="Undo" onclick="undo()">&#8634;</button>
  <button class="hbtn" title="Redo" onclick="redo()">&#8635;</button>
  <button class="hbtn" onclick="saveDesign()">&#128190; Save</button>
  <button class="hbtn solid" onclick="approveOrder()">&#10003; Approve &amp; order</button>
</header>
<div class="wrap">
  <aside class="tools">
    <div class="grp"><h4>Product</h4>
      <div class="prodrow">
        <button class="prodbtn on" data-k="tshirt" onclick="setProduct('tshirt')">&#128085; T-Shirt</button>
        <button class="prodbtn" data-k="hoodie" onclick="setProduct('hoodie')">&#129509; Hoodie</button>
        <button class="prodbtn" data-k="sweat" onclick="setProduct('sweat')">&#129508; Sweatshirt</button>
        <button class="prodbtn" data-k="kids" onclick="setProduct('kids')">&#129722; Kids Tee</button>
        <button class="prodbtn" data-k="mug" onclick="setProduct('mug')">&#9749; Mug</button>
        <button class="prodbtn" data-k="tote" onclick="setProduct('tote')">&#128717; Tote</button>
        <button class="prodbtn" data-k="poster" onclick="setProduct('poster')">&#128444; Poster</button>
      </div>
      <div id="sidegrp" class="prodrow" style="margin-top:8px;display:none">
        <button class="prodbtn on" id="sideFront" onclick="setSide('front')">&#128083; Front</button>
        <button class="prodbtn" id="sideBack" onclick="setSide('back')">&#128083; Back</button>
      </div>
    </div>
    <div class="grp"><h4>Size, colour &amp; quantity</h4>
      <div class="row" style="margin-bottom:8px"><label style="width:42px">Size</label>
        <select id="psize" onchange="CSIZE=this.value" style="flex:1"></select></div>
      <div class="row" style="margin-bottom:8px"><label style="width:42px">Qty</label>
        <input id="pqty" type="number" min="1" max="50" value="1" class="mini" style="width:60px"
          onchange="CQTY=Math.max(1,Math.min(50,parseInt(this.value)||1));this.value=CQTY"></div>
      <div id="pcolors" class="swrow"></div>
    </div>
    <div class="grp"><h4>Add to your design</h4>
      <button class="tbtn" onclick="addText()">&#10133; Add text</button>
      <label class="tbtn" style="cursor:pointer">&#128247; Upload an image / logo
        <input type="file" accept="image/png,image/jpeg" style="display:none" onchange="uploadImage(this)"></label>
    </div>
    <div class="grp"><h4>Elements</h4>
      <div class="row">
        <span class="mini" title="Rectangle" onclick="addShape('rect')">&#9645;</span>
        <span class="mini" title="Circle" onclick="addShape('circle')">&#9679;</span>
        <span class="mini" title="Line" onclick="addShape('line')">&#9135;</span>
        <span class="mini" title="Triangle" onclick="addShape('triangle')">&#9650;</span>
        <span class="mini" title="Star" onclick="addShape('star')">&#9733;</span>
        <span class="mini" title="Heart" onclick="addShape('heart')">&#9829;</span>
      </div>
      <div class="row" style="margin-top:7px"><label style="width:42px">Fill</label>
        <input type="color" id="shapecolor" value="#0f3d2e" oninput="applyShape('fill',this.value)">
        <span class="mini" title="No fill (outline)" onclick="applyShape('fill','')">&#9633;</span>
      </div>
    </div>
    <div class="grp disabled" id="imggrp"><h4>Image</h4>
      <div class="row">
        <span class="mini" title="Flip horizontal" onclick="flipImg('x')">&#8596;</span>
        <span class="mini" title="Flip vertical" onclick="flipImg('y')">&#8597;</span>
        <span class="mini" title="Black &amp; white" onclick="imgBW()">&#9680;</span>
        <span class="mini" title="Original colours" onclick="imgClear()">&#127912;</span>
      </div>
      <div class="row" style="margin-top:7px"><label style="width:42px">Fade</label>
        <input type="range" min="20" max="100" value="100" style="flex:1" oninput="applyAny('opacity',this.value/100)"></div>
    </div>
    <div class="grp" id="textgrp"><h4>Text</h4>
      <div class="row" style="margin-bottom:7px">
        <select id="ffont" onchange="applyText('fontFamily',this.value)" style="flex:1">
          <option value="Oswald, sans-serif">Oswald</option>
          <option value="Montserrat, sans-serif">Montserrat</option>
          <option value="'Bebas Neue', sans-serif">Bebas</option>
          <option value="'Cormorant Garamond', serif">Cormorant</option>
          <option value="'Playfair Display', serif">Playfair</option>
          <option value="Georgia, serif">Georgia</option>
        </select>
      </div>
      <div class="row" style="margin-bottom:7px">
        <span class="mini" onclick="bumpSize(-4)">A-</span>
        <span class="mini" onclick="bumpSize(4)">A+</span>
        <span class="mini" onclick="applyText('fontWeight', _isBold()?'normal':'bold')"><b>B</b></span>
        <span class="mini" onclick="applyText('fontStyle', _isItalic()?'normal':'italic')"><i>I</i></span>
        <input type="color" id="fcolor" value="#1b1b1f" oninput="applyText('fill',this.value)">
      </div>
      <div class="row" style="margin-bottom:7px">
        <span class="mini" onclick="applyText('textAlign','left')">&#8676;</span>
        <span class="mini" onclick="applyText('textAlign','center')">&#8596;</span>
        <span class="mini" onclick="applyText('textAlign','right')">&#8677;</span>
      </div>
      <div class="row" style="margin-bottom:7px"><label style="width:42px">Curve</label>
        <span class="mini" title="Straight" onclick="curveText('straight')">&mdash;</span>
        <span class="mini" title="Arc (curved)" onclick="curveText('up')">&#9180;</span>
        <span class="mini" title="Full circle (badge)" onclick="curveText('circle')">&#9711;</span>
      </div>
      <div class="row"><label style="width:42px">Style</label>
        <span class="mini" title="Outline / solid" onclick="textOutline()">&#9106;</span>
        <span class="mini" title="Wider letters" onclick="bumpSpacing(80)">A&rarr;A</span>
        <span class="mini" title="Tighter letters" onclick="bumpSpacing(-80)">A&larr;A</span>
        <input type="range" title="Fade" min="20" max="100" value="100" style="flex:1" oninput="applyAny('opacity',this.value/100)">
      </div>
    </div>
    <div class="grp"><h4>Arrange</h4>
      <div class="row">
        <span class="mini" title="Duplicate" onclick="dupSel()">&#10697;</span>
        <span class="mini" title="Bring forward" onclick="fwd()">&#9650;</span>
        <span class="mini" title="Send back" onclick="bwd()">&#9660;</span>
        <span class="mini" title="Delete" onclick="delSel()">&#128465;</span>
      </div>
      <div class="note">Drag to move &middot; corner to resize &middot; top handle to rotate. Keep important art inside the dashed line - the edge is trimmed in printing.</div>
    </div>
    <div class="grp"><h4>Before you order</h4>
      <div id="ready" class="readybox"></div>
      <label class="cpr"><input type="checkbox" id="cpr" onchange="checkReady()"> I own or have the rights to use this design.</label>
      <div class="note">Personalizing is 100% free. "Approve &amp; order" builds a high-resolution print file and sends it to our print partner only after you check out. Nothing prints until you approve it.</div>
    </div>
  </aside>
  <main class="stage">
    <div class="board board-tshirt" id="board"><canvas id="fcanvas"></canvas><div id="safe"></div></div>
    <div class="hint" id="hint">Add text or an image to start your T-Shirt design.</div>
  </main>
</div></div>
<div id="toast"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js" crossorigin="anonymous"></script>
<script>
 const ANGE_API="__ASK_API__";
 const UPLOAD_API=ANGE_API?ANGE_API.replace(/\/ask$/,'/upload'):"";
 const DESIGN_API=ANGE_API?ANGE_API.replace(/\/ask$/,'/design'):"";
 const CHECKOUT_URL="__CHECKOUT__";
 const MAX_MB=25, PASS="__PASS__";
 function knownEmail(){try{return localStorage.getItem('jf_email')||""}catch(e){return""}}
 function toast(t){var n=document.getElementById('toast');n.textContent=t;n.classList.add('on');setTimeout(function(){n.classList.remove('on')},2600);}
 // Garment/print colour name -> swatch hex (the print field on a real product).
 const COLORHEX={'White':'#f4f3ef','Natural':'#e7ddc7','Sand':'#d8c9a8','Cream':'#f3ecd9','Heather Grey':'#b9bdc2',
   'Light Blue':'#a7c7e7','Black':'#1c1c1e','Navy':'#26324a','Royal Blue':'#2f4ba0','Red':'#b3322c',
   'Maroon':'#5e2a32','Forest Green':'#2e4a39','Sage':'#7f9b78','Mustard':'#cda434'};
 const DARKCOLOR={'Black':1,'Navy':1,'Royal Blue':1,'Red':1,'Maroon':1,'Forest Green':1};
 // Each product: on-screen board size + the real print-file pixel target + safe inset +
 // the sizes/colours that actually order through the pipeline.
 const _APP_COL=['White','Sand','Heather Grey','Light Blue','Black','Navy','Red','Forest Green'];
 const PRODUCTS={
  tshirt:{name:'T-Shirt',w:460,h:575,print:[2400,3000],safe:0.06,board:'tshirt',twosided:true,
    sizes:['S','M','L','XL','2XL','3XL'],colors:_APP_COL},
  hoodie:{name:'Hoodie',w:470,h:560,print:[2400,3000],safe:0.07,board:'tshirt',twosided:true,
    sizes:['S','M','L','XL','2XL','3XL'],colors:['White','Sand','Heather Grey','Black','Navy','Forest Green','Maroon']},
  sweat:{name:'Sweatshirt',w:470,h:560,print:[2400,3000],safe:0.07,board:'tshirt',twosided:true,
    sizes:['S','M','L','XL','2XL','3XL'],colors:['White','Sand','Heather Grey','Black','Navy']},
  kids:{name:'Kids Tee',w:430,h:520,print:[1800,2400],safe:0.06,board:'tshirt',twosided:true,
    sizes:['2T','3T','4T','5-6','7-8','10-12'],colors:['White','Light Blue','Heather Grey','Black','Red']},
  mug:{name:'Mug',w:540,h:250,print:[2475,1155],safe:0.05,board:'mug',
    sizes:['11oz','15oz'],colors:['White','Black','Navy','Red']},
  tote:{name:'Tote',w:440,h:520,print:[2200,2600],safe:0.07,board:'tote',
    sizes:['One size'],colors:['Natural','Black']},
  poster:{name:'Poster',w:430,h:560,print:[3600,4500],safe:0.04,board:'poster',
    sizes:['12x18','18x24','24x36'],colors:['White']}
 };
 let CURP='tshirt', CSIZE='M', CCOLOR='White', CQTY=1, CSIDE='front', SIDES={}, canvas=null;
 function tryGate(){ if((document.getElementById('gpw').value||'')===PASS){ try{sessionStorage.setItem('jf','1')}catch(e){} openApp(); } else { document.getElementById('gpw').style.borderColor='#b3322c'; } }
 function openApp(){ document.getElementById('gate').style.display='none'; document.getElementById('app').style.display=''; if(!canvas) initStudio(); }
 function initStudio(){
   // Persist the curve MODE on text, never the live path object (it breaks on reload).
   if(fabric.Text && !fabric.Text.prototype._jfPatched){
     var _to=fabric.Text.prototype.toObject;
     fabric.Text.prototype.toObject=function(p){ var r=_to.call(this,(p||[]).concat(['_curve'])); delete r.path; return r; };
     fabric.Text.prototype._jfPatched=true;
   }
   canvas=new fabric.Canvas('fcanvas',{preserveObjectStacking:true,selection:true});
   canvas.on('selection:created',syncText); canvas.on('selection:updated',syncText); canvas.on('selection:cleared',syncText);
   canvas.on('object:modified',checkReady); canvas.on('object:removed',checkReady);
   canvas.on('object:added',_snap); canvas.on('object:modified',_snap); canvas.on('object:removed',_snap);
   var _rzT; window.addEventListener('resize',function(){ clearTimeout(_rzT); _rzT=setTimeout(refitCanvas,180); });
   document.addEventListener('keydown',function(e){ if((e.key==='Delete'||e.key==='Backspace') && canvas.getActiveObject() && !canvas.getActiveObject().isEditing){ e.preventDefault(); delSel(); } });
   setProduct('tshirt');
   // Fonts load async; Fabric renders text before they arrive, so re-render once the
   // web fonts are ready (otherwise the chosen display font falls back to system).
   if(document.fonts&&document.fonts.ready){ document.fonts.ready.then(function(){ if(canvas) canvas.requestRenderAll(); }); }
 }
 function _fontReflow(fam){ if(document.fonts&&document.fonts.load){ try{ document.fonts.load('24px '+fam).then(function(){ canvas&&canvas.requestRenderAll(); }).catch(function(){}); }catch(e){} } }
 // Re-fit the canvas to the current stage width WITHOUT touching the design: used on
 // window resize (mobile orientation / URL-bar) so a resize never discards work.
 // Objects are scaled by the size ratio so they keep their relative position.
 function refitCanvas(){
   if(!canvas) return; var p=PRODUCTS[CURP];
   var stage=document.querySelector('.stage'); var maxW=Math.min(p.w, (stage.clientWidth-60)), sc=maxW/p.w;
   var W=Math.round(p.w*sc), H=Math.round(p.h*sc);
   var oldW=canvas.getWidth()||W, ratio=oldW?(W/oldW):1;
   var board=document.getElementById('board'); board.style.width=(W+32)+'px'; board.style.height=(H+32)+'px';
   canvas.setWidth(W); canvas.setHeight(H);
   if(ratio && Math.abs(ratio-1)>0.001){ canvas.getObjects().forEach(function(o){ o.left*=ratio; o.top*=ratio; o.scaleX*=ratio; o.scaleY*=ratio; o.setCoords(); }); }
   canvas.calcOffset(); canvas.renderAll();
   var s=document.getElementById('safe'), m=Math.round(Math.min(W,H)*p.safe);
   s.style.left=(16+m)+'px'; s.style.top=(16+m)+'px'; s.style.width=(W-2*m)+'px'; s.style.height=(H-2*m)+'px';
 }
 function setProduct(k){
   // Re-selecting the same product just re-fits (no clear, no confirm).
   if(k===CURP && canvas){ refitCanvas(); return; }
   // Switching to a DIFFERENT product clears the board (a mug is not a tee). Guard
   // against accidental loss of in-progress work.
   if(canvas && canvas.getObjects().length && !confirm('Switch product? This clears your current design.')){
     document.querySelectorAll('.prodbtn').forEach(function(b){ b.classList.toggle('on',b.dataset.k===CURP); });
     return;
   }
   CURP=k; var p=PRODUCTS[k];
   document.getElementById('board').className='board board-'+p.board;
   document.querySelectorAll('.prodbtn').forEach(function(b){ b.classList.toggle('on',b.dataset.k===k); });
   if(canvas) canvas.clear();
   CSIDE='front'; SIDES={};
   refitCanvas();
   document.getElementById('hint').textContent='Add text or an image to start your '+p.name+' design.';
   var sg=document.getElementById('sidegrp'); if(sg) sg.style.display=p.twosided?'grid':'none';
   var sf=document.getElementById('sideFront'),sb=document.getElementById('sideBack');
   if(sf) sf.classList.add('on'); if(sb) sb.classList.remove('on');
   renderOptions(); applyColor(); checkReady();
 }
 // Size dropdown + colour swatches for the chosen product; ordering carries these.
 function renderOptions(){
   var p=PRODUCTS[CURP];
   if(p.sizes.indexOf(CSIZE)<0) CSIZE=p.sizes[Math.min(1,p.sizes.length-1)];
   var sz=document.getElementById('psize'); sz.innerHTML=p.sizes.map(function(s){return '<option'+(s===CSIZE?' selected':'')+'>'+s+'</option>';}).join('');
   if(p.colors.indexOf(CCOLOR)<0) CCOLOR=p.colors[0];
   document.getElementById('pcolors').innerHTML=p.colors.map(function(c){
     return '<span class="sw'+(c===CCOLOR?' on':'')+'" title="'+c+'" style="background:'+(COLORHEX[c]||'#ccc')+'" onclick="setColor(\''+c+'\')"></span>';
   }).join('');
 }
 function setColor(c){ CCOLOR=c; renderOptions(); applyColor(); }
 // Tint the print field to the chosen colour and keep text legible on it.
 function applyColor(){
   if(!canvas) return; canvas.setBackgroundColor(COLORHEX[CCOLOR]||'#fbfaf7', canvas.renderAll.bind(canvas));
   var ink=DARKCOLOR[CCOLOR]?'#ffffff':'#1b1b1f';
   document.getElementById('board').style.background=COLORHEX[CCOLOR]||'#fbfaf7';
   window._inkDefault=ink;
 }
 function addText(){
   var t=new fabric.IText('Your text',{left:canvas.getWidth()/2,top:canvas.getHeight()/2,originX:'center',originY:'center',
     fontFamily:'Oswald, sans-serif',fontSize:Math.round(canvas.getHeight()*0.10),fill:(window._inkDefault||'#1b1b1f'),textAlign:'center'});
   canvas.add(t); canvas.setActiveObject(t); t.enterEditing(); t.selectAll(); canvas.renderAll(); syncText(); checkReady();
 }
 function uploadImage(inp){
   var f=inp.files&&inp.files[0]; if(!f) return;
   if(f.size>MAX_MB*1048576){ toast('That image is over '+MAX_MB+'MB - please use a smaller file.'); inp.value=''; return; }
   var isPng=/\.png$/i.test(f.name)||f.type==='image/png';
   var r=new FileReader();
   r.onload=function(e){ fabric.Image.fromURL(e.target.result,function(img){
     var sc=Math.min(canvas.getWidth()*0.6/img.width, canvas.getHeight()*0.6/img.height);
     img.set({left:canvas.getWidth()/2,top:canvas.getHeight()/2,originX:'center',originY:'center',scaleX:sc,scaleY:sc});
     // Print-quality checks the customer should see (spec): native resolution vs the
     // print target, and whether a logo has a transparent background.
     img._natW=img.width; img._natH=img.height; img._isPng=isPng; img._hasAlpha=isPng&&_hasAlpha(img._element);
     canvas.add(img); canvas.setActiveObject(img); canvas.renderAll(); checkReady();
   }); };
   r.readAsDataURL(f); inp.value='';
 }
 // Sample the image's corners for transparency (a logo on a photo background prints
 // the box, not just the mark) - drives the "needs a transparent background" tip.
 function _hasAlpha(el){ try{ var c=document.createElement('canvas'),n=24; c.width=n;c.height=n;
   var x=c.getContext('2d'); x.drawImage(el,0,0,n,n); var d=x.getImageData(0,0,n,n).data;
   for(var i=3;i<d.length;i+=4){ if(d[i]<200) return true; } return false; }catch(e){ return true; } }
 function _outsideSafe(){ var p=PRODUCTS[CURP], m=Math.min(canvas.getWidth(),canvas.getHeight())*p.safe, out=false;
   canvas.getObjects().forEach(function(o){ var r=o.getBoundingRect(true,true);
     if(r.left<m-1||r.top<m-1||r.left+r.width>canvas.getWidth()-m+1||r.top+r.height>canvas.getHeight()-m+1) out=true; }); return out; }
 // Live print-readiness messages (the spec's plain-language checks).
 function checkReady(){
   var box=document.getElementById('ready'); if(!box||!canvas) return; var p=PRODUCTS[CURP], objs=canvas.getObjects();
   if(!objs.length){ box.innerHTML='<span class="warn">Add text or an image to begin.</span>'; window._READY=false; return; }
   var lowres=false, needAlpha=false, tiny=false;
   objs.forEach(function(o){
     if(o.type==='image'){ var req=(o.getScaledWidth()/canvas.getWidth())*p.print[0];
       if(o._natW && o._natW<req*0.6) lowres=true; if(o._hasAlpha===false) needAlpha=true; }
     else if(_isText(o)){ if(o.fontSize*(p.print[0]/canvas.getWidth())<55) tiny=true; }
   });
   var outside=_outsideSafe(), m=[];
   if(outside) m.push('<span class="bad">&#9888; Part of your design is outside the safe print area (dashed line) - move it inside.</span>');
   if(lowres) m.push('<span class="warn">&#9888; Your image looks low-resolution for this print size - it may print soft. Try a larger file.</span>');
   if(needAlpha) m.push('<span class="warn">&#9888; For a logo, use a PNG with a transparent background - otherwise it prints inside a box.</span>');
   if(tiny) m.push('<span class="warn">&#9888; Some text may be too small to print clearly - make it larger.</span>');
   if(!m.length) m.push('<span class="ok">&#10003; Looks print-ready. Order whenever you are happy.</span>');
   box.innerHTML=m.join('<br>'); window._READY=!outside;
 }
 function approveOrder(){
   if(!canvas.getObjects().length){ toast('Add something to your design first.'); return; }
   checkReady();
   if(window._READY===false){ toast('Move your design inside the dashed safe area first.'); return; }
   if(!document.getElementById('cpr').checked){ toast('Please confirm you own the rights to this design.'); try{document.getElementById('cpr').focus();}catch(e){} return; }
   var email=knownEmail(), p=PRODUCTS[CURP], mult=p.print[0]/canvas.getWidth();
   canvas.discardActiveObject(); canvas.renderAll();
   var url=canvas.toDataURL({format:'png',multiplier:mult});
   if(p.twosided) SIDES[CSIDE]=canvas.toJSON();
   // Save the design WITH the hosted print URL so the pipeline can put it straight on
   // the order's artwork (link_design_to_order -> _propagate_design_artwork). True
   // end to end: design + print file reach production tied to the order.
   function _finish(printUrl){
     var design={engine:'fabric',product:CURP,productName:p.name,size:CSIZE,color:CCOLOR,qty:CQTY,rights:true,
       side:CSIDE, sides:(p.twosided?SIDES:null), printUrl:printUrl||'', json:canvas.toJSON()};
     try{ localStorage.setItem('jf_pro_order', JSON.stringify(design)); }catch(e){}
     if(email && DESIGN_API){ fetch(DESIGN_API,{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({email:email,design:design,summary:'Pro Designer - '+p.name+' '+CSIZE+' '+CCOLOR+' x'+CQTY})}).catch(function(){}); }
     var a=document.createElement('a'); a.href=url; a.download='joffiels-'+CURP+'-design.png'; a.click();
     if(CHECKOUT_URL){ toast('Design approved - opening secure checkout...'); setTimeout(function(){ window.open(CHECKOUT_URL,'_blank','noopener'); },800); }
     else { toast('Design approved & print-ready file saved - we will follow up to finish your order.'); }
   }
   if(email && UPLOAD_API){ try{ var fd=new FormData(); fd.append('file',_dataURLtoBlob(url),'pro-'+CURP+'.png');
     fd.append('email',email); fd.append('size',p.print[0]+'x'+p.print[1]); fd.append('name','pro-'+CURP+'-'+CSIZE+'-'+CCOLOR);
     fetch(UPLOAD_API,{method:'POST',body:fd}).then(function(r){return r.json();}).then(function(d){ _finish(d&&d.url); }).catch(function(){ _finish(''); }); }catch(e){ _finish(''); } }
   else { _finish(''); }
 }
 function _active(){ return canvas&&canvas.getActiveObject(); }
 function _isText(o){ return o&&(o.type==='i-text'||o.type==='text'||o.type==='textbox'); }
 function applyText(prop,val){ var o=_active(); if(_isText(o)){ o.set(prop,val); canvas.requestRenderAll(); if(prop==='fontFamily') _fontReflow(val); } }
 function bumpSize(d){ var o=_active(); if(_isText(o)){ o.set('fontSize',Math.max(8,(o.fontSize||24)+d)); canvas.requestRenderAll(); } }
 // Curve a real (still-editable) text object along an arc/circle using Fabric's native
 // text-on-path. Straight removes the path. Radius is derived from the text width so it
 // fits the wording. The classic Layout Studio's badge/arc look, in the free editor.
 // Apply an arc/circle path to a text object. The live fabric.Path does NOT survive
 // toJSON/loadFromJSON (it revives broken and crashes render), so we persist only the
 // curve MODE on the object and rebuild the path here - on edit AND after any load.
 function _applyCurve(o,mode){
   if(!o) return;
   if(!mode||mode==='straight'){ o.set({path:null,pathStartOffset:0}); o.setCoords(); return; }
   o.set({path:null}); if(o.initDimensions) o.initDimensions();
   var tw=Math.max(40,o.width||o.getScaledWidth()), r, d, path, off=0;
   if(mode==='circle'){ r=Math.max(34,tw/(2*Math.PI)); d=2*r;
     path='M '+d+','+r+' A '+r+','+r+' 0 1,1 0,'+r+' A '+r+','+r+' 0 1,1 '+d+','+r+' z'; off=0; }
   else { r=Math.max(40,tw/Math.PI*1.04); d=2*r; off=Math.max(0,(Math.PI*r-tw)/2);
     path='M 0,'+r+' A '+r+','+r+' 0 0,1 '+d+','+r; }                                   // hump (rainbow)
   o.set({path:new fabric.Path(path,{fill:'',stroke:''}),pathSide:'left',pathAlign:'baseline',pathStartOffset:off,textAlign:'left'});
   o.setCoords();
 }
 function curveText(mode){ var o=_active(); if(!_isText(o)) return;
   o._curve=(mode==='straight'?null:{mode:mode}); _applyCurve(o,mode); canvas.requestRenderAll(); checkReady(); }
 function _rehydrateCurves(){ if(!canvas) return; canvas.getObjects().forEach(function(o){ if(o._curve&&o._curve.mode) _applyCurve(o,o._curve.mode); }); }
 // ── Shapes / elements ───────────────────────────────────────────────
 function _starPts(n,outer,inner){ var pts=[]; for(var i=0;i<n*2;i++){ var r=i%2?inner:outer,a=Math.PI/n*i-Math.PI/2; pts.push({x:Math.cos(a)*r,y:Math.sin(a)*r}); } return pts; }
 function addShape(kind){
   if(!canvas) return; var W=canvas.getWidth(),H=canvas.getHeight(),s=Math.min(W,H)*0.26,o,
     col=(document.getElementById('shapecolor')||{}).value||'#0f3d2e',
     base={left:W/2,top:H/2,originX:'center',originY:'center',fill:col};
   if(kind==='rect') o=new fabric.Rect(Object.assign({width:s*1.5,height:s,rx:4,ry:4},base));
   else if(kind==='circle') o=new fabric.Circle(Object.assign({radius:s/2},base));
   else if(kind==='triangle') o=new fabric.Triangle(Object.assign({width:s,height:s},base));
   else if(kind==='line') o=new fabric.Line([W/2-s,H/2,W/2+s,H/2],{stroke:col,strokeWidth:Math.max(4,s*0.05),originX:'center',originY:'center'});
   else if(kind==='star') o=new fabric.Polygon(_starPts(5,s/2,s/4),Object.assign({},base));
   else if(kind==='heart') o=new fabric.Path('M0,-15 C-16,-38 -46,-14 0,26 C46,-14 16,-38 0,-15 z',Object.assign({scaleX:s/42,scaleY:s/42},base));
   if(o){ canvas.add(o); canvas.setActiveObject(o); canvas.renderAll(); _snap(); checkReady(); }
 }
 function applyShape(prop,val){ var o=_active(); if(o&&!_isText(o)&&o.type!=='image'){
   if(prop==='fill'&&val===''){ o.set({fill:'',stroke:o.stroke||((document.getElementById('shapecolor')||{}).value||'#0f3d2e'),strokeWidth:o.strokeWidth||3}); }
   else o.set(prop,val); canvas.requestRenderAll(); } }
 function applyAny(prop,val){ var o=_active(); if(o){ o.set(prop,val); canvas.requestRenderAll(); } }
 // ── Image effects ───────────────────────────────────────────────────
 function flipImg(ax){ var o=_active(); if(o&&o.type==='image'){ o.set(ax==='x'?'flipX':'flipY', !(ax==='x'?o.flipX:o.flipY)); canvas.requestRenderAll(); } }
 function imgBW(){ var o=_active(); if(o&&o.type==='image'){ o.filters=[new fabric.Image.filters.Grayscale()]; o.applyFilters(); canvas.requestRenderAll(); } }
 function imgClear(){ var o=_active(); if(o&&o.type==='image'){ o.filters=[]; o.applyFilters(); canvas.requestRenderAll(); } }
 // ── Text effects ────────────────────────────────────────────────────
 function _isLightHex(h){ if(typeof h!=='string'||h[0]!=='#'||h.length<7) return false; var n=parseInt(h.slice(1),16),r=(n>>16)&255,g=(n>>8)&255,b=n&255; return (0.299*r+0.587*g+0.114*b)>150; }
 function textOutline(){ var o=_active(); if(_isText(o)){ if(o.strokeWidth>0&&o.stroke){ o.set({stroke:null,strokeWidth:0}); }
   else { o.set({stroke:(_isLightHex(o.fill)?'#1b1b1f':'#ffffff'),strokeWidth:Math.max(1.2,(o.fontSize||24)*0.045),paintFirst:'stroke'}); } canvas.requestRenderAll(); } }
 function bumpSpacing(d){ var o=_active(); if(_isText(o)){ o.set('charSpacing',(o.charSpacing||0)+d); canvas.requestRenderAll(); } }
 // ── Front / back (two-sided products) ───────────────────────────────
 function setSide(side){ if(!PRODUCTS[CURP].twosided||side===CSIDE) return;
   SIDES[CSIDE]=canvas.toJSON(); CSIDE=side;
   document.getElementById('sideFront').classList.toggle('on',side==='front');
   document.getElementById('sideBack').classList.toggle('on',side==='back');
   _histlock=true; canvas.clear();
   if(SIDES[side]){ canvas.loadFromJSON(SIDES[side],function(){ _rehydrateCurves(); applyColor(); canvas.renderAll(); _histlock=false; checkReady(); }); }
   else { applyColor(); canvas.renderAll(); _histlock=false; checkReady(); }
   document.getElementById('hint').textContent='Designing the '+side.toUpperCase()+' of your '+PRODUCTS[CURP].name+'.';
 }
 // ── Undo / redo ─────────────────────────────────────────────────────
 var HIST=[], HPTR=-1, _histlock=false;
 function _snap(){ if(_histlock||!canvas) return; try{ var j=JSON.stringify(canvas.toJSON());
   if(HIST[HPTR]===j) return; HIST=HIST.slice(0,HPTR+1); HIST.push(j); if(HIST.length>50)HIST.shift(); HPTR=HIST.length-1; }catch(e){} }
 function undo(){ if(HPTR<=0) return; HPTR--; _restore(); }
 function redo(){ if(HPTR>=HIST.length-1) return; HPTR++; _restore(); }
 function _restore(){ _histlock=true; canvas.loadFromJSON(HIST[HPTR],function(){ _rehydrateCurves(); applyColor(); canvas.renderAll(); _histlock=false; checkReady(); }); }
 function _isBold(){ var o=_active(); return _isText(o)&&(o.fontWeight==='bold'); }
 function _isItalic(){ var o=_active(); return _isText(o)&&(o.fontStyle==='italic'); }
 function syncText(){ var o=_active(); var on=_isText(o); document.getElementById('textgrp').classList.toggle('disabled',!on);
   if(on){ var ff=document.getElementById('ffont'); if(o.fontFamily) ff.value=o.fontFamily; var fc=document.getElementById('fcolor'); if(typeof o.fill==='string') fc.value=o.fill; }
   var ig=document.getElementById('imggrp'); if(ig) ig.classList.toggle('disabled', !(o&&o.type==='image')); }
 function dupSel(){ var o=_active(); if(!o) return; o.clone(function(c){ c.set({left:(o.left||0)+18,top:(o.top||0)+18}); canvas.add(c); canvas.setActiveObject(c); canvas.renderAll(); }); }
 function fwd(){ var o=_active(); if(o){ canvas.bringForward(o); canvas.renderAll(); } }
 function bwd(){ var o=_active(); if(o){ canvas.sendBackwards(o); canvas.renderAll(); } }
 function delSel(){ var o=_active(); if(o){ canvas.remove(o); canvas.discardActiveObject(); canvas.renderAll(); } }
 function saveDesign(){
   if(!canvas.getObjects().length){ toast('Add something to your design first.'); return; }
   var json=canvas.toJSON();
   try{ localStorage.setItem('jf_pro_'+CURP, JSON.stringify(json)); }catch(e){}
   var email=knownEmail();
   if(email && DESIGN_API){
     fetch(DESIGN_API,{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({email:email,design:{engine:'fabric',product:CURP,json:json},summary:'Pro Designer - '+PRODUCTS[CURP].name})})
       .then(function(){toast('Saved to your account.')}).catch(function(){toast('Saved on this device.')});
   } else { toast('Saved on this device. (Sign up to save it to your order.)'); }
 }
 function _dataURLtoBlob(u){ var a=u.split(','),m=a[0].match(/:(.*?);/)[1],b=atob(a[1]),n=b.length,arr=new Uint8Array(n); while(n--) arr[n]=b.charCodeAt(n); return new Blob([arr],{type:m}); }
 function exportPrint(){
   if(!canvas.getObjects().length){ toast('Add something to your design first.'); return; }
   var p=PRODUCTS[CURP], mult=p.print[0]/canvas.getWidth();
   canvas.discardObjectControls&&canvas.discardObjectControls(); canvas.discardActiveObject(); canvas.renderAll();
   var url=canvas.toDataURL({format:'png',multiplier:mult});
   var a=document.createElement('a'); a.href=url; a.download='joffiels-'+CURP+'-design.png'; a.click();
   saveDesign();
   var email=knownEmail();
   if(email && UPLOAD_API){
     try{ var fd=new FormData(); fd.append('file',_dataURLtoBlob(url),'design-'+CURP+'.png');
       fd.append('email',email); fd.append('size',p.print[0]+'x'+p.print[1]); fd.append('name','pro-'+CURP);
       fetch(UPLOAD_API,{method:'POST',body:fd}).then(function(r){return r.json()}).then(function(d){ toast('Print-ready file created &amp; saved.'); }).catch(function(){ toast('Print-ready file downloaded.'); });
     }catch(e){ toast('Print-ready file downloaded.'); }
   } else { toast('Print-ready file downloaded. (Sign up to attach it to your order.)'); }
 }
 // Open immediately if the shop gate was already cleared this session.
 try{ if(sessionStorage.getItem('jf')==='1'){ window.addEventListener('load',openApp); } }catch(e){}
</script></body></html>
"""


def build_pro_studio(out_path=None, password: str = "Jesus") -> Path:
    """Write the self-contained Fabric.js Pro Designer studio (beta) to docs/studio.html.

    Additive to the main editor: it reuses the same /upload (print file) and /design
    (save) endpoints the order pipeline already consumes, so a Pro design flows to the
    print partner exactly like a classic-editor design."""
    try:
        from quoteforge.config import ASK_ANGE_API_URL as ask_api_url
    except Exception:  # noqa: BLE001
        ask_api_url = ""
    try:
        from quoteforge.config import ETSY_SHOP_URL as shop_url
    except Exception:  # noqa: BLE001
        shop_url = ""
    html = (_PRO_STUDIO_HTML.replace("__ASK_API__", ask_api_url)
            .replace("__CHECKOUT__", shop_url).replace("__PASS__", password))
    out = Path(out_path) if out_path else Path("docs/studio.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def build_preview(n: int = 1, kit_dir=None, out_path=None) -> Path:
    """Build a single-listing preview page (gallery + SEO copy) for listing ``n``
    from its launch-kit folder; used to eyeball one listing before publishing."""
    from quoteforge.config import OUTPUT_DIR, ETSY_DEFAULT_LISTING_PRICE, SHOP_NAME
    from quoteforge.etsy.listing_seo import build_launch_seo

    kit_dir = Path(kit_dir) if kit_dir else (OUTPUT_DIR / "launch_kit")
    bundle = next((b for b in build_launch_seo() if b.listing_n == n), None)
    if not bundle:
        raise ValueError(f"No launch listing #{n}")

    imgs = sorted(kit_dir.glob(f"{n:02d}_*/gallery/*.png"))
    if not imgs:
        raise FileNotFoundError(
            f"No gallery images for #{n}. Run: admin launch-kit")
    main = _b64(imgs[0])
    thumbs = "".join(
        f'<img class="thumb" src="{_b64(p)}" onclick="document.getElementById(\'main\').src=this.src">'
        for p in imgs)

    tags = "".join(f'<span class="tag">{t}</span>' for t in bundle.tags)
    desc = bundle.description.replace("\n", "<br>")
    price = ETSY_DEFAULT_LISTING_PRICE

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{SHOP_NAME} - {bundle.title[:60]}</title>
<style>
 body{{font-family:Arial,Helvetica,sans-serif;color:#222;margin:0;background:#faf8f4}}
 .top{{background:#103d2e;color:#e8d8a8;padding:10px 24px;font-size:20px;
   font-family:Georgia,serif}}
 .wrap{{max-width:1100px;margin:24px auto;display:flex;gap:32px;padding:0 16px}}
 .gallery{{flex:1}} .main{{width:100%;border-radius:8px;border:1px solid #e3ddd2}}
 .thumbs{{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}}
 .thumb{{width:72px;height:72px;object-fit:cover;border:2px solid #d8cdb6;
   border-radius:6px;cursor:pointer}}
 .info{{flex:1}}
 .shop{{color:#103d2e;font-weight:bold}} .stars{{color:#c9a84c}}
 h1{{font-size:20px;line-height:1.4;margin:6px 0}}
 .price{{font-size:28px;font-weight:bold;margin:10px 0}}
 .box{{border:1px solid #d8cdb6;border-radius:8px;padding:12px;margin:14px 0;
   background:#fff}}
 .box label{{font-size:13px;color:#555}} textarea{{width:100%;height:70px;
   margin-top:6px;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}}
 .btn{{background:#103d2e;color:#fff;border:none;padding:14px;width:100%;
   border-radius:24px;font-size:16px;cursor:pointer;margin-top:8px}}
 .tags{{margin-top:16px}} .tag{{display:inline-block;background:#eef0ea;
   color:#33503f;border-radius:14px;padding:4px 10px;margin:3px;font-size:12px}}
 .desc{{margin-top:20px;line-height:1.6;font-size:14px;white-space:normal}}
 .note{{font-size:12px;color:#888;margin-top:6px}}
</style></head><body>
<div class="top">{SHOP_NAME} &nbsp;|&nbsp; Personalized wall art for life's biggest moments</div>
<div class="wrap">
 <div class="gallery">
   <img id="main" class="main" src="{main}">
   <div class="thumbs">{thumbs}</div>
   <div class="note">(A short video would also appear here - admin listing-video)</div>
 </div>
 <div class="info">
   <div class="shop">{SHOP_NAME}</div>
   <div class="stars">&#9733;&#9733;&#9733;&#9733;&#9733; <span style="color:#888">(new shop)</span></div>
   <h1>{bundle.title}</h1>
   <div class="price">${price:.2f}</div>
   <div class="box">
     <label>Personalize this gift (the buyer fills this in):</label>
     <textarea placeholder="Recipient name, occasion, relationship, a short story, and (optional) your own exact wording..."></textarea>
   </div>
   <button class="btn">Add to cart</button>
   <div class="note">Approve your free proof on screen before printing.</div>
   <div class="tags">{tags}</div>
   <div class="desc">{desc}</div>
 </div>
</div>
<div style="text-align:center;color:#aaa;font-size:12px;margin:24px">
  Mock preview generated by QuoteForge - preview only, not a live shop.</div>
</body></html>"""

    out = Path(out_path) if out_path else (kit_dir / f"preview_{n:02d}.html")
    out.write_text(html, encoding="utf-8")
    return out


def build_showroom(numbers=None, kit_dir=None, out_path=None) -> Path:
    """Combine several listings into ONE self-contained HTML file to share."""
    from quoteforge.config import OUTPUT_DIR, ETSY_DEFAULT_LISTING_PRICE, SHOP_NAME
    from quoteforge.etsy.listing_seo import build_launch_seo

    kit_dir = Path(kit_dir) if kit_dir else (OUTPUT_DIR / "launch_kit")
    numbers = numbers or [1, 5, 7, 10, 16, 19]   # a representative spread
    by_n = {b.listing_n: b for b in build_launch_seo()}

    cards = []
    for n in numbers:
        b = by_n.get(n)
        imgs = sorted(kit_dir.glob(f"{n:02d}_*/gallery/*.png"))
        if not b or not imgs:
            continue
        thumbs = "".join(
            f'<img class="t" src="{_b64(p)}" '
            f'onclick="this.closest(\'.card\').querySelector(\'.hero\').src=this.src">'
            for p in imgs)
        short = (b.description.split("\n")[0])[:160]
        cards.append(f"""
 <div class="card">
   <img class="hero" src="{_b64(imgs[0])}">
   <div class="cap">
     <div class="ttl">{b.title}</div>
     <div class="pr">${ETSY_DEFAULT_LISTING_PRICE:.2f}</div>
     <div class="th">{thumbs}</div>
     <div class="ds">{short}...</div>
   </div>
 </div>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{SHOP_NAME} - Sample Listings</title><style>
 body{{font-family:Arial,sans-serif;background:#faf8f4;color:#222;margin:0}}
 .top{{background:#103d2e;color:#e8d8a8;padding:18px 24px;font-family:Georgia,serif}}
 .top h1{{margin:0;font-size:24px}} .top p{{margin:4px 0 0;opacity:.85}}
 .grid{{max-width:1200px;margin:24px auto;display:grid;
   grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:22px;padding:0 16px}}
 .card{{background:#fff;border:1px solid #e3ddd2;border-radius:10px;overflow:hidden}}
 .hero{{width:100%;display:block}}
 .cap{{padding:12px}} .ttl{{font-size:14px;line-height:1.4;height:58px;overflow:hidden}}
 .pr{{font-weight:bold;font-size:20px;margin:6px 0;color:#103d2e}}
 .th{{display:flex;gap:5px;margin:6px 0}}
 .t{{width:48px;height:48px;object-fit:cover;border:1px solid #d8cdb6;
   border-radius:4px;cursor:pointer}}
 .ds{{font-size:12px;color:#666;margin-top:6px}}
 .foot{{text-align:center;color:#aaa;font-size:12px;margin:24px}}
</style></head><body>
<div class="top"><h1>{SHOP_NAME}</h1>
  <p>Personalized wall art for life's biggest moments - sample listings for review</p></div>
<div class="grid">{''.join(cards)}</div>
<div class="foot">Mock preview by QuoteForge - click a thumbnail to swap the main image.</div>
</body></html>"""
    out = Path(out_path) if out_path else (kit_dir / "SHOWROOM.html")
    out.write_text(html, encoding="utf-8")
    return out
