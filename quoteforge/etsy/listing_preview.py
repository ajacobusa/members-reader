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


def _web_img(path: Path, max_dim: int = 900, quality: int = 82) -> str:
    """Downscaled JPEG data-URI so the shared page loads fast (small payload)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_shop_home(password: str = "Jesus", numbers=None, kit_dir=None,
                    out_path=None, uat: bool = True) -> Path:
    """A polished, password-gated shop-home / UAT page: logo+banner, a 20-listing
    grid, a per-listing detail modal (all 5 images + description), and one-click
    feedback (mailto to the owner). Shareable as one link."""
    import json
    from quoteforge.config import (
        OUTPUT_DIR, ETSY_DEFAULT_LISTING_PRICE, SHOP_NAME, REPORT_RECIPIENT,
    )
    from quoteforge.etsy.listing_seo import build_launch_seo

    kit_dir = Path(kit_dir) if kit_dir else (OUTPUT_DIR / "launch_kit")
    brand = Path("brand")
    bundles = build_launch_seo()
    if numbers:
        bundles = [b for b in bundles if b.listing_n in numbers]

    # Build a compact JS data array (each image embedded once).
    listings = []
    for b in bundles:
        gallery = sorted((kit_dir).glob(f"{b.listing_n:02d}_*/gallery/*.png"))
        if not gallery:
            continue
        listings.append({
            "n": b.listing_n,
            "title": b.title.split(" | ")[0],
            "full_title": b.title,
            "price": f"{ETSY_DEFAULT_LISTING_PRICE:.2f}",
            "desc": b.description,
            "imgs": [_web_img(p) for p in gallery],
        })
    data_json = json.dumps(listings)
    owner = REPORT_RECIPIENT or "owner@example.com"

    logo = brand / "joffiels_logo_green_gold.png"
    banner = brand / "joffiels_banner.png"
    logo_src = _web_img(logo, 240) if logo.exists() else ""
    banner_src = _web_img(banner, 1400) if banner.exists() else ""
    pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest() if password else ""

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
<style>
 *{{box-sizing:border-box}} body{{font-family:'Helvetica Neue',Arial,sans-serif;
   margin:0;background:#f6f3ee;color:#23302b}}
 /* gate */
 #gate{{position:fixed;inset:0;background:#0f3d2e;display:flex;align-items:center;
   justify-content:center;z-index:99}}
 .gatebox{{background:#fff;border-radius:14px;padding:34px;max-width:360px;
   text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.3)}}
 .glogo{{width:120px;margin-bottom:8px}}
 .gatebox h2{{font-family:Georgia,serif;color:#0f3d2e;margin:6px 0}}
 .gatebox p{{color:#666;font-size:14px}}
 #pw{{width:100%;padding:12px;border:1px solid #ccc;border-radius:8px;
   font-size:16px;margin:10px 0}}
 .gatebox button{{background:#0f3d2e;color:#fff;border:none;padding:12px 0;
   width:100%;border-radius:24px;font-size:16px;cursor:pointer}}
 #err{{display:none;color:#b3261e;font-size:13px;margin-top:10px}}
 /* hero */
 .hero-banner{{width:100%;display:block}}
 .ribbon{{background:#0f3d2e;color:#e8d8a8;text-align:center;padding:14px;
   font-family:Georgia,serif;font-size:18px}}
 .tag{{text-align:center;color:#5a6b62;margin:18px 16px;font-size:16px;line-height:1.5}}
 .grid{{max-width:1180px;margin:10px auto 40px;display:grid;
   grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px;padding:0 16px}}
 .card{{background:#fff;border:1px solid #e6e0d6;border-radius:12px;overflow:hidden;
   transition:transform .15s,box-shadow .15s}}
 .card:hover{{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.10)}}
 .card .hero{{width:100%;display:block;aspect-ratio:1/1;object-fit:cover}}
 .cap{{padding:12px 14px}}
 .ttl{{font-size:14px;line-height:1.45;height:60px;overflow:hidden;color:#2b3a33}}
 .pr{{margin-top:8px;font-weight:bold;color:#0f3d2e;font-size:16px}}
 .fb{{display:inline-block;margin-top:8px;font-size:12px;color:#0f3d2e;
   text-decoration:none;border:1px solid #0f3d2e;border-radius:14px;padding:3px 10px}}
 .uatbar{{background:#fff7e6;border:1px solid #f0e0b8;color:#6b5a2b;
   margin:16px;padding:12px 16px;border-radius:8px;font-size:14px;text-align:center}}
 .uatbar a{{color:#0f3d2e;font-weight:bold}}
 .foot{{text-align:center;color:#9aa39d;font-size:12px;margin:30px 16px}}
 /* modal */
 #modal{{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;
   align-items:flex-start;justify-content:center;z-index:50;overflow:auto;padding:20px}}
 .mbox{{background:#fff;border-radius:12px;max-width:820px;width:100%;margin:20px;
   overflow:hidden}}
 .mbody{{display:flex;flex-wrap:wrap;gap:18px;padding:18px}}
 .mleft{{flex:1;min-width:280px}} .mright{{flex:1;min-width:260px}}
 #mmain{{width:100%;border-radius:8px}}
 .mthumbs{{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}}
 .mthumbs img{{width:60px;height:60px;object-fit:cover;border:1px solid #d8cdb6;
   border-radius:5px;cursor:pointer}}
 .mbox h2{{font-size:18px;margin:0 0 6px}} .mprice{{font-weight:bold;
   color:#0f3d2e;font-size:22px;margin:6px 0}}
 .mdesc{{font-size:13px;line-height:1.6;color:#444;white-space:pre-wrap}}
 .closex{{float:right;font-size:24px;cursor:pointer;color:#888;padding:8px 14px}}
 .fbbtn{{display:block;background:#c9a84c;color:#22301e;text-align:center;
   text-decoration:none;padding:12px;border-radius:24px;font-weight:bold;margin:12px 0}}
</style></head><body>
{gate}
<div id="site" style="{site_style}">
 {f'<img class="hero-banner" src="{banner_src}">' if banner_src else f'<div class="ribbon">{SHOP_NAME}</div>'}
 <div class="ribbon">Personalized wall art for life's most meaningful moments</div>
 {"<div class='uatbar'>👋 Thanks for helping review " + SHOP_NAME +
  "! <b>Tap any item</b> to see all its photos &amp; details, then tap "
  "<b>“Tell us what you think”</b> to send quick feedback. "
  "<a href='mailto:" + owner + "?subject=Joffiels%20overall%20feedback'>"
  "Send overall feedback</a></div>" if uat else ""}
 <p class="tag">Every piece is custom-made for your recipient - a name, an occasion,
   their story. A free digital proof is sent before anything is printed.</p>
 <div class="grid" id="grid"></div>
 <div class="foot">{SHOP_NAME} - sample preview for review. Prices shown are starting
   prices; every item is personalized to order.</div>
</div>

<div id="modal" onclick="if(event.target.id==='modal')closeM()">
 <div class="mbox">
   <span class="closex" onclick="closeM()">&times;</span>
   <div class="mbody">
     <div class="mleft"><img id="mmain"><div class="mthumbs" id="mthumbs"></div></div>
     <div class="mright">
       <h2 id="mtitle"></h2><div class="mprice" id="mprice"></div>
       <a id="mfb" class="fbbtn" href="#">💬 Tell us what you think</a>
       <div class="mdesc" id="mdesc"></div>
     </div>
   </div>
 </div>
</div>

<script>
 const DATA = {data_json};
 const OWNER = "{owner}";
 const UAT = {str(bool(uat)).lower()};
 function fbLink(t){{
   const s = encodeURIComponent("Joffiels feedback: " + t);
   const body = encodeURIComponent(
     "Would you buy this as a gift?  (yes / maybe / no)\\n\\n" +
     "Does the price feel right?\\n\\n" +
     "Anything to change about the design or wording?\\n\\n");
   return "mailto:" + OWNER + "?subject=" + s + "&body=" + body;
 }}
 function render(){{
   const g = document.getElementById('grid');
   g.innerHTML = DATA.map((d,i) => `
     <div class="card" onclick="openM(${{i}})">
       <img class="hero" src="${{d.imgs[0]}}" alt="">
       <div class="cap"><div class="ttl">${{d.title}}</div>
         <div class="pr">from $${{d.price}}</div>
         ${{UAT?`<span class="fb">Tap to view &amp; review</span>`:``}}
       </div>
     </div>`).join('');
 }}
 function openM(i){{
   const d = DATA[i];
   document.getElementById('mmain').src = d.imgs[0];
   document.getElementById('mthumbs').innerHTML = d.imgs.map(
     s=>`<img src="${{s}}" onclick="document.getElementById('mmain').src=this.src">`).join('');
   document.getElementById('mtitle').textContent = d.full_title;
   document.getElementById('mprice').textContent = "from $" + d.price;
   document.getElementById('mdesc').textContent = d.desc;
   const fb = document.getElementById('mfb');
   fb.href = fbLink(d.title); fb.style.display = UAT ? 'block':'none';
   document.getElementById('modal').style.display='flex';
 }}
 function closeM(){{document.getElementById('modal').style.display='none';}}
 render();
</script>
</body></html>"""
    out = Path(out_path) if out_path else (kit_dir / "shop_home.html")
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
 .top{{background:#0f3d2e;color:#e8d8a8;padding:10px 24px;font-size:20px;
   font-family:Georgia,serif}}
 .wrap{{max-width:1100px;margin:24px auto;display:flex;gap:32px;padding:0 16px}}
 .gallery{{flex:1}} .main{{width:100%;border-radius:8px;border:1px solid #e3ddd2}}
 .thumbs{{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}}
 .thumb{{width:72px;height:72px;object-fit:cover;border:2px solid #d8cdb6;
   border-radius:6px;cursor:pointer}}
 .info{{flex:1}}
 .shop{{color:#0f3d2e;font-weight:bold}} .stars{{color:#c9a84c}}
 h1{{font-size:20px;line-height:1.4;margin:6px 0}}
 .price{{font-size:28px;font-weight:bold;margin:10px 0}}
 .box{{border:1px solid #d8cdb6;border-radius:8px;padding:12px;margin:14px 0;
   background:#fff}}
 .box label{{font-size:13px;color:#555}} textarea{{width:100%;height:70px;
   margin-top:6px;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}}
 .btn{{background:#0f3d2e;color:#fff;border:none;padding:14px;width:100%;
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
 .top{{background:#0f3d2e;color:#e8d8a8;padding:18px 24px;font-family:Georgia,serif}}
 .top h1{{margin:0;font-size:24px}} .top p{{margin:4px 0 0;opacity:.85}}
 .grid{{max-width:1200px;margin:24px auto;display:grid;
   grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:22px;padding:0 16px}}
 .card{{background:#fff;border:1px solid #e3ddd2;border-radius:10px;overflow:hidden}}
 .hero{{width:100%;display:block}}
 .cap{{padding:12px}} .ttl{{font-size:14px;line-height:1.4;height:58px;overflow:hidden}}
 .pr{{font-weight:bold;font-size:20px;margin:6px 0;color:#0f3d2e}}
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
