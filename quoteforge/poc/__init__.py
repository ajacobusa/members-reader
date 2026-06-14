"""POC (proof-of-concept) end-to-end validation harness.

Drives the REAL QuoteForge production code against an isolated, seeded test
database with vendor / carrier / email mocks, so the full workflow can be
validated like production before launch - WITHOUT touching real data. Produces
an owner-facing dashboard + a go/no-go decision.

This package is for TESTING ONLY. It never becomes the primary site and never
uses real customer data or real orders.
"""
from quoteforge.poc.harness import run_validation
from quoteforge.poc.report import build_dashboard, build_poc_site

__all__ = ["run_validation", "build_dashboard", "build_poc_site"]
