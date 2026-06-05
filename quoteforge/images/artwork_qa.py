"""Artwork-quality QA harness.

The reviewer's #2 watch-item: "The system can generate technically valid artwork
that still looks amateur." This renders the SAME message across the edge cases
that break POD templates - very short vs. very long names, short vs. long
quotes, and every product size - then runs each through the print preflight so
you can both EYEBALL the output and confirm it passes spec.

Run:  python -m quoteforge.admin artwork-qa
Then open the output folder and look critically at long-name / long-quote cases.
"""
from pathlib import Path

# Edge cases that typically break layout.
NAME_CASES = [
    ("short_name", "Emma"),
    ("long_name", "Alexandria Katherine Thompson"),
]
QUOTE_CASES = [
    ("short_quote", "Never stop believing in yourself."),
    ("long_quote",
     "Emma, never forget how hard you worked through every late night and early "
     "morning, every doubt you pushed past, and every dream you refused to give "
     "up on. We are endlessly proud of the woman you have become. - Love, Mom"),
]
# (label, size string, renderer pixel size at 300 DPI)
SIZE_CASES = [
    ("8x10", "8x10 in", (2400, 3000)),
    ("11x14", "11x14 in", (3300, 4200)),
    ("16x20", "16x20 in", (4800, 6000)),
    ("18x24", "18x24 in", (5400, 7200)),
]


def run_artwork_qa(output_dir: Path | None = None,
                   sizes: bool = True) -> dict:
    """Render the edge-case matrix and preflight each. Returns a report."""
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.images.local_renderer import render_local_poster
    from quoteforge.images.preflight import run_preflight

    out_dir = Path(output_dir) if output_dir else (OUTPUT_DIR / "artwork_qa")
    out_dir.mkdir(parents=True, exist_ok=True)

    size_matrix = SIZE_CASES if sizes else [SIZE_CASES[1]]  # 11x14 only if not
    cases = []
    for nlabel, name in NAME_CASES:
        for qlabel, quote in QUOTE_CASES:
            for slabel, size_str, px in size_matrix:
                text = quote.replace("Emma,", f"{name},") if qlabel == "long_quote" \
                    else f"{name} - {quote}"
                fname = f"{nlabel}_{qlabel}_{slabel}.png"
                path = out_dir / fname
                render_local_poster(quote=text, output_path=path, size=px)
                pf = run_preflight(path, size_str)
                cases.append({
                    "case": f"{nlabel} / {qlabel} / {slabel}",
                    "file": str(path),
                    "preflight_ok": pf["ok"],
                    "fails": [c["name"] for c in pf["checks"] if not c["ok"]],
                })
    passed = sum(1 for c in cases if c["preflight_ok"])
    return {"output_dir": str(out_dir), "total": len(cases),
            "passed": passed, "failed": len(cases) - passed, "cases": cases}


def format_qa_text(report: dict) -> str:
    lines = ["=" * 64, "ARTWORK QA - edge-case render + preflight", "=" * 64,
             f"Output folder: {report['output_dir']}",
             f"Preflight: {report['passed']}/{report['total']} passed", ""]
    for c in report["cases"]:
        flag = "[OK]" if c["preflight_ok"] else "[XX]"
        detail = "" if c["preflight_ok"] else f" - {', '.join(c['fails'])}"
        lines.append(f"  {flag} {c['case']}{detail}")
    lines.append("")
    lines.append("Now OPEN the folder and look at the long_name / long_quote")
    lines.append("renders - preflight passing is necessary but not sufficient;")
    lines.append("only your eye catches 'technically valid but amateur'.")
    lines.append("=" * 64)
    return "\n".join(lines)
