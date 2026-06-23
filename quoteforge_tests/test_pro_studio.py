"""Pro Designer (beta) — the additive Fabric.js free-canvas studio."""
from PIL import Image


def _page(tmp_path) -> str:
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    return build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                           out_path=tmp_path / "h.html", frame_picker=True).read_text(encoding="utf-8")


def test_pro_studio_builds_with_fabric_engine(tmp_path):
    # The Pro Designer is a self-contained Fabric.js studio with the core POD
    # capabilities: add text + image, manipulate, save, export a print-ready file.
    from quoteforge.etsy.listing_preview import build_pro_studio
    out = build_pro_studio(out_path=tmp_path / "studio.html")
    h = out.read_text(encoding="utf-8")
    assert "fabric.min.js" in h and "new fabric.Canvas" in h
    assert "function addText" in h and "function uploadImage" in h
    assert "function exportPrint" in h and "function saveDesign" in h
    assert "function setProduct" in h
    for p in ("T-Shirt", "Mug", "Tote", "Poster"):
        assert p in h
    # the chosen web fonts must actually be loaded + re-rendered (Fabric font race)
    assert "fonts.googleapis.com/css2" in h and "document.fonts.ready" in h


def test_pro_studio_reuses_pipeline_endpoints(tmp_path):
    # A Pro design must flow to the SAME /upload (print file) + /design (save) the
    # order pipeline already consumes - not a parallel, unwired path.
    from quoteforge.etsy.listing_preview import build_pro_studio
    h = (build_pro_studio(out_path=tmp_path / "studio.html")).read_text(encoding="utf-8")
    assert "/upload" in h and "/design" in h
    assert "UPLOAD_API" in h and "DESIGN_API" in h


def test_pro_studio_no_supplier_or_marketplace_leak(tmp_path):
    # Customer-facing studio: never a supplier/marketplace name; use "print partner".
    from quoteforge.etsy.listing_preview import build_pro_studio
    low = (build_pro_studio(out_path=tmp_path / "studio.html")).read_text(encoding="utf-8").lower()
    assert "gelato" not in low and "printify" not in low and "printful" not in low
    assert "etsy" not in low
    assert "print partner" in low


def test_storefront_links_to_pro_studio(tmp_path):
    # The storefront offers a discoverable entry point to the beta studio.
    h = _page(tmp_path)
    assert "studio.html" in h and "Pro Designer" in h


def test_pro_studio_end_to_end_order_path(tmp_path):
    # The studio is a true end-to-end path: product + size + colour + qty, print-
    # readiness checks, a copyright gate, then Approve & order -> export + /upload +
    # /design (full product context) -> checkout.
    from quoteforge.etsy.listing_preview import build_pro_studio
    h = (build_pro_studio(out_path=tmp_path / "studio.html")).read_text(encoding="utf-8")
    # size / colour / quantity selection
    assert "function renderOptions" in h and "function setColor" in h
    assert "Size, colour" in h
    # copyright gate (real IP-risk control)
    assert "I own or have the rights" in h
    # print-readiness messages (the spec's plain-language checks)
    assert "outside the safe print area" in h
    assert "transparent background" in h
    assert "too small to print" in h
    assert "low-resolution" in h
    # order carries full product context + hands off to checkout
    assert "function approveOrder" in h and "CHECKOUT_URL" in h
    assert "size:CSIZE" in h and "color:CCOLOR" in h and "qty:CQTY" in h


def test_pro_studio_curved_and_circle_text(tmp_path):
    # Parity with the classic Layout Studio: a real (editable) text object can be
    # curved into an arc or a full circle (badge) via Fabric text-on-path.
    from quoteforge.etsy.listing_preview import build_pro_studio
    h = (build_pro_studio(out_path=tmp_path / "studio.html")).read_text(encoding="utf-8")
    assert "function curveText" in h
    assert "Arc (curved)" in h and "Full circle" in h
    assert "fabric.Path" in h and "pathSide" in h
