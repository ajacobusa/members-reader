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


def build_shop_home(password: str = "Jesus", numbers=None, kit_dir=None,
                    out_path=None, uat: bool = True,
                    feedback_form_url=None, frame_picker: bool = True) -> Path:
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

    # Build a compact JS data array (each image embedded once).
    listings = []
    for b in bundles:
        gallery = sorted((kit_dir).glob(f"{b.listing_n:02d}_*/gallery/*.png"))
        if not gallery:
            continue
        entry = {
            "n": b.listing_n,
            "title": b.title.split(" | ")[0],
            "full_title": b.title,
            "price": f"{ETSY_DEFAULT_LISTING_PRICE:.2f}",
            "desc": b.description,
            "imgs": [_web_img(p) for p in gallery],
        }
        # Real per-frame / per-material previews (tap a frame -> see the look).
        if frame_picker:
            poster = next(iter(sorted(
                kit_dir.glob(f"{b.listing_n:02d}_*/poster*.png"))), None)
            if poster:
                try:
                    from quoteforge.images.frame_preview import format_preview_datauris
                    fmts = format_preview_datauris(poster)
                    if fmts:
                        entry["formats"] = [{"name": n, "img": d} for n, d in fmts]
                except Exception:  # noqa: BLE001
                    pass
        listings.append(entry)
    data_json = json.dumps(listings)
    owner = REPORT_RECIPIENT or "owner@example.com"

    # Product range + frame note for the detail modal.
    try:
        from quoteforge.etsy.variations import price_range, materials_offered
        _lo, _hi = price_range()
        materials_line = (" · ".join(m.split(" (")[0] for m in materials_offered())
                          + f" — ${_lo:.0f}–${_hi:.0f}")
    except Exception:  # noqa: BLE001
        materials_line = ""

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
{_analytics_snippet()}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
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
 .fb{{display:inline-block;margin-top:10px;font-size:12px;color:var(--green);
   text-decoration:none;border:1px solid var(--green);border-radius:16px;
   padding:5px 12px;transition:.15s}}
 .card:hover .fb{{background:var(--green);color:#fff}}
 .uatbar{{max-width:1160px;background:#fffaf0;border:1px solid #f0e2bd;
   color:#6b5a2b;margin:16px auto 0;padding:13px 18px;border-radius:10px;
   font-size:14px;text-align:center;line-height:1.55}}
 .uatbar a{{color:var(--green);font-weight:600}}
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
 .fpick{{margin-top:12px}}
 .fpick .lbl{{font-size:12px;color:var(--muted);margin-bottom:6px;font-weight:500}}
 .fchips{{display:flex;flex-wrap:wrap;gap:6px}}
 .fchip{{border:1px solid #cdbf98;background:#fff;border-radius:16px;padding:5px 11px;
   font-size:12px;cursor:pointer;transition:.12s;white-space:nowrap}}
 .fchip:hover{{border-color:var(--gold)}}
 .fchip.sel{{background:var(--green);color:#fff;border-color:var(--green)}}
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
 </div>
 <div class="hero">
   {f'<img class="hero-banner" src="{banner_src}">' if banner_src else '<div class="hero-fallback"><h1>'+SHOP_NAME+'</h1></div>'}
   <div class="hero-overlay">
     <h1>Personalized wall art for life's most meaningful moments</h1>
     <p>Custom names, dates &amp; your own words - hand-designed and made to order.</p>
   </div>
 </div>
 <div class="trust">
   <span>✦ <b>Free digital proof</b> before printing</span>
   <span>✦ <b>Made to order</b>, just for you</span>
   <span>✦ <b>Premium</b> museum-quality materials</span>
   <span>✦ <b>Worldwide</b> tracked shipping</span>
 </div>
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
 <div class="foot">
   <div class="fbn">{SHOP_NAME}</div>
   <p>Personalized wall art, made to order - free proof before printing.<br>
   Sample preview for review. Prices shown are starting prices; every item is
   personalized to order.</p>
 </div>
</div>

<div id="modal" onclick="if(event.target.id==='modal')closeM()">
 <div class="mbox">
   <span class="closex" onclick="closeM()">&times;</span>
   <div class="mbody">
     <div class="mleft"><img id="mmain"><div class="mthumbs" id="mthumbs"></div>
       <div class="fpick" id="mfpick" style="display:none">
         <div class="lbl">See it in your frame / material:</div>
         <div class="fchips" id="mfchips"></div>
       </div>
     </div>
     <div class="mright">
       <h2 id="mtitle"></h2><div class="mprice" id="mprice"></div>
       <div style="font-size:12px;color:#5a6b62;margin:-2px 0 8px">
         Available as: {materials_line}<br>
         <b>Frame not included</b> unless you choose a Framed option
         (6 frame styles: Essential → Classic → Premium). Canvas is gallery-wrapped (open).
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
       <img class="hero" src="${{d.imgs[0]}}" alt="">
       <div class="cap"><div class="ttl">${{d.title}}</div>
         <div class="pr">from $${{d.price}}</div>
         ${{UAT?`<span class="fb">Tap to view &amp; review</span>`:``}}
       </div>
     </div>`).join('');
 }}
 function openM(i){{
   CUR = i; RATING = 0; paintStars();
   const d = DATA[i];
   document.getElementById('mmain').src = d.imgs[0];
   document.getElementById('mthumbs').innerHTML = d.imgs.map(
     s=>`<img src="${{s}}" onclick="document.getElementById('mmain').src=this.src">`).join('');
   const fp=document.getElementById('mfpick'), fc=document.getElementById('mfchips');
   if(d.formats && d.formats.length){{
     fc.innerHTML=d.formats.map((f,j)=>
       `<span class="fchip" id="fc${{j}}" onclick="pickFmt(${{i}},${{j}})">${{f.name}}</span>`).join('');
     fp.style.display='block';
   }} else {{ fp.style.display='none'; }}
   document.getElementById('mtitle').textContent = d.full_title;
   document.getElementById('mprice').textContent = "from $" + d.price;
   document.getElementById('mdesc').textContent = d.desc;
   document.getElementById('mratemsg').textContent = "";
   document.getElementById('mrate').style.display = UAT ? 'block':'none';
   const fb = document.getElementById('mfb');
   fb.href = fbLink(d.title);
   fb.textContent = FORM_URL ? "📝 Give feedback (1 min)" : "💬 Tell us what you think";
   fb.style.display = UAT ? 'block':'none';
   document.getElementById('modal').style.display='flex';
 }}
 function pickFmt(i,j){{
   const f = DATA[i].formats[j];
   document.getElementById('mmain').src = f.img;
   document.querySelectorAll('#mfchips .fchip').forEach((e,k)=>
     e.classList.toggle('sel', k===j));
 }}
 function closeM(){{document.getElementById('modal').style.display='none';}}
 document.querySelectorAll('#mstars span').forEach(function(el){{
   el.addEventListener('click', function(){{ setRating(parseInt(el.dataset.v)); }});
 }});
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
