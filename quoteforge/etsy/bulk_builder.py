"""Bulk listing builder — scale the catalog with one command.

Going from 20 -> 50 -> 100 -> 300 listings by hand (SEO + images + a design for
each) is the real bottleneck to scaling. This turns the scaling plan into
ready-to-upload PACKAGES:

  for each listing in the next batch:
    - a validated SEO bundle (title + 13 tags + attributes + description)
    - (optional) a generated artwork file + the 5-image Etsy gallery pack
  plus a master Excel of the whole batch for fast copy-paste.

SEO-only is instant and free. With --art it generates a design per listing
(mock quote in TEST_MODE, real Claude quote when a key is set).
"""
from pathlib import Path

from quoteforge.etsy.launch_pack import LaunchListing, next_additions, LAUNCH_PACK_20
from quoteforge.etsy.listing_seo import optimize_listing, format_seo_text


def _to_listing(d: dict, n: int) -> LaunchListing:
    """Convert a next_additions dict into a numbered LaunchListing."""
    return LaunchListing(n, d.get("relationship", "Daughter"),
                         d["title"], d.get("occasion", "Just Because"),
                         d.get("relationship", "Daughter"))


def _slug(text: str) -> str:
    """Turn a title into a short filesystem-safe folder slug."""
    return "".join(c if c.isalnum() else "_" for c in text)[:50].strip("_")


def build_batch(batch: int = 30, start_count: int | None = None,
                with_art: bool = False, output_dir=None) -> dict:
    """Generate ready-to-upload packages for the next `batch` listings."""
    from quoteforge.config import OUTPUT_DIR
    start = start_count if start_count is not None else len(LAUNCH_PACK_20)
    out_dir = Path(output_dir) if output_dir else (OUTPUT_DIR / "bulk_listings")
    out_dir.mkdir(parents=True, exist_ok=True)

    additions = next_additions(start, batch)
    results = []
    bundles = []
    for i, d in enumerate(additions, 1):
        listing = _to_listing(d, start + i)
        bundle = optimize_listing(listing)
        bundles.append(bundle)
        folder = out_dir / f"{start + i:03d}_{_slug(d['title'])}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "seo.txt").write_text(format_seo_text(bundle), encoding="utf-8")
        rec = {"n": start + i, "title": bundle.title[:60],
               "tags": len(bundle.tags), "folder": str(folder),
               "warnings": bundle.warnings, "art": False}
        if with_art:
            try:
                _generate_art(listing, folder)
                rec["art"] = True
            except Exception as exc:  # noqa: BLE001
                rec["art_error"] = f"{type(exc).__name__}: {exc}"
        results.append(rec)

    master = _export_master(bundles, out_dir)
    clean = sum(1 for r in results if not r["warnings"])
    return {"start_count": start, "batch": len(additions),
            "output_dir": str(out_dir), "master_excel": str(master),
            "seo_clean": clean, "with_art": with_art, "listings": results}


# Tasteful sample first-names so launch gallery photos look real (not "[Name]").
_SAMPLE_NAME = {
    "daughter": "Emma", "son": "Liam", "mother": "Mom", "mom": "Mom",
    "father": "Dad", "dad": "Dad", "grandmother": "Grandma",
    "grandfather": "Grandpa", "wife": "Sarah", "husband": "James",
    "best friend": "Grace", "family": "Our Family", "pet": "Buddy",
}


def build_launch_kit(with_art: bool = True, output_dir=None) -> dict:
    """Produce ready-to-upload packages for the ACTUAL 20 launch listings:
    SEO bundle + a real sample design + 5 gallery images + section + checklist."""
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.etsy.shop_layout import assign_listings
    out_dir = Path(output_dir) if output_dir else (OUTPUT_DIR / "launch_kit")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Which section each title belongs to.
    section_of = {}
    for sec, titles in assign_listings().items():
        for t in titles:
            section_of[t] = sec

    results, bundles = [], []
    for l in LAUNCH_PACK_20:
        bundle = optimize_listing(l)
        bundles.append(bundle)
        folder = out_dir / f"{l.n:02d}_{_slug(l.title)}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "seo.txt").write_text(
            f"SECTION: {section_of.get(l.title, 'Best Sellers')}\n\n"
            + format_seo_text(bundle), encoding="utf-8")
        rec = {"n": l.n, "title": l.title,
               "section": section_of.get(l.title, "Best Sellers"),
               "art": False, "warnings": bundle.warnings}
        if with_art:
            try:
                _generate_art(l, folder, _SAMPLE_NAME.get(l.relationship.lower(), "Emma"))
                rec["art"] = True
            except Exception as exc:  # noqa: BLE001
                rec["art_error"] = f"{type(exc).__name__}: {exc}"
        results.append(rec)

    master = _export_master(bundles, out_dir)
    _write_checklist(results, out_dir)
    clean = sum(1 for r in results if not r["warnings"])
    arted = sum(1 for r in results if r["art"])
    return {"count": len(results), "output_dir": str(out_dir),
            "master_excel": str(master), "seo_clean": clean,
            "art_generated": arted, "with_art": with_art, "listings": results}


def _write_checklist(results: list[dict], out_dir: Path) -> None:
    """Write a section-grouped UPLOAD_CHECKLIST.txt covering every built listing."""
    lines = ["JOFFIELS LAUNCH UPLOAD CHECKLIST", "=" * 40,
             "For EACH listing below, in Etsy: create listing -> paste title/tags/",
             "description from seo.txt -> upload the 5 gallery images -> set the",
             "section -> price ladder -> personalization ON -> publish.\n"]
    by_section: dict[str, list[dict]] = {}
    for r in results:
        by_section.setdefault(r["section"], []).append(r)
    for sec, items in by_section.items():
        lines.append(f"\n## SECTION: {sec}")
        for r in items:
            lines.append(f"  [ ] #{r['n']:02d} {r['title']}"
                         + ("  (+images)" if r["art"] else ""))
    (out_dir / "UPLOAD_CHECKLIST.txt").write_text("\n".join(lines), encoding="utf-8")


def _generate_art(listing: LaunchListing, folder: Path,
                  sample_name: str = "Emma") -> None:
    """Generate a poster design + the 5-image listing pack for one listing."""
    from quoteforge.quotes.generator import generate_personal_message
    from quoteforge.images.local_renderer import render_local_poster
    from quoteforge.images.listing_pack import build_listing_pack
    from quoteforge.config import ANTHROPIC_API_KEY
    quote = generate_personal_message(
        relationship=listing.relationship, recipient_name=sample_name,
        sender_name="", occasion=listing.occasion, memory_or_story="",
        scenery="Mountains", output_style="Custom Quote", count=1,
        force_real=bool(ANTHROPIC_API_KEY))[0]
    # Burn in recipient-neutral wording ([Name]/[Your name]) so the mockup fits
    # ANY recipient and matches the storefront's live preview - never a fixed name.
    from quoteforge.etsy.listing_preview import _generalize_quote
    quote = _generalize_quote(quote)
    poster = folder / "poster_18x24.png"
    (folder / "quote.txt").write_text(quote, encoding="utf-8")  # for live color preview
    render_local_poster(quote=quote, output_path=poster, size=(5400, 7200))
    build_listing_pack(poster, folder / "gallery")


def _export_master(bundles, out_dir: Path) -> Path:
    """Write all SEO bundles to a single master Excel sheet for fast copy-paste."""
    from openpyxl import Workbook
    path = out_dir / "batch_seo_master.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "Batch SEO"
    ws.append(["#", "Niche", "Title", "Title len", "Tags (comma-sep)",
               "Materials", "Attributes", "Description"])
    for i, b in enumerate(bundles, 1):
        ws.append([i, b.niche, b.title, len(b.title), ", ".join(b.tags),
                   ", ".join(b.materials),
                   "; ".join(f"{k}: {v}" for k, v in b.attributes.items()),
                   b.description])
    wb.save(path)
    return path


def format_batch_text(report: dict) -> str:
    """Render a build_batch report as printable console text."""
    lines = ["=" * 64, "BULK LISTING BUILDER", "=" * 64,
             f"Built {report['batch']} listing package(s) "
             f"(starting after #{report['start_count']}).",
             f"SEO clean: {report['seo_clean']}/{report['batch']}",
             f"Artwork  : {'generated' if report['with_art'] else 'skipped (--art to add)'}",
             f"\nFolder      : {report['output_dir']}",
             f"Master sheet: {report['master_excel']}", "",
             "First few:"]
    for r in report["listings"][:8]:
        flag = "[OK]" if not r["warnings"] else "[!!]"
        art = " +art" if r["art"] else ""
        lines.append(f"  {flag} #{r['n']:>3} {r['title']}{art}")
    if report["batch"] > 8:
        lines.append(f"  ... and {report['batch'] - 8} more")
    lines.append("\nUpload each folder's SEO + images to a new Etsy listing,")
    lines.append("or copy the master sheet row-by-row.")
    lines.append("=" * 64)
    return "\n".join(lines)
