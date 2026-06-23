"""Sheet-driven product-photo download agent (network + clock injected)."""
from pathlib import Path

from quoteforge.automation.product_photo_agent import (
    process_photo_sheet, default_dest, read_sheet, write_sheet,
    build_template_rows, REQUIRED_COLUMNS)


def _row(pid, status, url=""):
    return {"product_id": pid, "product_name": pid, "gelato_product_url": "",
            "mockup_image_url": url, "image_status": status,
            "local_file_name": "", "last_downloaded_date": "", "notes": ""}


def test_downloads_renames_and_archives_by_month(tmp_path):
    rows = [_row("classic_mug", "Ready to Download", "http://x/img.png")]
    dest = lambda pid, n: default_dest(tmp_path, pid, n)
    s = process_photo_sheet(rows, lambda u: b"IMGBYTES", dest, "2026-06-23")
    assert s["downloaded"] == 1
    # live tile + dated archive both written, both named tile-<id>.jpg
    assert (tmp_path / "tile-classic_mug.jpg").read_bytes() == b"IMGBYTES"
    assert (tmp_path / "product_photos" / "2026" / "06"
            / "tile-classic_mug.jpg").exists()
    assert rows[0]["image_status"] == "Downloaded"
    assert rows[0]["local_file_name"] == "tile-classic_mug.jpg"
    assert rows[0]["last_downloaded_date"] == "2026-06-23"


def test_missing_url_is_flagged_not_downloaded(tmp_path):
    rows = [_row("m_tshirt", "Ready to Download", "")]
    s = process_photo_sheet(rows, lambda u: b"x",
                            lambda pid, n: default_dest(tmp_path, pid, n), "2026-06-23")
    assert s["missing"] == 1 and rows[0]["image_status"] == "Missing Image URL"


def test_failed_download_retries_then_records_error(tmp_path):
    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        raise RuntimeError("boom")

    rows = [_row("tote", "Ready to Download", "http://x")]
    s = process_photo_sheet(rows, flaky,
                            lambda pid, n: default_dest(tmp_path, pid, n),
                            "2026-06-23", retries=2)
    assert calls["n"] == 3              # initial + 2 retries
    assert s["failed"] == 1
    assert rows[0]["image_status"] == "Failed"
    assert "boom" in rows[0]["notes"]


def test_existing_tile_not_overwritten_unless_enabled(tmp_path):
    (tmp_path / "tile-wall_cal.jpg").write_bytes(b"APPROVED")
    rows = [_row("wall_cal", "Ready to Download", "http://x")]
    dest = lambda pid, n: default_dest(tmp_path, pid, n)
    s = process_photo_sheet(rows, lambda u: b"NEW", dest, "2026-06-23")
    assert s["exists"] == 1 and rows[0]["image_status"] == "Already Exists"
    assert (tmp_path / "tile-wall_cal.jpg").read_bytes() == b"APPROVED"  # untouched
    # with overwrite the approved file IS replaced
    rows2 = [_row("wall_cal", "Ready to Download", "http://x")]
    process_photo_sheet(rows2, lambda u: b"NEW", dest, "2026-06-23", overwrite=True)
    assert (tmp_path / "tile-wall_cal.jpg").read_bytes() == b"NEW"


def test_only_ready_rows_are_touched(tmp_path):
    rows = [_row("a", "Needs URL", "http://x"), _row("b", "Downloaded", "http://x")]
    s = process_photo_sheet(rows, lambda u: b"x",
                            lambda pid, n: default_dest(tmp_path, pid, n), "2026-06-23")
    assert s["downloaded"] == 0 and s["skipped"] == 2


def test_sheet_round_trips_with_required_columns(tmp_path):
    p = tmp_path / "products.csv"
    write_sheet(p, [_row("x", "Needs URL")])
    back = read_sheet(p)
    assert list(back[0].keys()) == REQUIRED_COLUMNS
    assert back[0]["product_id"] == "x"


def test_template_lists_every_product_with_blank_urls():
    rows = build_template_rows({"mug:classic_mug": "mug_uid_123"})
    ids = {r["product_id"] for r in rows}
    assert {"classic_mug", "wall_cal", "tote", "m_tshirt"} <= ids
    assert all(r["mockup_image_url"] == "" for r in rows)
    assert all(r["image_status"] == "Needs URL" for r in rows)
    mug = next(r for r in rows if r["product_id"] == "classic_mug")
    assert mug["gelato_product_url"] == "mug_uid_123"   # pre-filled from the map
