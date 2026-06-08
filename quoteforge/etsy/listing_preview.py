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


def _competitive_sections() -> str:
    """Conversion sections that beat mass printers: why-us comparison, a real
    happiness guarantee, and an FAQ. (Honest: no fabricated reviews pre-launch.)"""
    from quoteforge.config import SHOP_NAME
    rows = [
        ("Designed by a real person for your story", "Templated, mass-produced"),
        ("FREE digital proof - approve before we print", "What you upload is what prints"),
        ("Made to order, museum-quality materials", "Bulk factory runs"),
        ("Custom wording, colors &amp; frame - you preview it live", "Limited presets"),
        ("Personal note + gift e-card included free", "Add-on fees"),
        ("Happiness guarantee - we make it right", "Rigid return windows"),
    ]
    cmp_rows = "".join(
        f'<tr><td class="us">✓ {u}</td><td class="them">{t}</td></tr>' for u, t in rows)
    faqs = [
        ("Is the frame included?",
         "Poster, canvas, acrylic and metal ship without a frame. Choose a "
         "\"Framed\" option to add a real wood frame (6 styles)."),
        ("Can I use my own photo or exact wording?",
         "Yes! Upload a high-resolution photo and type your own words - we "
         "auto-check quality and send a free proof before printing."),
        ("How fast will it arrive?",
         "We send your proof within ~24h; once approved it's printed and shipped "
         "with tracking, typically within 3-5 business days."),
        ("What if I don't love it?",
         "Message us - our happiness guarantee means we'll fix or remake it. "
         "Personalized items are made to order, so approval happens on the proof."),
    ]
    faq_html = "".join(
        f'<details class="faq"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faqs)
    occ = ["Graduation", "Birthday", "Wedding", "Anniversary", "Mother's Day",
           "Father's Day", "Memorial", "New Home", "Faith", "Christmas"]
    chips = "".join(f'<span class="occhip">{o}</span>' for o in occ)
    return (
        f'<div class="shopocc"><div class="lbl">Shop by occasion</div>'
        f'<div class="occrow">{chips}</div></div>'
        f'<div class="why"><h2>Why {SHOP_NAME} (not a mass printer)</h2>'
        f'<table class="cmp"><tr><th>{SHOP_NAME}</th><th>Big-box printers</th></tr>'
        f'{cmp_rows}</table></div>'
        f'<div class="guarantee">💚 <b>Happiness Guarantee.</b> Every piece is '
        f'made to order and approved by you on a free proof. If something isn\'t '
        f'right, we\'ll make it right.</div>'
        f'<div class="faqs"><h2>Questions, answered</h2>{faq_html}</div>')


def _gift_and_b2b_section(owner: str) -> str:
    """'Complete the gift' affiliate cards (off-Etsy) + a B2B/wholesale inquiry
    block. Affiliate cards appear only for links that are configured; B2B always
    shows. FTC disclosure is included automatically."""
    from quoteforge.config import B2B_CONTACT_EMAIL
    from quoteforge.marketing.affiliate_programs import configured_links, emoji_for
    cards = []
    for label, url in configured_links().items():
        cards.append(
            f'<a class="gcard" href="{url}" target="_blank" '
            f'rel="sponsored noopener nofollow"><div class="ge">{emoji_for(label)}</div>'
            f'<div class="gl">{label}</div></a>')
    gift_html = ""
    if cards:
        gift_html = (
            '<div class="giftsec"><h2>Complete the gift</h2>'
            '<p class="gsub">Pair your personalized art with flowers or a gift '
            'card - delivered by trusted partners.</p>'
            f'<div class="gcards">{"".join(cards)}</div>'
            '<p class="ftc">Some links are affiliate links - we may earn a small '
            'commission at no extra cost to you.</p></div>')

    b2b_to = B2B_CONTACT_EMAIL or owner
    b2b_html = (
        '<div class="b2b"><h2>Corporate &amp; bulk gifting</h2>'
        '<p class="gsub">Personalized art for employee recognition, client gifts, '
        'weddings, realtor closings, churches &amp; schools - wholesale pricing on '
        'volume orders.</p>'
        '<div class="b2bform">'
        '<input id="bz_name" placeholder="Your name">'
        '<input id="bz_co" placeholder="Company / organization">'
        '<input id="bz_email" placeholder="Your email">'
        '<input id="bz_qty" placeholder="Approx. quantity">'
        '<textarea id="bz_msg" rows="2" placeholder="What do you need? (occasion, timeline)"></textarea>'
        f'<button onclick="b2bSend(\'{b2b_to}\')">Request a wholesale quote</button>'
        '</div></div>')
    return gift_html + b2b_html


def _save_web_jpg(src: Path, dest: Path, max_dim: int = 900, quality: int = 80) -> None:
    """Write an optimized JPEG copy of src to dest (for lazy-loaded assets)."""
    from PIL import Image
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail((max_dim, max_dim), Image.LANCZOS)
    im.save(dest, "JPEG", quality=quality, optimize=True)


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

    def _emit(src: Path, fname: str) -> str:
        """Return a data-URI (inline mode) or a lazy-loaded relative URL."""
        if external_assets:
            _save_web_jpg(src, assets / fname)
            return f"assets/{fname}"
        return _web_img(src)

    # Build a compact JS data array.
    listings = []
    for b in bundles:
        gallery = sorted((kit_dir).glob(f"{b.listing_n:02d}_*/gallery/*.png"))
        if not gallery:
            continue
        qf = next(iter(sorted(kit_dir.glob(f"{b.listing_n:02d}_*/quote.txt"))), None)
        quote_txt = ""
        if qf:
            try:
                import re as _re
                quote_txt = _re.sub(r"^\s*\[TEST MODE[^\]]*\]\s*", "",
                                    qf.read_text(encoding="utf-8")).strip()
            except Exception:  # noqa: BLE001
                quote_txt = ""
        if not quote_txt:
            quote_txt = ("You make every day brighter. "
                         "Today, and always - with all my love.")
        entry = {
            "n": b.listing_n,
            "quote": quote_txt,
            "title": b.title.split(" | ")[0],
            "full_title": b.title,
            "price": f"{ETSY_DEFAULT_LISTING_PRICE:.2f}",
            "desc": b.description,
            "imgs": [_emit(p, f"{b.listing_n:02d}_g{i:02d}.jpg")
                     for i, p in enumerate(gallery)],
        }
        # Real per-frame / per-material previews (tap a frame -> see the look).
        if frame_picker:
            poster = next(iter(sorted(
                kit_dir.glob(f"{b.listing_n:02d}_*/poster*.png"))), None)
            if poster:
                try:
                    if external_assets:
                        from quoteforge.images.frame_preview import format_preview_files
                        files = format_preview_files(
                            poster, assets, f"{b.listing_n:02d}f")
                        if files:
                            entry["formats"] = [
                                {"name": n, "img": f"assets/{fn}",
                                 "price": fmt_price.get(n)} for n, fn in files]
                    else:
                        from quoteforge.images.frame_preview import format_preview_datauris
                        fmts = format_preview_datauris(poster)
                        if fmts:
                            entry["formats"] = [{"name": n, "img": d,
                                                 "price": fmt_price.get(n)}
                                                for n, d in fmts]
                except Exception:  # noqa: BLE001
                    pass
        # Card "from" price = the real lowest variation price (not a flat default).
        prices = [f["price"] for f in entry.get("formats", []) if f.get("price")]
        if prices:
            entry["price"] = f"{min(prices):.2f}"
        listings.append(entry)
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
    sizemap_json = json.dumps(sizemap)

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
    banner_src = _web_img(hero_img, 1600) if hero_img else (
        _web_img(banner, 1400) if banner.exists() else "")
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
        packages_html = packages_section(_b2b or owner)
    except Exception:  # noqa: BLE001
        packages_html = ""

    gate = "" if not password else f"""
<div id="gate">
  <div class="gatebox">
    {f'<img src="{logo_src}" class="glogo">' if logo_src else ''}
    <h2>{SHOP_NAME}</h2>
    <p>This preview is private. Please enter the password to view.</p>
    <input id="pw" type="password" placeholder="Password" onkeydown="if(event.key==='Enter')check()">
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
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SHOP_NAME} - Personalized Wall Art</title>
{_analytics_snippet()}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Inter:wght@400;500;600&family=Playfair+Display:wght@500;600;700&family=Montserrat:wght@400;600&family=Lora:wght@400;600&family=Dancing+Script:wght@600;700&family=Oswald:wght@500&display=swap" rel="stylesheet">
<style>
 :root{{--green:#103d2e;--green-d:#0b2c21;--gold:#c9a84c;--gold-d:#b3902f;
   --cream:#f7f4ee;--ink:#23302b;--muted:#6b7a72;--line:#e7e1d6}}
 *{{box-sizing:border-box}}
 body{{font-family:'Inter',-apple-system,Segoe UI,Arial,sans-serif;margin:0;
   background:var(--cream);color:var(--ink);-webkit-font-smoothing:antialiased}}
 h1,h2,h3,.serif{{font-family:'Cormorant Garamond',Georgia,serif;font-weight:600;
   letter-spacing:.2px}}
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
 .bundle{{max-width:1100px;margin:30px auto;padding:0 20px;text-align:center}}
 .bundle h2{{font-size:28px;color:var(--green);margin:0 0 6px}}
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
 .hero{{position:relative}} .hero-banner{{width:100%;display:block}}
 .hero-fallback{{background:linear-gradient(160deg,#103d2e,#0b2c21);color:#fff;
   padding:64px 20px;text-align:center}}
 .hero-fallback h1{{font-size:44px;margin:0;color:#fff}}
 .hero-overlay{{position:absolute;inset:0;display:flex;flex-direction:column;
   align-items:center;justify-content:center;text-align:center;
   background:linear-gradient(rgba(8,30,22,.18),rgba(8,30,22,.45));color:#fff;padding:20px}}
 .hero-overlay h1{{font-size:clamp(30px,5vw,52px);margin:0;color:#fff;
   text-shadow:0 2px 18px rgba(0,0,0,.4)}}
 .hero-overlay p{{font-size:clamp(14px,2vw,19px);margin:10px 0 0;max-width:620px;
   text-shadow:0 1px 10px rgba(0,0,0,.45)}}
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
 .grid{{max-width:1200px;margin:26px auto 50px;display:grid;
   grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:26px;padding:0 20px}}
 .card{{background:#fff;border:1px solid var(--line);border-radius:14px;
   overflow:hidden;cursor:pointer;transition:transform .18s,box-shadow .18s;
   display:flex;flex-direction:column}}
 .card:hover{{transform:translateY(-5px);box-shadow:0 14px 34px rgba(16,61,46,.14)}}
 .card .hero{{width:100%;display:block;aspect-ratio:1/1;object-fit:cover}}
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
 /* Ask Ange chat */
 #angeBtn{{position:fixed;right:20px;bottom:20px;z-index:60;background:var(--green);
   color:#fff;border:none;border-radius:30px;padding:13px 20px;font-size:15px;
   font-weight:600;cursor:pointer;box-shadow:0 8px 24px rgba(16,61,46,.35)}}
 #angeBtn:hover{{background:var(--green-d)}}
 #angePanel{{position:fixed;right:20px;bottom:78px;z-index:61;width:340px;
   max-width:92vw;background:#fff;border:1px solid var(--line);border-radius:16px;
   box-shadow:0 20px 50px rgba(0,0,0,.3);display:none;overflow:hidden}}
 .angehdr{{background:var(--green);color:#e8d8a8;padding:13px 16px;
   font-family:'Cormorant Garamond',serif;font-size:20px}}
 .angehdr small{{display:block;font-family:Inter,sans-serif;font-size:11px;
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
 .shopocc{{max-width:1000px;margin:18px auto 0;padding:0 20px;text-align:center}}
 .shopocc .lbl{{font-size:13px;color:var(--muted);margin-bottom:8px}}
 .occrow{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}}
 .occhip{{background:#fff;border:1px solid var(--line);border-radius:18px;
   padding:7px 14px;font-size:13px;color:var(--green)}}
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
 .fpick .lbl{{font-size:13px;color:var(--green);margin-bottom:8px;font-weight:600}}
 .fchips{{display:flex;flex-wrap:wrap;gap:7px}}
 .fchip{{border:1px solid #cdbf98;background:#fff;border-radius:18px;padding:7px 13px;
   font-size:12.5px;cursor:pointer;transition:.12s;white-space:nowrap}}
 .fchip:hover{{border-color:var(--gold);background:#fffaf0}}
 .fchip.sel{{background:var(--green);color:#fff;border-color:var(--green);
   box-shadow:0 2px 8px rgba(16,61,46,.25)}}
 .perso{{margin-top:14px;background:#f3efe6;border:1px solid var(--line);
   border-radius:12px;padding:12px}}
 .perso .lbl{{font-size:13px;color:var(--green);font-weight:600;margin-bottom:8px}}
 .sw{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}
 .sw span{{width:26px;height:26px;border-radius:50%;cursor:pointer;
   border:2px solid #fff;box-shadow:0 0 0 1px #cdbf98;transition:.12s}}
 .sw span.sel{{box-shadow:0 0 0 2px var(--green);transform:scale(1.12)}}
 .perso input,.perso textarea{{width:100%;border:1px solid #cdbf98;border-radius:8px;
   padding:8px 10px;font-size:13px;font-family:inherit;margin-bottom:6px}}
 .perso .note{{font-size:11px;color:var(--muted)}}
 .perso .cc{{font-size:11px;color:var(--muted);text-align:right;margin:-2px 0 4px}}
 .fonts{{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:6px}}
 .fonts .fchip{{font-size:14px}}
 .perso .swrow{{font-size:11px;color:var(--muted);margin:6px 0 4px;font-weight:500}}
 #mcanvas{{width:100%;border-radius:8px;border:1px solid var(--line);display:block;
   margin-bottom:8px;background:#103d2e}}
 .orderbox{{margin-top:14px;background:#fff;border:1px solid var(--line);
   border-radius:12px;padding:12px}}
 .orderbox .lbl{{font-size:13px;color:var(--green);font-weight:600;margin-bottom:8px}}
 .orow{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-bottom:8px}}
 .orow label{{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:3px}}
 .orow select{{padding:8px;border:1px solid #cdbf98;border-radius:8px;font-size:13px}}
 .addbtn{{background:var(--green);color:#fff;border:none;border-radius:18px;
   padding:9px 16px;font-size:13px;font-weight:600;cursor:pointer}}
 .addbtn:hover{{background:var(--green-d)}}
 .cart{{font-size:13px}} .cart .line{{display:flex;justify-content:space-between;
   padding:4px 0;border-bottom:1px dashed #e7e1d6}}
 .cart .rm{{color:#b3261e;cursor:pointer;margin-left:8px}}
 .cart .tot{{font-weight:700;color:var(--green);padding-top:6px}}
 .uploadbox{{margin-top:10px;border-top:1px solid var(--line);padding-top:10px}}
 .uploadbox input[type=file]{{font-size:12px}}
 .upok{{color:#0f7a3d}} .upbad{{color:#b3261e}}
 .mbox h2{{font-size:24px;margin:2px 0 6px;color:var(--green);line-height:1.25}}
 .mprice{{font-weight:600;color:var(--green);font-size:24px;margin:6px 0}}
 .mdesc{{font-size:13px;line-height:1.65;color:#4a564f;white-space:pre-wrap;
   border-top:1px solid var(--line);margin-top:14px;padding-top:12px}}
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
 @media(max-width:560px){{.mbody{{padding:16px}} .nav .bn{{font-size:20px}}}}
</style></head><body>
{gate}
<div id="site" style="{site_style}">
 <div class="nav">
   {f'<img src="{logo_src}" alt="{SHOP_NAME}">' if logo_src else ''}
   <span class="bn">{SHOP_NAME}</span>
   <button class="navquiz" onclick="openQuiz()">🎁 Gift Finder</button>
 </div>
 <div class="hero">
   {f'<img class="hero-banner" src="{banner_src}">' if banner_src else '<div class="hero-fallback"><h1>'+SHOP_NAME+'</h1></div>'}
   <div class="hero-overlay">
     <h1 data-ab="hero_h1">Personalized wall art for life's most meaningful moments</h1>
     <p>Custom names, dates &amp; your own words - hand-designed and made to order.</p>
   </div>
 </div>
 <div class="trust">
   <span>✦ <b>Free digital proof</b> before printing</span>
   <span>✦ <b>Made to order</b>, just for you</span>
   <span>✦ <b>Premium</b> museum-quality materials</span>
   <span>✦ <b>Worldwide</b> tracked shipping</span>
 </div>
 {sproof_html}
 {cutoff_html}
 {"<div class='uatbar'>👋 Thanks for helping review " + SHOP_NAME +
  "! <b>Tap any piece</b> to see all its photos &amp; details, rate it, then "
  "tap <b>feedback</b>. "
  "<a href='mailto:" + owner + "?subject=Joffiels%20overall%20feedback'>"
  "Send overall feedback</a></div>" if uat else ""}
 <div class="intro">
   <h2>Gifts they'll keep forever</h2>
   <p>Every piece is custom-made for your recipient - a name, an occasion, their
     story. Choose poster, framed, canvas, acrylic or metal at checkout; a free
     digital proof is sent before anything is printed.</p>
 </div>
 <div class="grid" id="grid"></div>
 <div class="bundle">
   <h2>Build a gallery set &amp; save</h2>
   <p class="gsub">Pick 2-3 designs for a wall or a family collection - bundle
     discounts apply automatically ({bundle_discount_text}).</p>
   <div class="bgrid" id="bgrid"></div>
   <div class="btot" id="btot">Select 2 or more to see your set price.</div>
 </div>
 {reviews_html}
 {gallery_html}
 {_competitive_sections()}
 {packages_html}
 {_gift_and_b2b_section(owner)}
 <div class="foot">
   <div class="fbn">{SHOP_NAME}</div>
   <p>Personalized wall art, made to order - free proof before printing.<br>
   Sample preview for review. Prices shown are starting prices; every item is
   personalized to order.</p>
 </div>
</div>

<div id="quiz" onclick="if(event.target.id==='quiz')closeQuiz()">
  <div class="qbox">
    <span class="qclose" onclick="closeQuiz()">&times;</span>
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

<div id="exitpop" onclick="if(event.target.id==='exitpop')closeExit()">
  <div class="xbox">
    <span class="qclose" onclick="closeExit()">&times;</span>
    <h2>Wait - here's {promo_pct}% off your first piece</h2>
    <p class="qsub">Join the insider list for an instant discount code, early
      access to new designs &amp; seasonal gift guides.</p>
    <div id="xform">
      <input id="xemail" type="email" placeholder="you@email.com"
        onkeydown="if(event.key==='Enter')submitExit()">
      <button class="qgo" onclick="submitExit()">Send my code &rarr;</button>
    </div>
    <div id="xmsg"></div>
    <p class="ftc">No spam - unsubscribe anytime. One email, one code.</p>
  </div>
</div>

<div id="modal" onclick="if(event.target.id==='modal')closeM()">
 <div class="mbox">
   <span class="closex" onclick="closeM()">&times;</span>
   <div class="mbody">
     <div class="mleft">
       <canvas id="mcanvas" width="520" height="650"></canvas>
       <div class="fpick" id="mfpick" style="display:none">
         <div class="lbl">👉 Choose your frame / material:</div>
         <div class="fchips" id="mfchips"></div>
       </div>
       <div class="swrow" style="font-size:11px;color:#6b7a72;margin:8px 0 4px">📷 See it styled in a room (tap to open):</div>
       <div class="mthumbs" id="mthumbs"></div>
     </div>
     <div class="mright">
       <h2 id="mtitle"></h2><div class="mprice" id="mprice"></div>
       <div style="font-size:12px;color:#5a6b62;margin:-2px 0 8px">
         Available as: {materials_line}<br>
         <b>Frame not included</b> unless you choose a Framed option
         (6 frame styles: Essential → Classic → Premium). Canvas is gallery-wrapped (open).
       </div>
       <div class="perso">
         <div class="lbl">🎨 Your colors - the preview on the left updates live</div>
         <div class="swrow">Background</div>
         <div class="sw" id="mbg"></div>
         <div class="swrow">Text color</div>
         <div class="sw" id="mtxt"></div>
         <div class="swrow">🛋️ Your room wall <span style="color:#9aa49c;font-weight:400">(preview against your wall color)</span></div>
         <div class="sw" id="mwall"></div>
         <div class="swrow">Your wording</div>
         <textarea id="mtext" maxlength="250" rows="3" oninput="onText()"
           placeholder="Type your own message (optional) - previews live"></textarea>
         <div class="cc"><span id="mcc">0 / 250</span> characters</div>
         <div class="swrow">Font</div>
         <div class="fonts" id="mfonts"></div>
         <div class="note">Background, text color, font &amp; wording are all free -
           the preview updates instantly and final details are confirmed on your
           FREE digital proof before printing.</div>
       </div>
       <div class="orderbox">
         <div class="lbl">🛒 Build your order (mix sizes &amp; quantities)</div>
         <div class="orow">
           <label>Size <select id="msize"></select></label>
           <label>Qty <select id="mqty"></select></label>
           <button class="addbtn" data-ab="primary_cta" onclick="addToOrder()">Add to order</button>
         </div>
         <div id="mcart" class="cart"></div>
         <div class="uploadbox">
           <div class="lbl">📷 Add your own photo (optional)</div>
           <input type="file" id="mupload"
             accept="image/jpeg,image/png,application/pdf,image/tiff"
             onchange="checkUpload()">
           <div id="muploadmsg" class="note"></div>
           <div class="note">High-resolution JPG/PNG/PDF/TIFF only - we auto-check
             quality and ask for a better photo if needed before printing.</div>
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
       <div class="mdesc" id="mdesc"></div>
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
 function render(){{
   const g = document.getElementById('grid');
   g.innerHTML = DATA.map((d,i) => `
     <div class="card" onclick="openM(${{i}})">
       <img class="hero" loading="lazy" src="${{d.imgs[0]}}" alt="">
       <div class="cap"><div class="ttl">${{d.title}}</div>
         <div class="pr">Starting at $${{d.price}}</div>
         <div class="prsub">${{MAT_SHORT}} &middot; ${{OPT_COUNT}} options to $${{PRICE_HI}}</div>
         <span class="fb">Tap to choose frame / canvas &amp; see it</span>
       </div>
     </div>`).join('');
 }}
 function openM(i){{
   CUR = i; RATING = 0; paintStars();
   const d = DATA[i];
   const roomShots = (d.formats && d.formats.length) ? d.formats.map(f=>f.img) : d.imgs;
   document.getElementById('mthumbs').innerHTML = roomShots.map(
     s=>`<img src="${{s}}" onclick="window.open('${{s}}','_blank')">`).join('');
   const fp=document.getElementById('mfpick'), fc=document.getElementById('mfchips');
   if(d.formats && d.formats.length){{
     fc.innerHTML=d.formats.map((f,j)=>
       `<span class="fchip${{j===0?' sel':''}}" id="fc${{j}}" onclick="pickFmt(${{i}},${{j}})">${{f.name}}${{f.price?` - $${{f.price}}`:''}}</span>`).join('');
     fp.style.display='block';
     if(d.formats[0].price) document.getElementById('mprice').textContent="from $"+d.formats[0].price;
   }} else {{ fp.style.display='none'; }}
   document.getElementById('mtitle').textContent = d.full_title;
   if(!(d.formats && d.formats.length && d.formats[0].price))
     document.getElementById('mprice').textContent = "from $" + d.price;
   document.getElementById('mdesc').textContent = d.desc;
   document.getElementById('mratemsg').textContent = "";
   CURQUOTE = d.quote || ""; SELBG = BGCOLORS[0]; SELTXT = TXTCOLORS[0];
   SELFONT = FONTS[0][1]; SELWALL = WALLS[0][0];
   CURFMT = (d.formats && d.formats.length) ? d.formats[0].name : "";
   var mt=document.getElementById('mtext'); if(mt) mt.value="";
   var cc=document.getElementById('mcc'); if(cc) cc.textContent="0 / "+MAXCHARS;
   renderBg(); renderTxt(); renderWall(); renderFonts(); drawArt();
   fillQty(); fillSizes(); renderCart();
   var um=document.getElementById('muploadmsg'); if(um) um.textContent="";
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
   ["Oswald","'Oswald',sans-serif"]];
 const MAXCHARS = 250;
 const SIZEMAP = {sizemap_json};
 let CART = [];
 const QD = {qty_discount_json};
 function qdisc(q){{let best=0; for(const t of QD){{if(q>=t[0]&&t[1]>best)best=t[1];}} return best;}}
 function fillQty(){{const s=document.getElementById('mqty'); if(s&&!s.options.length){{
   for(let i=1;i<=10;i++){{const o=document.createElement('option');o.value=i;o.text=i;s.add(o);}}}}}}
 function fillSizes(){{const sel=document.getElementById('msize'); if(!sel)return;
   const rows=SIZEMAP[CURFMT]||[];
   sel.innerHTML=rows.map(r=>`<option value="${{r.size}}|${{r.price}}">${{r.size}} in - $${{r.price}}</option>`).join('');}}
 function addToOrder(){{const sv=(document.getElementById('msize')||{{}}).value; if(!sv)return;
   const p=sv.split('|'); const qty=parseInt((document.getElementById('mqty')||{{}}).value||'1');
   CART.push({{fmt:CURFMT,size:p[0],unit:parseFloat(p[1]),qty:qty}}); renderCart();
   clearDraft(); if(typeof abConvert==='function') abConvert();}}
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
 function renderCart(){{const c=document.getElementById('mcart'); if(!c)return;
   if(!CART.length){{c.innerHTML='<div class="note">No items yet - choose size + qty, then Add.</div>';return;}}
   let tot=0; c.innerHTML=CART.map((l,i)=>{{const d=qdisc(l.qty);
     const unit=+(l.unit*(1-d)).toFixed(2); const sub=+(unit*l.qty).toFixed(2); tot+=sub;
     return `<div class="line"><span>${{l.qty}}x ${{l.fmt}} ${{l.size}}${{d?` (${{Math.round(d*100)}}% off)`:''}}</span>`+
       `<span>$${{sub.toFixed(2)}} <span class="rm" onclick="rmLine(${{i}})">remove</span></span></div>`;}}).join('')+
     `<div class="line tot"><span>Order total</span><span>$${{tot.toFixed(2)}}</span></div>`;}}
 function checkUpload(){{const inp=document.getElementById('mupload'),msg=document.getElementById('muploadmsg');
   const f=inp.files&&inp.files[0]; if(!f){{msg.textContent='';return;}}
   if(!/(jpe?g|png|pdf|tiff?)$/i.test(f.name)){{msg.className='note upbad';
     msg.textContent='Unsupported format. Use JPG, PNG, PDF or TIFF.';return;}}
   if(/pdf$/i.test(f.name)){{msg.className='note upok';msg.textContent="PDF received - we'll verify print quality.";return;}}
   const inches=((document.getElementById('msize')||{{}}).value||'18x24|0').split('|')[0].split('x').map(parseFloat);
   const img=new Image();
   img.onload=function(){{const nw=(inches[0]||18)*150, nh=(inches[1]||24)*150;
     const big=Math.max(img.width,img.height), small=Math.min(img.width,img.height);
     if(big>=Math.max(nw,nh)&&small>=Math.min(nw,nh)){{msg.className='note upok';
       msg.textContent=`Great - ${{img.width}}x${{img.height}}px works for ${{inches[0]}}x${{inches[1]}}".`;}}
     else{{msg.className='note upbad';
       msg.textContent=`Only ${{img.width}}x${{img.height}}px - too low for a sharp ${{inches[0]}}x${{inches[1]}}" print. Please upload a higher-resolution original.`;}}
     URL.revokeObjectURL(img.src);}};
   img.onerror=function(){{msg.className='note upbad';msg.textContent='Could not read image - try another file.';}};
   img.src=URL.createObjectURL(f);}}
 let SELBG=BGCOLORS[0], SELTXT=TXTCOLORS[0], SELFONT=FONTS[0][1], CURQUOTE="";
 function renderFonts(){{
   document.getElementById('mfonts').innerHTML = FONTS.map((f,k)=>
     `<span class="fchip ${{f[1]===SELFONT?'sel':''}}" style="font-family:${{f[1]}}" onclick="pickFont(${{k}})">${{f[0]}}</span>`).join('');
 }}
 function pickFont(k){{ SELFONT=FONTS[k][1];
   document.querySelectorAll('#mfonts .fchip').forEach((e,m)=>e.classList.toggle('sel',m===k)); drawArt(); }}
 function onText(){{
   const v=(document.getElementById('mtext').value||'');
   document.getElementById('mcc').textContent = v.length + ' / ' + MAXCHARS;
   drawArt();
 }}
 function renderBg(){{
   document.getElementById('mbg').innerHTML = BGCOLORS.map((c,k)=>
     `<span style="background:${{c}}" class="${{c===SELBG?'sel':''}}" onclick="pickBg('${{c}}',this)" title="${{c}}"></span>`).join('');
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
 function pickTxt(c,el){{ SELTXT=c;
   document.querySelectorAll('#mtxt span').forEach(e=>e.classList.toggle('sel',e===el)); drawArt(); }}
 const FRAMECOLOR = {{"Premium Solid Oak":"#b28e60","Premium Walnut":"#5c4030",
   "Gallery Gold":"#c6a052","Classic Black Wood":"#1c1c1e",
   "Classic White Wood":"#f4f3ef","Slim Black":"#1c1c1e"}};
 let CURFMT="";
 function frameSpec(){{
   if(CURFMT.indexOf('Framed - ')===0){{
     const n=CURFMT.slice(9);
     return {{t:(n==='Slim Black'?0.028:0.06), color:FRAMECOLOR[n]||'#1c1c1e', mat:true}};
   }}
   if(CURFMT.indexOf('Acrylic')===0||CURFMT.indexOf('Metal')===0)
     return {{t:0.014, color:'#c9ccce', mat:false}};
   return null;  // Poster / Canvas = unframed
 }}
 function drawArt(){{
   const cv=document.getElementById('mcanvas'); if(!cv) return;
   const ctx=cv.getContext('2d'), W=cv.width, H=cv.height;
   ctx.fillStyle=SELWALL; ctx.fillRect(0,0,W,H);             // room wall
   const m=16, spec=frameSpec();
   let x=m,y=m,w=W-2*m,h=H-2*m;
   // drop shadow for depth
   ctx.fillStyle="rgba(0,0,0,.18)"; ctx.fillRect(x+5,y+6,w,h);
   if(spec){{ const t=spec.t*w;
     ctx.fillStyle=spec.color; ctx.fillRect(x,y,w,h);          // frame
     x+=t; y+=t; w-=2*t; h-=2*t;
     if(spec.mat){{ const mm=0.05*w; ctx.fillStyle="#f7f5ef";
       ctx.fillRect(x,y,w,h); x+=mm; y+=mm; w-=2*mm; h-=2*mm; }}
   }}
   ctx.fillStyle=SELBG; ctx.fillRect(x,y,w,h);                 // art background
   const typed=(document.getElementById('mtext')||{{}}).value;
   const text=(typed&&typed.trim())?typed.trim():CURQUOTE;
   ctx.fillStyle=SELTXT; ctx.textAlign='center';
   const maxW=w*0.84; let fs=Math.round(h*0.10);
   function wrap(f){{ctx.font='600 '+f+'px '+SELFONT;
     const words=text.split(/\\s+/); let lines=[],cur='';
     for(const wd of words){{const tt=(cur+' '+wd).trim();
       if(ctx.measureText(tt).width<=maxW){{cur=tt;}}else{{lines.push(cur);cur=wd;}}}}
     if(cur)lines.push(cur); return lines;}}
   let lines=wrap(fs);
   while((lines.length*fs*1.32)>h*0.82 && fs>9){{fs-=1; lines=wrap(fs);}}
   const lh=fs*1.34; let ty=y+(h-lines.length*lh)/2+fs*0.9;
   for(const ln of lines){{ctx.fillText(ln,x+w/2,ty); ty+=lh;}}
   saveDraft();
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
   const f = DATA[i].formats[j];
   if(f.price) document.getElementById('mprice').textContent = "from $" + f.price;
   document.querySelectorAll('#mfchips .fchip').forEach((e,k)=>
     e.classList.toggle('sel', k===j));
   CURFMT = f.name; drawArt(); fillSizes();   // update sizes for this format
 }}
 function b2bSend(to){{
   const g=id=>(document.getElementById(id)||{{}}).value||'';
   const body=encodeURIComponent(
     "Name: "+g('bz_name')+"\\nCompany: "+g('bz_co')+"\\nEmail: "+g('bz_email')+
     "\\nQuantity: "+g('bz_qty')+"\\n\\nDetails:\\n"+g('bz_msg'));
   window.location.href="mailto:"+to+"?subject="+
     encodeURIComponent("Wholesale / bulk gifting inquiry")+"&body="+body;
 }}
 function closeM(){{document.getElementById('modal').style.display='none';}}
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
     `<div class="bopt ${{BSEL.has(i)?'sel':''}}" onclick="toggleBundle(${{i}})">`+
     `<span class="bcheck">${{BSEL.has(i)?'✓':'+'}}</span>`+
     `<img src="${{d.imgs[0]}}" loading="lazy"><div>${{d.title.slice(0,28)}}</div></div>`).join('');
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
   t.innerHTML=`<b>${{n}} prints selected</b> &middot; ${{Math.round(disc*100)}}% off &middot; `+
     `set from <b>$${{total}}</b> <span class="bsave">(save $${{saved}})</span> `+
     `&middot; mix sizes/frames at checkout`;
 }}
 function toggleBundle(i){{ if(BSEL.has(i))BSEL.delete(i); else BSEL.add(i); renderBundle(); }}
 renderBundle();
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
 function knownEmail(){{ try{{return localStorage.getItem('jf_email')||"";}}catch(e){{return "";}} }}
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
 const SIGNUP_URL = "{signup_url}";
 let EXIT_SHOWN = false;
 function _exitDone(){{ try{{localStorage.setItem('jf_exit','1');}}catch(e){{}} }}
 function _exitSeen(){{ try{{return localStorage.getItem('jf_exit')==='1';}}catch(e){{return false;}} }}
 function openExit(){{ if(EXIT_SHOWN||_exitSeen())return; EXIT_SHOWN=true;
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
    return out


def build_preview(n: int = 1, kit_dir=None, out_path=None) -> Path:
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
   <div class="note">Free digital proof before printing - nothing prints until you approve.</div>
   <div class="tags">{tags}</div>
   <div class="desc">{desc}</div>
 </div>
</div>
<div style="text-align:center;color:#aaa;font-size:12px;margin:24px">
  Mock preview generated by QuoteForge - not a live Etsy page.</div>
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
