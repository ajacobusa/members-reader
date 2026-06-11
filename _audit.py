import tempfile, importlib
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

issues = []

# 1. Every module imports cleanly (no circular imports / broken wiring)
mods = ["quoteforge.main","quoteforge.admin","quoteforge.etsy.financials",
        "quoteforge.etsy.reports","quoteforge.etsy.tco","quoteforge.etsy.sales_engine",
        "quoteforge.etsy.product_lines","quoteforge.etsy.occasions","quoteforge.etsy.campaign",
        "quoteforge.etsy.marketing_calendar","quoteforge.etsy.launch_pack",
        "quoteforge.automation.healthcheck","quoteforge.automation.customer_proof",
        "quoteforge.automation.emailer","quoteforge.automation.pipeline_orchestrator"]
for m in mods:
    try: importlib.import_module(m)
    except Exception as e: issues.append(f"IMPORT {m}: {e}")
print(f"[1] Imports: {len(mods)-len([i for i in issues if i.startswith('IMPORT')])}/{len(mods)} clean")

# 2. End-to-end: order -> pipeline -> DB -> financials -> reports -> tco all agree
import quoteforge.db.database as db
from quoteforge.automation import pipeline_orchestrator as po
tmp = Path(tempfile.mkdtemp())
with patch.object(db,'DB_PATH',tmp/'t.db'), patch.object(db,'OUTPUT_DIR',tmp), \
     patch.object(po,'OUTPUT_DIR',tmp), patch.object(po,'RENDERER','local'), \
     patch.object(po,'CUSTOMER_PROOF_APPROVAL',False), patch.object(po,'PIPELINE_AUTO_APPROVE_PROOF',True), \
     patch('quoteforge.automation.pipeline_orchestrator.fetch_background_url',return_value=None):
    db.init_db()
    po.run_full_pipeline({'order_id':'AUD','recipient_name':'Emma','occasion':'Graduation',
        'sender_name':'Mom','relationship':'Daughter','sale_price':34.99,'gelato_cost':11.0},
        skip_proof=True)
    o = db.get_order('AUD')
    from quoteforge.etsy.financials import summarize, order_financials
    from quoteforge.etsy.reports import period_report
    from quoteforge.etsy.tco import live_tco
    fin = summarize([o])
    rep = period_report('monthly')
    # Consistency checks
    of = order_financials(o)
    if of['sale_price'] != 34.99: issues.append("financials sale_price != real price")
    if fin['revenue'] != 34.99: issues.append(f"summarize revenue {fin['revenue']} != 34.99")
    if rep['financials']['revenue'] != 34.99: issues.append(f"report revenue {rep['financials']['revenue']} != 34.99")
    # gelato_cost: was it actually stored?
    if o['gelato_cost'] != 11.0: issues.append(f"gelato_cost not stored: {o['gelato_cost']}")
    # tco live uses real order
    tco = live_tco(listings=20)
    if 'live' not in tco['source']: issues.append("tco not using live order")
    print(f"[2] E2E numbers agree: revenue=${fin['revenue']} across financials/report; gelato_cost stored={o['gelato_cost']}")

print(f"\n=== AUDIT RESULT: {'CLEAN' if not issues else str(len(issues))+' ISSUES'} ===")
for i in issues: print("  -", i)
