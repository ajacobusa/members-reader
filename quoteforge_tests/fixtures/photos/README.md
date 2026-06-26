# Test photo library

The print-quality gate (`quoteforge/images/photo_quality.py`) is tested in layers by
`quoteforge_tests/test_photo_pipeline.py`:

1. **Unit** — each rule (blur / noise / compression / exposure / effective-DPI / score)
2. **Generated fixtures** — one synthetic image per failure mode (good, low-res,
   blurry, over-compressed, tiny, dark, noisy), built deterministically in the test
   so no binaries are committed and there's no copyright concern
3. **Product-size** — the SAME photo across Gelato sizes (8x10 PASS → 24x36 FAIL),
   proving the gate uses *effective* DPI, not metadata
4. **Full /upload flow** — a bad photo is blocked before it could reach the vendor
5. **Report shape** — the per-upload quality report contract

## Add your own REAL photos here

Drop real JPG/PNG files into this folder and they are scored automatically by
`test_real_fixture_photos_score_cleanly` (the report must be well-formed). Suggested
set, matching the QA plan:

```
good_300dpi.jpg            -> PASS
120dpi_soft.jpg            -> ENHANCE / WARN
150dpi_blurry.jpg          -> FAIL (blur)
facebook_download.jpg      -> WARN / FAIL (compression)
instagram_screenshot.jpg   -> FAIL (small + compressed)
tiny_photo.jpg             -> FAIL (resolution)
dark_photo.jpg             -> WARN (exposure)
overcompressed.jpg         -> FAIL (compression)
portrait_face_too_small.jpg-> WARN (face < 15% of frame)
```

Inspect a single file from the portable runner:

```
python\python.exe -c "from quoteforge.images.photo_quality import quality_report; \
import json; print(json.dumps(quality_report(r'quoteforge_tests/fixtures/photos/your.jpg', '16x20', run_ai=False), indent=2))"
```

## Final real-world check (before go-live)
Order Gelato samples with: 1 excellent, 1 borderline, 1 AI-enhanced, 1 intentionally
bad photo. The bad one must be blocked here; the borderline one warns or enhances.
