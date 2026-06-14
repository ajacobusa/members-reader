#!/usr/bin/env python
"""POC end-to-end validation runner (TEST ONLY).

Runs the full proof-of-concept validation against the REAL QuoteForge code on an
isolated, seeded test database, then writes:
  - POC/poc_dashboard.html   the results + go/no-go verdict
  - POC/poc_site/index.html  the deployed storefront stamped as a TEST-ONLY POC

This environment never uses real customer data and must never be promoted to the
primary site.

    python POC/run_poc.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quoteforge.poc.runner import run_poc, format_summary  # noqa: E402


def main() -> int:
    """Run the POC and print the summary; exit non-zero on a NO-GO verdict."""
    out = run_poc()
    print(format_summary(out["results"]))
    print(f"\nDashboard : {out['dashboard']}")
    if out["site"]:
        print(f"POC site  : {out['site']}")
    return 0 if out["results"]["go"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
