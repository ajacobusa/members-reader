"""QuoteForge admin CLI — operational commands for go-live and daily ops.

Usage:
  python -m quoteforge.admin gen-secret       # generate a webhook signing secret
  python -m quoteforge.admin backup           # snapshot the database (+ prune)
  python -m quoteforge.admin restore [PATH]   # restore newest (or given) backup
  python -m quoteforge.admin list-backups     # show available backups
  python -m quoteforge.admin daily-report     # daily order-review summary
  python -m quoteforge.admin preflight        # run the go-live preflight checks
  python -m quoteforge.admin verify-keys      # LIVE test: Anthropic + Gelato auth
  python -m quoteforge.admin sample-quote     # preview a REAL AI quote (safe)
  python -m quoteforge.admin email-report     # email the daily sales report
  python -m quoteforge.admin report PERIOD    # daily|weekly|monthly|yearly (add 'email' to send)
  python -m quoteforge.admin healthcheck [email]  # verify jobs/DB/storage; email if problems
  python -m quoteforge.admin install-schedule [--dry-run|--remove]  # create all scheduled jobs
  python -m quoteforge.admin maintenance [email|--check]  # daily self-healing infra agent
  python -m quoteforge.admin mockup POSTER.png [out] [wall] [frame]  # styled-room lifestyle mockup
  python -m quoteforge.admin bundles [occasion]   # high-ticket gallery-set bundles ($180-500)
  python -m quoteforge.admin margins [floor%]      # audit catalog against the margin floor
  python -m quoteforge.admin plan              # which occasions to create listings for now
  python -m quoteforge.admin campaign [Month]  # batch listing plan + publish-by dates (Excel)
  python -m quoteforge.admin sales             # today's upsell/review/win-back actions to send
  python -m quoteforge.admin calendar          # annual retailer timeline: list/market dates due
  python -m quoteforge.admin products [Occasion]  # full product range + 1-story-to-many bundle
  python -m quoteforge.admin tco [listings] [orders/mo]  # total cost of ownership breakdown
  python -m quoteforge.admin launch [scale N]  # the 20 starter listings; or next batch to add
  python -m quoteforge.admin reconcile [YYYY-MM]  # monthly bookkeeping Excel
  python -m quoteforge.admin show-proof ID    # show the proof message to send the buyer
  python -m quoteforge.admin customer-approved ID  # buyer approved -> release to print (logs audit trail)
  python -m quoteforge.admin resolve <issue> [ID]  # decide a return/refund issue + draft the reply
  python -m quoteforge.admin costs [today|week|month] [email]  # detailed API spend report
  python -m quoteforge.admin sample-batch [N]      # review quote quality across categories
  python -m quoteforge.admin artwork-qa            # render name/quote/size edge cases + preflight
  python -m quoteforge.admin preflight-art ART.png [size]  # artwork print-quality check
  python -m quoteforge.admin listing-pack POSTER.png [out]  # 5 Etsy gallery images from a design
  python -m quoteforge.admin seo [N|export]        # per-listing Etsy SEO (title+13 tags+desc)
  python -m quoteforge.admin poll-etsy             # pull new paid Etsy orders (no Make/Zapier)
  python -m quoteforge.admin autopilot "<issue>" [ID]  # bot decides: auto-act or escalate to you
  python -m quoteforge.admin approvals [approve|reject ID]  # your decision queue (only when needed)
"""
import sys

from quoteforge.secrets_util import generate_webhook_secret


def _cmd_gen_secret() -> int:
    """CLI handler for `python -m quoteforge.admin gen-secret`."""
    secret = generate_webhook_secret()
    print("Generated webhook signing secret:\n")
    print(f"  {secret}\n")
    print("Add this to BOTH places (same value):")
    print("  1. .env  →  ETSY_WEBHOOK_SECRET=" + secret)
    print("  2. Make.com/Zapier HTTP module → sign body with HMAC-SHA256 →")
    print("     send as header  X-Webhook-Signature")
    return 0


def _cmd_backup_all(args: list[str]) -> int:
    """Full backup: DB snapshot + auto-commit + push to GitHub + bundle."""
    from quoteforge.automation.full_backup import run_full_backup, format_backup_text
    r = run_full_backup(push="--no-push" not in args)
    print(format_backup_text(r))
    return 0 if "fail" not in str(r.get("push", "")) else 1


def _cmd_backup() -> int:
    """CLI handler for `python -m quoteforge.admin backup`."""
    from quoteforge.db.database import backup_database, prune_old_backups
    path = backup_database()
    if not path:
        print("No database found to back up.")
        return 1
    from quoteforge.config import BACKUP_RETENTION_DAYS
    deleted = prune_old_backups()  # age-based retention
    print(f"Backup created: {path}")
    print(f"Retention: keeping backups from the last {BACKUP_RETENTION_DAYS} "
          f"day(s) (newest always kept).")
    if deleted:
        print(f"Pruned {deleted} backup(s) older than {BACKUP_RETENTION_DAYS} days.")
    return 0


def _cmd_restore(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin restore`."""
    from pathlib import Path
    from quoteforge.db.database import restore_database
    target = Path(args[0]) if args else None
    restored = restore_database(target)
    if not restored:
        print("No backup available to restore.")
        return 1
    print(f"Database restored from: {restored}")
    print("(The previous live DB was snapshotted first — restore is reversible.)")
    return 0


def _cmd_launch_dash(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin launch-dash` - the launch KPI
    dashboard (views/favorites/conversion/revenue/profit/keywords/occasions).
    `launch-dash record "<listing>" <views> <favs>` stores real Etsy stats."""
    from quoteforge.analytics.launch_dashboard import (
        launch_metrics, format_dashboard, record_listing_stats)
    if args and args[0] == "record" and len(args) >= 4:
        record_listing_stats(args[1], int(args[2]), int(args[3]))
        print(f"Recorded: {args[1]} views={args[2]} favorites={args[3]}")
    print(format_dashboard(launch_metrics()))
    return 0


def _cmd_site_doctor(args: list[str]) -> int:
    """Daily self-healing website QA bot.

    Usage: site-doctor [email] [--no-heal] [--no-tests]
      checks the built storefront (fonts lazy-load, JSON-LD, alt coverage,
      asset integrity, occasion filter, design count, editor JS, docs ratchet),
      heals page-level problems by rebuilding, and runs the regression subset.
    """
    from quoteforge.automation.site_doctor import (
        run_site_doctor, format_site_doctor_text, send_site_doctor_alert)
    r = run_site_doctor(heal="--no-heal" not in args,
                        regression="--no-tests" not in args)
    print(format_site_doctor_text(r))
    if "email" in args:
        send_site_doctor_alert(r)
    return 0 if r["overall"] == "OK" else 1


def _cmd_restore_all(args: list[str]) -> int:
    """One-command recovery: DB (newest snapshot) + code (from the local bundle).

    Usage: restore-all [--into DIR]
      (no --into) restores the DB and prints the clone command for the code.
      --into DIR also clones the code bundle into a fresh DIR.
    """
    from quoteforge.automation.full_backup import restore_all, format_restore_text
    into = ""
    if "--into" in args:
        i = args.index("--into")
        into = args[i + 1] if i + 1 < len(args) else ""
    r = restore_all(into=into)
    print(format_restore_text(r))
    return 0 if "error" not in str(r.get("db_restore", "")) else 1


def _cmd_list_backups() -> int:
    """CLI handler for `python -m quoteforge.admin list-backups`."""
    from quoteforge.db.database import list_backups
    backups = list_backups()
    if not backups:
        print("No backups found.")
        return 0
    print(f"{len(backups)} backup(s), newest first:")
    for b in backups:
        size_kb = b.stat().st_size // 1024
        print(f"  {b.name}  ({size_kb} KB)")
    return 0


def _cmd_daily_report() -> int:
    """CLI handler for `python -m quoteforge.admin daily-report`."""
    from quoteforge.db.database import init_db, daily_order_report
    init_db()
    r = daily_order_report()
    print("=" * 52)
    print("QUOTEFORGE DAILY ORDER REPORT")
    print("=" * 52)
    print("\nOrders by status:")
    if r["by_status"]:
        for status, n in sorted(r["by_status"].items()):
            print(f"  {status:20s} {n}")
    else:
        print("  (no orders yet)")
    print(f"\nUnsent customer messages: {r['unsent_messages']}")
    print(f"Pending review requests:  {r['pending_reviews']}")
    print(f"\nOrders needing attention: {len(r['needs_attention'])}")
    for o in r["needs_attention"]:
        print(f"  [{o['status']:11s}] {o['order_id']}  {o['recipient_name']} — {o['occasion']}")
    print("=" * 52)
    return 0


def _cmd_preflight() -> int:
    """CLI handler for `python -m quoteforge.admin preflight`."""
    from quoteforge.preflight import main as preflight_main
    preflight_main()
    return 0


def _cmd_verify_keys() -> int:
    """Live connectivity test for the two minimum-launch keys."""
    from quoteforge import config
    print("Live key verification (Anthropic + Gelato)\n")

    # Anthropic — make a real tiny generation (force_real bypasses TEST_MODE)
    if not config.ANTHROPIC_API_KEY:
        print("  [ -- ] Anthropic: ANTHROPIC_API_KEY not set")
        anthropic_ok = False
    else:
        try:
            from quoteforge.quotes.generator import generate_personal_message
            out = generate_personal_message(
                relationship="To My Daughter", recipient_name="Emma",
                sender_name="Mom", occasion="Graduation", memory_or_story="",
                scenery="Mountains", output_style="Custom Quote",
                count=1, force_real=True,
            )
            anthropic_ok = bool(out and out[0])
            print(f"  [{'PASS' if anthropic_ok else 'FAIL'}] Anthropic: live generation "
                  + ("succeeded" if anthropic_ok else "returned nothing"))
        except Exception as exc:  # noqa: BLE001
            anthropic_ok = False
            print(f"  [FAIL] Anthropic: {type(exc).__name__}: {exc}")

    # Gelato — catalog auth check (no order created)
    from quoteforge.automation.gelato_api import verify_gelato_auth
    g = verify_gelato_auth()
    print(f"  [{'PASS' if g['ok'] else ' -- ' if 'not set' in g['detail'] else 'FAIL'}] "
          f"Gelato: {g['detail']}")

    # Printify / Printful — auth checks (no orders created; '--' = key not set,
    # which is fine: these vendors are optional until you route products to them)
    from quoteforge.fulfillment.printify import verify_printify_auth
    from quoteforge.fulfillment.printful import verify_printful_auth
    for label, res in (("Printify", verify_printify_auth()),
                       ("Printful", verify_printful_auth())):
        print(f"  [{'PASS' if res['ok'] else ' -- ' if 'not set' in res['detail'] else 'FAIL'}] "
              f"{label}: {res['detail']}")

    # Gelato product UID mappings — must be real, not seed placeholders
    from quoteforge.etsy.gelato_catalog import verify_catalog_mappings
    m = verify_catalog_mappings()
    if m["all_real"]:
        print(f"  [PASS] Gelato UIDs: all {m['total']} product mappings configured")
    else:
        print(f"  [WARN] Gelato UIDs: {m['placeholder_count']}/{m['total']} still on "
              f"placeholder SKUs - replace with real UIDs from your Gelato account:")
        for ph in m["placeholders"][:8]:
            print(f"           - {ph['product_id']} ({ph['size']}): {ph['current_sku']}")
        if m["placeholder_count"] > 8:
            print(f"           ... and {m['placeholder_count'] - 8} more")

    print()
    if anthropic_ok and g["ok"] and m["all_real"]:
        print("Keys + UID mappings verified live. You can run the real sample flow")
        print("(keep TEST_MODE=true — Gelato fulfillment stays manual).")
        return 0
    print("Not ready: fix the keys in .env and/or replace placeholder Gelato")
    print("product UIDs with real ones from your account, then re-run.")
    return 1


def _cmd_show_proof(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin show-proof`."""
    if not args:
        print("Usage: python -m quoteforge.admin show-proof <ORDER_ID>")
        return 2
    from quoteforge.db.database import init_db, get_order
    from quoteforge.automation.customer_proof import prepare_customer_proof
    init_db()
    oid = args[0]
    if not get_order(oid):
        print(f"Order {oid} not found.")
        return 1
    pkg = prepare_customer_proof(oid)
    print("=" * 56)
    print(f"PROOF TO SEND TO BUYER — order {oid}")
    print("=" * 56)
    print(f"\nAttach this image in the Etsy conversation:\n  {pkg['artwork_path']}\n")
    print("Message to send:\n")
    print(pkg["proof_message"])
    print("\n" + "-" * 56)
    print(f"When the buyer replies APPROVED, run:")
    print(f"  python -m quoteforge.admin customer-approved {oid}")
    return 0


def _cmd_customer_approved(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin customer-approved`."""
    if not args:
        print("Usage: python -m quoteforge.admin customer-approved <ORDER_ID>")
        return 2
    from quoteforge.db.database import init_db, get_order
    from quoteforge.automation.customer_proof import record_customer_approval
    init_db()
    oid = args[0]
    if not get_order(oid):
        print(f"Order {oid} not found.")
        return 1
    result = record_customer_approval(oid)
    status = result.get("status", "")
    print(f"Customer approval recorded for {oid}.")
    if status == "in_production":
        print("  Order sent to Gelato for printing.")
    else:
        print("  Status: approved_ready_to_print — now upload the artwork to "
              "Gelato to place the print order.")
    return 0


def _cmd_launch(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin launch`."""
    from quoteforge.etsy.launch_pack import (
        LAUNCH_PACK_20, PRICING, AVOID_INITIALLY, SCALING_PHASES,
        next_additions, current_phase,
    )
    # Scale mode: show the next batch to add
    if args and args[0] == "scale":
        count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
        phase = current_phase(count)
        adds = next_additions(count, batch=15)
        print("=" * 58)
        print(f"SCALING — you have ~{count} listings (Phase {phase['phase']})")
        print(f"Focus: {phase['focus']}")
        print("=" * 58)
        print("NEXT LISTINGS TO ADD:")
        for a in adds:
            print(f"  • {a['title']}")
        if not adds:
            print("  You've covered the proven pool — move to seasonal campaigns "
                  "(admin campaign) and cross-sell products (admin products).")
        return 0
    # Default: the 20 starter listings + pricing + what to avoid
    print("=" * 58)
    print("LAUNCH PACK — 20 high-intent personalized gift listings")
    print("=" * 58)
    last_cat = None
    for l in LAUNCH_PACK_20:
        if l.category != last_cat:
            print(f"\n[{l.category}]")
            last_cat = l.category
        print(f"  {l.n:>2}. {l.title}")
    print("\nPRICING LADDER (same design, multiple price points):")
    for product, (lo, hi) in PRICING.items():
        print(f"  {product:18} ${lo}-${hi}")
    print("\nAVOID AT LAUNCH (crowded / low-intent):")
    print("  " + ", ".join(AVOID_INITIALLY))
    print(f"\nThen scale: run  python -m quoteforge.admin launch scale 20")
    return 0


def _cmd_tco(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin tco`."""
    from quoteforge.db.database import init_db
    from quoteforge.etsy.tco import estimate_tco, live_tco, format_tco_text
    init_db()
    listings = int(args[0]) if args and args[0].isdigit() else 100
    if len(args) > 1 and args[1].isdigit():
        # explicit volume → projection
        tco = estimate_tco(listings=listings, orders_per_month=int(args[1]))
    else:
        # use this month's real orders for the variable side
        tco = live_tco(listings=listings)
    print(format_tco_text(tco))
    return 0


def _cmd_products(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin products`."""
    from quoteforge.etsy.product_lines import (
        top_ranked, bundle_value, catalog_by_category,
    )
    if args:
        occasion = " ".join(args)
        bundle = bundle_value(occasion)
        print("=" * 58)
        print(f"ONE STORY → MANY PRODUCTS — {occasion}")
        print("=" * 58)
        print(f"{'PRODUCT':24} {'PRICE':>8} {'PROFIT':>8}  PERSONALIZE")
        print("-" * 58)
        for p in bundle["products"]:
            print(f"{p['product']:24} ${p['sell_price']:>6.2f} ${p['net_profit']:>6.2f}  {p['personalization']}")
        print("-" * 58)
        print(f"If they buy the full bundle: ${bundle['total_revenue']:.2f} revenue, "
              f"${bundle['total_profit']:.2f} profit ({bundle['product_count']} products)")
        print("\nTip: offer 2-3 of these as a matching set to lift average order value.")
        return 0
    # No occasion → show the ranked product range
    print("=" * 58)
    print("GELATO PRODUCT RANGE — ranked by potential")
    print("=" * 58)
    print(f"{'#':>2} {'PRODUCT':24} {'COST':>7} {'SELL':>8} {'PROFIT':>8} {'MARGIN':>7}")
    print("-" * 58)
    for p in top_ranked(20):
        print(f"{p.rank:>2} {p.name:24} ${p.gelato_cost:>5.2f} ${p.sell_price:>6.2f} "
              f"${p.net_profit:>6.2f} {p.margin_pct:>5.1f}%")
    print("\nThe big idea: 1 AI message → poster + mug + journal + card + tote...")
    print("Run  python -m quoteforge.admin products Graduation  for a bundle.")
    return 0


def _cmd_calendar(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin calendar`."""
    from quoteforge.etsy.marketing_calendar import (
        upcoming_actions, ANNUAL_CALENDAR, HIGH_REVENUE_CATEGORIES,
    )
    horizon = int(args[0]) if args and args[0].isdigit() else 60
    actions = upcoming_actions(horizon_days=horizon)
    print("=" * 60)
    print(f"ANNUAL MARKETING CALENDAR — next {horizon} days")
    print("=" * 60)
    print(f"{'DATE':12} {'URGENCY':10} {'ACTION':20} OCCASION (rev #)")
    print("-" * 60)
    for a in actions:
        print(f"{a['date']:12} {a['urgency']:10} {a['action']:20} "
              f"{a['occasion']} (#{a['revenue_rank']})")
    if not actions:
        print("  Nothing due in this window — you're ahead of schedule.")
    print("\nHighest-revenue categories (always keep listed):")
    print("  " + " > ".join(HIGH_REVENUE_CATEGORIES[:5]))
    return 0


def _cmd_sales(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin sales`."""
    from quoteforge.db.database import init_db
    from quoteforge.etsy.sales_engine import sales_actions_digest, format_digest_text
    init_db()
    digest = sales_actions_digest()
    print(format_digest_text(digest))
    if args and args[0] == "email":
        from quoteforge.automation.emailer import _send_email
        body = (f"<html><body style='font-family:Arial'>"
                f"<pre style='font-size:13px'>{format_digest_text(digest)}</pre>"
                f"</body></html>")
        res = _send_email(f"QuoteForge Sales Actions ({digest['total_actions']} to send)", body)
        print(f"\nEmail: {res['status']}")
    return 0


def _cmd_campaign(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin campaign`."""
    from datetime import datetime
    from quoteforge.etsy.campaign import seasonal_campaign, export_campaign_excel
    month = args[0].title() if args else datetime.now().strftime("%B")
    try:
        plans = seasonal_campaign(month)
    except ValueError:
        print(f"Unknown month: {month!r}. Use a full month name, e.g. June.")
        return 2
    print("=" * 60)
    print(f"{month.upper()} CAMPAIGN — publish early to rank first")
    print("=" * 60)
    print(f"{'PUBLISH BY':12} {'URGENCY':22} OCCASION")
    print("-" * 60)
    for p in plans:
        print(f"{p['publish_by']:12} {p['urgency']:22} {p['occasion']}")
    path = export_campaign_excel(month)
    print(f"\n{len(plans)} listings planned. Full plan (titles + tags) saved:")
    print(f"  {path}")
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        rows = "\n".join(f"{p['publish_by']}  {p['urgency']:22}  {p['occasion']}"
                         for p in plans)
        body = (f"<html><body style='font-family:Arial'>"
                f"<h3>{month} Campaign — publish early to rank first</h3>"
                f"<pre style='font-size:13px'>{rows}</pre>"
                f"<p>Full plan with titles + tags: {path}</p></body></html>")
        res = _send_email(f"QuoteForge {month} Campaign — {len(plans)} listings to publish", body)
        print(f"Email: {res['status']}")
    return 0


def _cmd_plan(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin plan`."""
    from quoteforge.etsy.occasions import get_current_month_plan, coverage_summary
    plan = get_current_month_plan()
    cov = coverage_summary()
    print("=" * 56)
    print(f"OCCASION PLAN — {plan['month']}")
    print("=" * 56)
    print(f"\nCREATE THESE NOW ({plan['month']} buyers are shopping):")
    for o in plan["this_month"]:
        print(f"  • {o}")
    print(f"\nPREP AHEAD for {plan['prep_next_month']} (list ~3-4 weeks early):")
    for o in plan["next_month"]:
        print(f"  • {o}")
    print("\nALWAYS-ON evergreen categories (sell year-round):")
    for o in plan["evergreen_always_list"]:
        print(f"  • {o}")
    print(f"\nTotal distinct occasions covered: {cov['total_distinct_occasions']}")
    return 0


def _cmd_healthcheck(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin healthcheck`."""
    from quoteforge.automation.healthcheck import (
        run_healthcheck, format_health_text, send_health_alert,
    )
    if args and args[0] == "email":
        out = send_health_alert(always=True)
        result = out["result"]
        print(format_health_text(result))
        print(f"\nEmail: {out['status']}")
    else:
        result = run_healthcheck()
        print(format_health_text(result))
        # If there are problems, also fire an alert email automatically
        if result["overall"] != "OK":
            send_health_alert()
    # Exit non-zero on FAIL so a scheduler / monitor can detect it
    return 1 if result["overall"] == "FAIL" else 0


def _cmd_autopilot(args: list[str]) -> int:
    """Run an autonomous decision on a customer issue (auto-act or escalate)."""
    from quoteforge.automation.autopilot import handle_issue
    if not args:
        print('Usage: python -m quoteforge.admin autopilot "<issue text>" [ORDER_ID]')
        return 2
    issue = args[0]
    order_id = args[1] if len(args) > 1 else None
    result = handle_issue(issue, order_id)
    d = result["decision"]
    print("=" * 56)
    print(f"AUTOPILOT DECISION - {d['title']}")
    print("=" * 56)
    print(f"  Category   : {d['category']}")
    print(f"  Decision   : {d['decision']}")
    print(f"  Confidence : {d['confidence']:.2f}   Risk: {d['risk']}   "
          f"Money out: ${d['money_out']:.2f}")
    print(f"  Outcome    : {result['outcome'].upper()}")
    print(f"  Reason     : {d['reason']}")
    pol = d.get("policy") or {}
    if pol.get("known"):
        print(f"\n  Etsy/Gelato policy:")
        print(f"    Etsy returnable     : {pol['etsy_returnable']}  "
              f"(Purchase-Protection risk: {pol['etsy_protection_risk']})")
        print(f"    Gelato covers reprint: {pol['gelato_covered']}  "
              f"(report window: {pol['report_window_days']} days)")
        print(f"    Recommended         : {pol['recommended']}")
    if result["outcome"] == "queued_for_human":
        print(f"\n  -> Needs your approval. Approve with: "
              f"python -m quoteforge.admin approvals approve {result['approval_id']}")
    elif d["customer_message"]:
        print(f"\n  Customer reply staged:\n  {d['customer_message'][:160]}...")
    print("=" * 56)
    return 0


def _cmd_approvals(args: list[str]) -> int:
    """List or resolve the human-approval queue (autopilot escalations)."""
    from quoteforge.db.database import init_db, get_pending_approvals, resolve_approval
    init_db()
    if args and args[0] in ("approve", "reject") and len(args) > 1:
        aid = int(args[1])
        if args[0] == "approve":
            from quoteforge.automation.autopilot import execute_approved
            res = execute_approved(aid)
            print(f"Approval {aid}: {res['status']}")
        else:
            resolve_approval(aid, "rejected")
            print(f"Approval {aid}: rejected (no action taken)")
        return 0
    pending = get_pending_approvals()
    if not pending:
        print("No pending approvals - autopilot is handling everything. [OK]")
        return 0
    print(f"{len(pending)} decision(s) awaiting your approval:\n")
    for a in pending:
        print(f"  #{a['id']} [{a['risk']}] {a['summary']}")
        print(f"       confidence {a['confidence']:.2f} | order {a['ref'] or '-'}")
        print(f"       approve: admin approvals approve {a['id']}   "
              f"reject: admin approvals reject {a['id']}")
    return 0


def _cmd_sample_batch(args: list[str]) -> int:
    """Generate representative sample quotes across the emotional categories."""
    from quoteforge import config
    from quoteforge.quotes.sample_batch import (
        generate_sample_batch, format_batch_text,
    )
    real = bool(config.ANTHROPIC_API_KEY) and "--mock" not in args
    per = next((int(a) for a in args if a.isdigit()), 1)
    results = generate_sample_batch(force_real=real, per_scenario=per)
    text = format_batch_text(results, real)
    print(text)
    # Save for side-by-side review.
    out = config.OUTPUT_DIR / "samples" / "quote_samples.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"\nSaved: {out}")
    return 0


def _cmd_artwork_qa(args: list[str]) -> int:
    """Render the edge-case artwork matrix and preflight each for visual review."""
    from quoteforge.images.artwork_qa import run_artwork_qa, format_qa_text
    report = run_artwork_qa(sizes="--quick" not in args)
    print(format_qa_text(report))
    return 0 if report["failed"] == 0 else 1


def _cmd_shop_plan(args: list[str]) -> int:
    """Storefront blueprint: shop sections, listing assignments + polish checklist."""
    from quoteforge.etsy.shop_layout import format_shop_text
    print(format_shop_text())
    return 0


def _cmd_briefing(args: list[str]) -> int:
    """One consolidated daily ops read: what needs action today."""
    from quoteforge.automation.briefing import (
        morning_briefing, format_briefing_text, send_briefing,
    )
    if args and args[0] == "email":
        out = send_briefing()
        print(format_briefing_text(out["briefing"]))
        print(f"\nEmail: {out['status']}")
        return 0
    print(format_briefing_text(morning_briefing()))
    return 0


def _cmd_fix_photo(args: list[str]) -> int:
    """Attach a corrected (higher-res) photo to a held order and resume it."""
    from pathlib import Path
    from quoteforge.db.database import init_db, get_order
    from quoteforge.images.photo_check import check_customer_photo
    if len(args) < 2:
        print("Usage: python -m quoteforge.admin fix-photo ORDER_ID PHOTO.jpg")
        return 2
    init_db()
    order_id, photo = args[0], args[1]
    order = get_order(order_id)
    if not order:
        print(f"Order {order_id} not found.")
        return 1
    if not Path(photo).exists():
        print(f"Photo not found: {photo}")
        return 1
    chk = check_customer_photo(photo, order.get("product_size") or "18x24 in")
    if not chk["ok"]:
        print(f"That photo is still too low quality: {chk['reason']}")
        print("Ask the buyer for the original, full-size image.")
        return 1
    # Resume: re-run the pipeline with the good photo, reusing the approved text.
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline
    data = dict(order)
    data["custom_image"] = photo
    if order.get("generated_quote"):
        data["custom_text"] = order["generated_quote"]   # keep the wording verbatim
    result = run_full_pipeline(data)
    print(f"Order {order_id} resumed with the new photo. "
          f"Status: {result.get('status', '?')}")
    return 0


def _cmd_remind(args: list[str]) -> int:
    """Manage persistent setup reminders (shown in the daily report)."""
    from quoteforge.reminders import (
        add_reminder, done_reminder, format_reminders_text,
    )
    if args and args[0] == "add" and len(args) > 1:
        rid = add_reminder(" ".join(args[1:]))
        print(f"Reminder #{rid} added.")
    elif args and args[0] == "done" and len(args) > 1:
        ok = done_reminder(int(args[1]))
        print(f"Reminder #{args[1]} {'cleared.' if ok else 'not found.'}")
    else:
        print(format_reminders_text())
    return 0


def _cmd_custom_copy(args: list[str]) -> int:
    """Print ready-to-paste listing copy for custom quotes + photo requirements."""
    from quoteforge.etsy.custom_copy import format_custom_copy
    print(format_custom_copy())
    return 0


def _cmd_check_photo(args: list[str]) -> int:
    """Check a customer-supplied photo's print quality for a given size."""
    from quoteforge.images.photo_check import check_customer_photo, photo_request_message
    if not args:
        print("Usage: python -m quoteforge.admin check-photo PHOTO.jpg [size]")
        return 2
    size = args[1] if len(args) > 1 else "18x24 in"
    chk = check_customer_photo(args[0], size)
    print(f"Photo: {chk['actual_px'][0]}x{chk['actual_px'][1]}px  "
          f"effective {chk['effective_dpi']} DPI  (min {chk['min_dpi']})")
    print(f"Result: {'OK - print quality' if chk['ok'] else 'TOO LOW: ' + chk['reason']}")
    if not chk["ok"]:
        print("\nAuto-reply that would be sent to the buyer:\n")
        print(photo_request_message(chk))
    return 0 if chk["ok"] else 1


def _cmd_delight(args: list[str]) -> int:
    """Post-delivery review + referral touches (the delight loop)."""
    from quoteforge.etsy.delight_loop import (
        send_delight_touches, format_delight_text, send_delight_email,
    )
    if args and args[0] == "email":
        out = send_delight_email()
        print(format_delight_text(out["result"]))
        print(f"\nEmail: {out['status']}")
        return 0
    # --dry stages nothing; default stages the messages (idempotent)
    result = send_delight_touches(record="--dry" not in args)
    print(format_delight_text(result))
    return 0


def _cmd_publish_listings(args: list[str]) -> int:
    """Auto-create Etsy DRAFT listings from the launch kit (dry-run by default)."""
    from quoteforge.automation.etsy_publisher import (
        publish_launch_kit, format_publish_text,
    )
    live = "--live" in args
    r = publish_launch_kit(live=live)
    print(format_publish_text(r))
    return 1 if (live and r["missing_prereqs"]) else 0


def _cmd_showroom(args: list[str]) -> int:
    """Combine several listings into ONE shareable HTML file (email it to review)."""
    from quoteforge.etsy.listing_preview import build_showroom
    nums = [int(a) for a in args if a.isdigit()] or None
    out = build_showroom(nums)
    print("Showroom (one file, all listings) generated:")
    print(f"  File: {out}")
    print(f"  URL : {out.resolve().as_uri()}")
    print("Email/share this single .html file - it opens in any browser, offline.")
    return 0


def _cmd_preview_listing(args: list[str]) -> int:
    """Generate a self-contained HTML preview of a listing (open via file:// URL)."""
    from quoteforge.etsy.listing_preview import build_preview
    n = next((int(a) for a in args if a.isdigit()), 1)
    try:
        out = build_preview(n)
    except FileNotFoundError as exc:
        print(f"{exc}")
        return 1
    url = out.resolve().as_uri()
    print(f"Listing #{n} preview generated:")
    print(f"  File: {out}")
    print(f"  URL : {url}")
    print("Open that URL in your browser to review.")
    return 0


def _cmd_listing_video(args: list[str]) -> int:
    """Make a short premium MP4 (slow zoom) from a mockup/image for Etsy."""
    from pathlib import Path
    from quoteforge.images.listing_video import make_listing_video
    if not args:
        print("Usage: python -m quoteforge.admin listing-video IMAGE.png [out.mp4]")
        return 2
    if not Path(args[0]).exists():
        print(f"Image not found: {args[0]}")
        return 1
    out = args[1] if len(args) > 1 else str(Path(args[0]).with_suffix(".mp4"))
    path = make_listing_video(args[0], out)
    kb = path.stat().st_size // 1024
    print(f"Listing video saved: {path} ({kb} KB)")
    print("Upload it to the listing (Etsy ranks video higher).")
    return 0


def _cmd_launch_kit(args: list[str]) -> int:
    """Build the COMPLETE ready-to-upload kit for the 20 launch listings."""
    from quoteforge.etsy.bulk_builder import build_launch_kit
    with_art = "--no-art" not in args
    print("Building launch kit for the 20 listings"
          + (" with designs + gallery images..." if with_art else " (SEO only)..."))
    r = build_launch_kit(with_art=with_art)
    print(f"\nDone: {r['count']} listing package(s), SEO clean {r['seo_clean']}/"
          f"{r['count']}, designs {r['art_generated']}/{r['count']}.")
    print(f"Folder        : {r['output_dir']}")
    print(f"Master SEO     : {r['master_excel']}")
    print(f"Upload checklist: {r['output_dir']}\\UPLOAD_CHECKLIST.txt")
    return 0


def _cmd_build_batch(args: list[str]) -> int:
    """Bulk-build the next N listing packages (SEO + optional art) to scale."""
    from quoteforge.etsy.bulk_builder import build_batch, format_batch_text
    batch = next((int(a) for a in args if a.isdigit()), 30)
    with_art = "--art" in args
    report = build_batch(batch=batch, with_art=with_art)
    print(format_batch_text(report))
    return 0


def _cmd_growth(args: list[str]) -> int:
    """Growth intelligence: what to scale, retire, and which demand gaps to fill."""
    from quoteforge.etsy.growth_intel import (
        growth_actions, format_growth_text, send_growth_report,
    )
    if args and args[0] == "email":
        out = send_growth_report()
        print(format_growth_text(out["growth"]))
        print(f"\nEmail: {out['status']}")
        return 0
    print(format_growth_text(growth_actions()))
    return 0


def _cmd_retention(args: list[str]) -> int:
    """Retention/LTV actions: repeat-gift outreach, cross-sell, win-backs."""
    from quoteforge.etsy.retention import (
        retention_digest, format_retention_text, send_retention_digest,
    )
    if args and args[0] == "email":
        out = send_retention_digest()
        print(format_retention_text(out["digest"]))
        print(f"\nEmail: {out['status']}")
        return 0
    print(format_retention_text(retention_digest()))
    return 0


def _cmd_seasonal_seo(args: list[str]) -> int:
    """Demand-driven SEO plan: what to refresh before each calendar peak."""
    from quoteforge.etsy.seasonal_seo import (
        seasonal_seo_plan, format_seasonal_seo, send_seasonal_seo,
    )
    if args and args[0] == "email":
        out = send_seasonal_seo()
        print(format_seasonal_seo(out["plan"]))
        print(f"\nEmail: {out['status']}")
        return 0
    print(format_seasonal_seo(seasonal_seo_plan()))
    return 0


def _cmd_seo(args: list[str]) -> int:
    """Per-listing Etsy SEO (title + 13 tags + attributes + description)."""
    from quoteforge.etsy.listing_seo import (
        build_launch_seo, format_seo_text, export_seo_excel,
        profession_seo, all_profession_seo, relationship_seo,
    )
    if args and args[0] == "prof" and len(args) > 1:
        print(format_seo_text(profession_seo(" ".join(args[1:]))))
        return 0
    if args and args[0] == "rel" and len(args) > 1:
        rel = args[1]
        occ = " ".join(args[2:]) if len(args) > 2 else "Birthday"
        print(format_seo_text(relationship_seo(rel, occ)))
        return 0
    if args and args[0] == "professions":
        bundles = all_profession_seo()
        bad = [b for b in bundles if b.warnings]
        print(f"Profession SEO coverage - {len(bundles) - len(bad)}/{len(bundles)} "
              f"job fields clean:")
        for b in bundles:
            flag = "[OK]" if not b.warnings else "[!!]"
            print(f"  {flag} {b.niche:18} title {len(b.title)}/140, {len(b.tags)} tags")
        return 0 if not bad else 1
    if args and args[0] == "export":
        path = export_seo_excel()
        print(f"All 20 listings' SEO exported to:\n  {path}")
        return 0
    bundles = build_launch_seo()
    if args and args[0].isdigit():
        n = int(args[0])
        match = next((b for b in bundles if b.listing_n == n), None)
        if not match:
            print(f"No launch listing #{n}.")
            return 1
        print(format_seo_text(match))
        return 0
    # summary: validate all + show first as example
    bad = [b for b in bundles if b.warnings]
    print(f"Generated SEO for {len(bundles)} launch listings - "
          f"{len(bundles) - len(bad)}/{len(bundles)} clean.")
    for b in bundles:
        flag = "[OK]" if not b.warnings else "[!!]"
        print(f"  {flag} #{b.listing_n:>2} {b.category:11} "
              f"title {len(b.title)}/140, {len(b.tags)} tags  ({b.niche})")
    print("\nView one:  admin seo 1     Export all:  admin seo export")
    return 0 if not bad else 1


def _cmd_listing_pack(args: list[str]) -> int:
    """Generate the full Etsy gallery image set from a print design."""
    from pathlib import Path
    from quoteforge.images.listing_pack import build_listing_pack, format_pack_text
    if not args:
        print("Usage: python -m quoteforge.admin listing-pack POSTER.png [out_dir]")
        return 2
    if not Path(args[0]).exists():
        print(f"Poster not found: {args[0]}")
        return 1
    out = args[1] if len(args) > 1 else None
    report = build_listing_pack(args[0], out)
    print(format_pack_text(report))
    return 0 if report["failed"] == 0 else 1


def _cmd_preflight_art(args: list[str]) -> int:
    """Run the artwork print-quality preflight on a file for a product size."""
    from quoteforge.images.preflight import run_preflight, format_preflight_text
    if not args:
        print("Usage: python -m quoteforge.admin preflight-art ART.png [size]")
        return 2
    product = args[1] if len(args) > 1 else ""
    report = run_preflight(args[0], product)
    print(format_preflight_text(report))
    return 0 if report["ok"] else 1


def _cmd_poll_etsy(args: list[str]) -> int:
    """Poll Etsy for new paid orders and import them (scheduled intake)."""
    from quoteforge.automation.etsy_poller import poll_once
    res = poll_once()
    if res.get("mock"):
        print("Etsy polling is in TEST/mock mode (no credentials) — no orders "
              "pulled. Set ETSY_OAUTH_TOKEN + ETSY_SHOP_ID to go live.")
        return 0
    print(f"Polled {res['polled']} receipt(s): imported {len(res['imported'])}, "
          f"skipped {res['skipped']}.")
    for oid in res["imported"]:
        print(f"  + imported order {oid}")
    return 0


def _cmd_costs(args: list[str]) -> int:
    """Detailed API cost report (today/week/month)."""
    from quoteforge.automation.cost_tracker import cost_report, format_cost_text
    period = args[0] if args and args[0] in ("today", "week", "month") else "today"
    print(format_cost_text(cost_report(period)))
    if len(args) > 1 and args[1] == "email" or (args and args[0] == "email"):
        from quoteforge.automation.emailer import send_cost_report
        r = send_cost_report(period)
        print(f"\nEmail: {r['status']}")
    return 0


def _cmd_policy(args: list[str]) -> int:
    """Show the Etsy + Gelato policy facts for an issue category (or all)."""
    from quoteforge.etsy.policy import POLICIES, format_policy_text
    if args:
        print(format_policy_text(args[0]))
        return 0
    for cat in POLICIES:
        print(format_policy_text(cat))
        print()
    return 0


def _cmd_resolve(args: list[str]) -> int:
    """Decide a customer issue (refund/replacement/claim) + draft the reply."""
    from quoteforge.etsy.resolution import (
        resolve_issue, format_resolution_text, ISSUE_CASES,
    )
    if not args:
        print("Usage: python -m quoteforge.admin resolve <issue> [ORDER_ID]")
        print("Issues: " + ", ".join(ISSUE_CASES.keys()))
        return 2
    category = args[0]
    order = None
    if len(args) > 1:
        from quoteforge.db.database import init_db, get_order
        init_db()
        order = get_order(args[1])
        if not order:
            print(f"Order {args[1]} not found.")
            return 1
    res = resolve_issue(category, order)
    print(format_resolution_text(res))
    return 0 if res["recognized"] else 2


def _cmd_bundles(args: list[str]) -> int:
    """Show the high-ticket gallery-set bundles (multi-piece, $180-500)."""
    from quoteforge.etsy.gallery_sets import (
        format_sets_text, sets_for_occasion, set_economics,
    )
    if args:
        matches = sets_for_occasion(" ".join(args))
        if not matches:
            print(f"No gallery sets match '{' '.join(args)}'.")
            return 0
        for s in matches:
            e = set_economics(s)
            print(f"{e['name']} — {e['pieces']}x {e['piece_format']}")
            print(f"  Price ${e['set_price']:.0f} | cost ${e['gelato_cost']:.0f} "
                  f"| profit ${e['net_profit']:.0f} | margin {e['margin_pct']:.0f}%")
        return 0
    print(format_sets_text())
    return 0


def _cmd_margins(args: list[str]) -> int:
    """Audit every product + gallery set against the target margin floor."""
    from quoteforge.etsy.margin_guard import audit_catalog, format_audit_text
    floor = float(args[0]) if args else None
    audit = audit_catalog(floor)
    print(format_audit_text(audit))
    return 1 if audit["below_floor"] else 0


def _cmd_mockup(args: list[str]) -> int:
    """Composite a poster PNG into a styled-room lifestyle mockup for the gallery."""
    from pathlib import Path
    from quoteforge.images.room_mockup import (
        render_room_mockup, WALL_PRESETS, FRAME_STYLES,
    )
    if not args:
        print("Usage: python -m quoteforge.admin mockup POSTER.png [out.png] "
              "[wall] [frame]")
        print(f"  walls : {', '.join(WALL_PRESETS)}")
        print(f"  frames: {', '.join(FRAME_STYLES)}")
        return 2
    poster = Path(args[0])
    if not poster.exists():
        print(f"Poster not found: {poster}")
        return 1
    out = Path(args[1]) if len(args) > 1 else poster.with_name(
        poster.stem + "_mockup.png")
    wall = args[2] if len(args) > 2 else "warm-gray"
    frame = args[3] if len(args) > 3 else "black"
    path = render_room_mockup(poster, out, wall=wall, frame_style=frame)
    print(f"Room mockup saved: {path}")
    print("Upload this to the Etsy gallery (it's a listing image, not the print).")
    return 0


def _cmd_maintenance(args: list[str]) -> int:
    """Daily self-healing agent: check infra, auto-fix ops issues, suggest more."""
    from quoteforge.automation.maintenance import (
        run_maintenance, format_maintenance_text, send_maintenance_digest,
    )
    fix = "--check" not in args  # --check = report only, change nothing
    if "email" in args:
        out = send_maintenance_digest(fix=fix, always=True)
        report = out["report"]
        print(format_maintenance_text(report))
        print(f"\nEmail: {out['status']}")
    else:
        report = run_maintenance(fix=fix)
        print(format_maintenance_text(report))
        # If something needs a human (failed fix / integrity alert), email anyway
        if report["overall"] == "ALERT":
            send_maintenance_digest(fix=False, always=True)
    return 1 if report["overall"] == "ALERT" else 0


def _cmd_install_schedule(args: list[str]) -> int:
    """Create (or remove) ALL Windows scheduled jobs from one source of truth."""
    from quoteforge.automation.scheduler import install_schedule, format_install_text
    remove = "--remove" in args or "--uninstall" in args
    dry_run = "--dry-run" in args or "--preview" in args
    summary = install_schedule(remove=remove, dry_run=dry_run)
    print(format_install_text(summary))
    if dry_run:
        print("\n(dry run - nothing changed. Re-run without --dry-run to apply.)")
        return 0
    if summary["errors"]:
        print("\nSome jobs failed. On Windows, run this in an ADMIN terminal.")
        return 1
    if not remove:
        print("\nAll jobs registered. Verify any time with: "
              "python -m quoteforge.admin healthcheck")
    return 0


def _cmd_report(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin report`."""
    from quoteforge.db.database import init_db
    from quoteforge.etsy.reports import period_report, format_report_text, PERIODS
    if not args or args[0] not in PERIODS:
        print(f"Usage: python -m quoteforge.admin report <{'|'.join(PERIODS)}> [email]")
        return 2
    init_db()
    period = args[0]
    rep = period_report(period)
    print(format_report_text(rep))
    if len(args) > 1 and args[1] == "email":
        from quoteforge.automation.emailer import send_period_report
        result = send_period_report(period)
        print(f"\nEmail: {result['status']}"
              + (f" -> {result.get('to')}" if result["status"] == "sent" else
                 f" ({result.get('message','')})"))
    return 0


def _cmd_reconcile(args: list[str]) -> int:
    """CLI handler for `python -m quoteforge.admin reconcile`."""
    from datetime import datetime
    from quoteforge.db.database import init_db
    from quoteforge.etsy.reconciliation import export_reconciliation
    from quoteforge.etsy.financials import month_financials
    init_db()
    if args and "-" in args[0]:
        year, month = (int(x) for x in args[0].split("-")[:2])
    else:
        now = datetime.now()
        year, month = now.year, now.month
    data = month_financials(year, month)
    path = export_reconciliation(year, month)
    print(f"Reconciliation for {data['period']} ({data['order_count']} billable orders):")
    print(f"  Revenue          : ${data['revenue']:.2f}")
    print(f"  Etsy fees        : -${data['etsy_fees']:.2f}")
    print(f"  Gelato cost      : -${data['gelato_cost']:.2f}")
    print(f"  NET PROFIT       : ${data['net_profit']:.2f}")
    print(f"  Sales tax (Etsy remits): ${data['sales_tax_collected']:.2f}")
    print(f"\n  Excel saved: {path}")
    return 0


def _cmd_email_report() -> int:
    """CLI handler for `python -m quoteforge.admin email-report`."""
    from quoteforge.automation.emailer import send_daily_report
    result = send_daily_report()
    if result["status"] == "sent":
        print(f"Daily report emailed to {result['to']}")
        print(f"  Subject: {result['subject']}")
        return 0
    print(f"Report not sent: {result['message']}")
    return 1


def _cmd_sample_quote() -> int:
    """Preview a REAL AI quote without disabling TEST_MODE (safe).

    This is Step 2 of the launch order: verify real AI quality while live
    Gelato fulfillment stays off.
    """
    from quoteforge import config
    if not config.ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set. Add it to .env first.")
        return 1
    from quoteforge.quotes.generator import generate_personal_message
    print("Generating a REAL AI quote (TEST_MODE stays on — Gelato untouched)...\n")
    try:
        variations = generate_personal_message(
            relationship="To My Daughter", recipient_name="Emma",
            sender_name="Mom", occasion="Graduation",
            memory_or_story="She worked so hard for four years and never gave up.",
            scenery="Mountains", output_style="Personal Letter",
            count=2, force_real=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Generation failed: {type(exc).__name__}: {exc}")
        return 1
    for i, v in enumerate(variations, 1):
        print(f"--- Variation {i} ---\n{v}\n")
    print("Review the quality above. If good, use a quote like this to create")
    print("artwork (Canva/Bannerbear) and place ONE manual Gelato sample order.")
    return 0


def _cmd_pinterest(args: list[str]) -> int:
    """Generate the Pinterest pin pack (images + pins.csv). `pinterest [N ...]`."""
    from quoteforge.marketing.pinterest import build_pin_pack
    nums = [int(a) for a in args if a.isdigit()] or None
    pins = build_pin_pack(nums)
    if not pins:
        print("No launch-kit gallery images found. Run: launch-kit first.")
        return 1
    from quoteforge.config import OUTPUT_DIR
    out = OUTPUT_DIR / "pinterest"
    print(f"Pinterest pack: {len(pins)} pins -> {out}")
    print(f"  Schedule CSV : {out / 'pins.csv'}")
    print("Bulk-upload the images and paste titles/descriptions from pins.csv.")
    return 0


def _cmd_pinterest_publish(args: list[str]) -> int:
    """Generate AND auto-post the pin pack. `pinterest-publish [--live] [N ...]`.
    Posts only when --live AND Pinterest is configured AND PINTEREST_AUTOPILOT=true;
    otherwise generates images + pins.csv for manual upload (safe dry-run)."""
    from quoteforge.marketing.pinterest_publisher import publish_pins
    live = "--live" in args
    nums = [int(a) for a in args if a.isdigit()] or None
    r = publish_pins(numbers=nums, live=live)
    print(r.get("message", ""))
    print(f"  Generated: {r['generated']}  Posted: {r['posted']}  "
          f"Failed: {r['failed']}  (configured={r['configured']}, live={r['live']})")
    return 0 if r["failed"] == 0 else 1


def _cmd_variations(args: list[str]) -> int:
    """Show the product/frame variation matrix + 60%-floor pricing, and write an
    Etsy inventory CSV (Material/Size/Frame -> price + Gelato SKU). `variations`."""
    import csv
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.etsy.variations import (
        build_variations, price_range, upsell_ladder, MATERIAL_LABELS)
    vs = build_variations()
    lo, hi = price_range()
    ladder = upsell_ladder()
    print(f"Variations: {len(vs)} | all clear 60%: {all(v.margin_pct>=60 for v in vs)}")
    print(f"Price range: ${lo:.2f} - ${hi:.2f}")
    print(f"Upsell ladder (lowest price/tier): entry ${ladder.get('entry',0):.2f}"
          f" -> mid(framed) ${ladder.get('mid',0):.2f}"
          f" -> top(canvas/acrylic/metal) ${ladder.get('top',0):.2f}")
    out = OUTPUT_DIR / "etsy_inventory.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["material", "size", "frame_color", "price", "margin_pct",
                    "gelato_sku", "gelato_cost", "tier"])
        for v in vs:
            w.writerow([MATERIAL_LABELS[v.material], v.size, v.frame_color,
                        f"{v.price:.2f}", v.margin_pct, v.gelato_sku,
                        f"{v.gelato_cost:.2f}", v.tier])
    print(f"Etsy inventory CSV -> {out}")
    print("Apply these as Variations on each listing (Material, Size, Frame "
          "color). Frame colors apply to the Framed material only.")
    # Bundle / quantity-discount ladder (holds the 60% floor).
    from quoteforge.etsy.variations import bundle_table
    entry = next((v for v in vs if v.tier == "entry"), vs[0])
    print(f"\nBUY MORE, SAVE MORE (e.g. {MATERIAL_LABELS[entry.material]} "
          f"{entry.size}, list ${entry.price:.2f}):")
    for row in bundle_table(entry.price, entry.gelato_cost, entry.tier):
        print(f"  {row['qty']}x  unit ${row['unit']:.2f}  ({row['discount_pct']}% off)"
              f"  total ${row['total']:.2f}  margin {row['margin_pct']}%"
              f"  {'OK' if row['holds_floor'] else 'FLOOR!'}")
    return 0


def _cmd_frame_preview(args: list[str]) -> int:
    """Render a 'see it before you buy' preview (one mockup per frame/material)
    + an interactive page. `frame-preview [N|POSTER.png]`."""
    from pathlib import Path
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.images.frame_preview import build_preview_page
    arg = args[0] if args else "1"
    if arg.isdigit():
        kit = OUTPUT_DIR / "launch_kit"
        posters = sorted(kit.glob(f"{int(arg):02d}_*/poster*.png")) or \
            sorted(kit.glob(f"{int(arg):02d}_*/*.png"))
        if not posters:
            print(f"No poster for listing {arg}. Run: launch-kit")
            return 1
        poster = posters[0]
    else:
        poster = Path(arg)
        if not poster.exists():
            print(f"Not found: {poster}")
            return 1
    out = build_preview_page(poster)
    print("Frame/material preview built:")
    print(f"  File: {out}")
    print(f"  URL : {out.resolve().as_uri()}")
    print("Open it: tap each frame to see the exact look before buying.")
    return 0


def _cmd_ledger(args: list[str]) -> int:
    """General ledger P&L. `ledger [today|week|month|year|all] [email]`.
    Persists today's snapshot and (with 'email') emails the report."""
    from quoteforge.etsy.ledger import build_ledger, format_ledger_text, snapshot_today
    period = next((a for a in args if a in
                   ("today", "week", "month", "year", "all")), "month")
    snapshot_today()
    led = build_ledger(period)
    text = format_ledger_text(led)
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email(f"Joffiels General Ledger ({period})", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_ledger_breakdown(args: list[str]) -> int:
    """P&L split by channel, vendor & product type. `ledger-breakdown [period]`."""
    from quoteforge.etsy.ledger import build_breakdown, format_breakdown_text
    period = next((a for a in args if a in
                   ("today", "week", "month", "year", "all")), "month")
    print(format_breakdown_text(build_breakdown(period)))
    return 0


def _cmd_clv(args: list[str]) -> int:
    """Customer Lifetime Value dashboard from real orders. `clv [email]`."""
    from quoteforge.analytics.clv import build_clv, format_clv_text
    text = format_clv_text(build_clv())
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels CLV Dashboard", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_quote_performance(args: list[str]) -> int:
    """Rank quote themes by REAL sales performance. `quote-performance`."""
    from quoteforge.quotes.performance import (format_performance_text,
                                               ranked_categories)
    print(format_performance_text())
    print("\nTop categories (sales-ranked):")
    for i, c in enumerate(ranked_categories()[:10], 1):
        print(f"  {i:>2}. {c}")
    return 0


def _cmd_deploy_status(args: list[str]) -> int:
    """Production-readiness tracker. `deploy-status [--write-doc] [email]`."""
    from quoteforge.automation.deployment_state import format_text, write_migration_doc
    text = format_text()
    print(text)
    if "--write-doc" in args or "doc" in args:
        dest = write_migration_doc()
        print(f"\nMigration tracker written: {dest}")
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Production Readiness", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_check_print(args: list[str]) -> int:
    """AI + resolution quality check on a print photo.
    `check-print <image_path> [size e.g. 18x24]`."""
    if not args:
        print("Usage: check-print <image_path> [size]")
        return 2
    path = args[0]
    size = next((a for a in args[1:] if "x" in a.lower()), "18x24")
    from quoteforge.automation.print_quality import assess_photo, format_assessment_text
    a = assess_photo(path, size)
    print(format_assessment_text(a))
    if a["decision"] != "approve":
        from quoteforge.automation.print_quality import reupload_request
        print("\nRe-upload message:\n  " + reupload_request(a))
    return 0


def _cmd_validate_order(args: list[str]) -> int:
    """Validate an order is ready for Gelato. `validate-order <order_id>`."""
    if not args:
        print("Usage: validate-order <order_id>")
        return 2
    from quoteforge.db.database import get_order
    from quoteforge.automation.print_quality import validate_order_for_gelato
    o = get_order(args[0])
    if not o:
        print("Order not found.")
        return 1
    v = validate_order_for_gelato(o)
    print(f"Order {args[0]}: {'READY for Gelato' if v['ok'] else 'NOT ready'}")
    for i in v["issues"]:
        print(f"  - {i}")
    return 0


def _cmd_competitors(args: list[str]) -> int:
    """Competitor Intelligence. `competitors` (dashboard), `competitors refresh`,
    or `competitors add <shop> <listings> <min_price> <reviews>`."""
    from quoteforge.analytics import competitor_intel as ci
    if args and args[0] == "add" and len(args) >= 2:
        shop = args[1]
        def _num(i, cast):
            """Parse args[i] with ``cast``, or None when absent/invalid."""
            try:
                return cast(args[i])
            except (IndexError, ValueError):
                return None
        ci.record(shop, listings=_num(2, int), min_price=_num(3, float),
                  reviews=_num(4, int))
        print(f"Recorded snapshot for {shop}.")
        return 0
    if args and args[0] == "refresh":
        print(ci.refresh())
        return 0
    text = ci.format_competitor_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Competitor Intelligence", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_trends(args: list[str]) -> int:
    """Trend Prediction Engine. `trends [email]`."""
    from quoteforge.analytics.trend_engine import format_trend_text
    text = format_trend_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Trend Predictions", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_capacity(args: list[str]) -> int:
    """Production Capacity Monitor (vendor speed, delays, defects). `capacity [email]`."""
    from quoteforge.automation.capacity_monitor import format_capacity_text
    text = format_capacity_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Production Capacity", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_ab(args: list[str]) -> int:
    """Automated A/B testing results. `ab [email]`."""
    from quoteforge.analytics.ab_testing import format_ab_text
    text = format_ab_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels A/B Testing", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_crm(args: list[str]) -> int:
    """CRM dashboard. `crm` (overview) or `crm <email>` (single 360 view)."""
    email = next((a for a in args if "@" in a), "")
    if email:
        from quoteforge.analytics.crm import format_customer_text
        print(format_customer_text(email))
    else:
        from quoteforge.analytics.crm import format_crm_overview
        print(format_crm_overview())
    return 0


def _cmd_leaderboard(args: list[str]) -> int:
    """Referral & loyalty leaderboard. `leaderboard [email]`."""
    from quoteforge.analytics.referrals import format_leaderboard_text
    text = format_leaderboard_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Referral Leaderboard", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_preferences(args: list[str]) -> int:
    """Customer Preference Graph (data moat). `preferences [email]`."""
    from quoteforge.analytics.preference_graph import format_graph_text
    text = format_graph_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Customer Preference Graph", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_journey(args: list[str]) -> int:
    """Customer Journey Analysis (Clarity + owned funnel). `journey [email]`."""
    from quoteforge.automation.journey_analysis import format_journey_text
    text = format_journey_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Customer Journey Analysis", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_profit(args: list[str]) -> int:
    """Profit Optimization Engine - profit per listing/size/material/source.
    `profit [email]`."""
    from quoteforge.analytics.profit_optimizer import format_profit_text
    text = format_profit_text()
    print(text)
    if "email" in args:
        from quoteforge.automation.emailer import _send_email
        from quoteforge.config import REPORT_RECIPIENT
        html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
        _send_email("Joffiels Profit Optimization", html, to=REPORT_RECIPIENT)
        print("\nEmailed.")
    return 0


def _cmd_recover_customizations(args: list[str]) -> int:
    """Recover abandoned customizations. `recover-customizations [--send] [minutes]`."""
    from quoteforge.automation.customization_recovery import (
        run_recovery, format_recovery_text)
    minutes = next((int(a) for a in args if a.isdigit()), 60)
    if "--send" in args or "send" in args:
        r = run_recovery(minutes, send=True)
        print(f"Recovery emails sent: {r['sent']} / {r['candidates']} candidate(s).")
    else:
        print(format_recovery_text(minutes))
    return 0


def _cmd_dynamic_pricing(args: list[str]) -> int:
    """Show current seasonal-demand pricing state. `dynamic-pricing`."""
    from quoteforge.etsy.dynamic_pricing import format_dynamic_text, dynamic_price
    print(format_dynamic_text())
    # quick illustration on a sample list price
    sample = dynamic_price(49.99, cost=12.0, tier="entry")
    print(f"\nExample: list $49.99 -> ${sample['price']} "
          f"(+{sample['uplift_pct']}%, margin {sample['margin_pct']}%, "
          f"holds_floor={sample['holds_floor']})")
    return 0


def _cmd_gift_profiles(args: list[str]) -> int:
    """Memory-based gift profiles + upcoming reminders.
    `gift-profiles [remind [days]] [email]`."""
    from quoteforge.marketing.gift_profiles import format_reminders_text
    from quoteforge.db.database import get_gift_profiles
    if "remind" in args:
        days = next((int(a) for a in args if a.isdigit()), 21)
        text = format_reminders_text(days)
        print(text)
        if "email" in args:
            from quoteforge.automation.emailer import _send_email
            from quoteforge.config import REPORT_RECIPIENT
            html = f"<html><body><pre style='font-size:12px'>{text}</pre></body></html>"
            _send_email("Joffiels Gift Reminders", html, to=REPORT_RECIPIENT)
            print("\nEmailed.")
        return 0
    profiles = get_gift_profiles()
    print(f"Saved gift profiles: {len(profiles)}")
    for p in profiles[:30]:
        print(f"  {p['recipient_name']} ({p.get('relationship','')}) - "
              f"{p.get('occasion','')} {p.get('event_date','')} [{p['owner_email']}]")
    return 0


def _cmd_add_review(args: list[str]) -> int:
    """Record a REAL customer review. `add-review "Name" RATING "text" [photo_url] [listing]`."""
    if len(args) < 2:
        print('Usage: add-review "Name" RATING(1-5) "text" [photo_url] [listing]')
        return 2
    from quoteforge.db.database import add_review, init_db
    init_db()
    rid = add_review(args[0], int(args[1]),
                     args[2] if len(args) > 2 else "",
                     args[3] if len(args) > 3 else "",
                     args[4] if len(args) > 4 else "")
    print(f"Saved review #{rid}. It will show on the site after the next rebuild.")
    return 0


def _cmd_reviews(args: list[str]) -> int:
    """Show published reviews + average. `reviews`."""
    from quoteforge.db.database import get_published_reviews, review_stats, init_db
    init_db()
    st = review_stats()
    print(f"Reviews: {st['count']}  avg {st['avg']}/5")
    for r in get_published_reviews(50):
        print(f"  {r['rating']}*  {r.get('customer_name','?')}: "
              f"{(r.get('text') or '')[:70]}")
    return 0


def _cmd_collage(args: list[str]) -> int:
    """Build the homepage hero collage from brand/collage_src/ -> brand/hero.jpg."""
    from quoteforge.images.collage import build_collage
    out = build_collage()
    print(f"Hero collage built: {out}")
    print("Drop JPG/PNGs into brand/collage_src/ (dog, scenery, your family "
          "photo), rerun, then rebuild-site to use it as the hero.")
    return 0


def _cmd_ask(args: list[str]) -> int:
    """Ask Ange (the AI assistant) a customer question. `ask "your question"`."""
    if not args:
        print('Usage: ask "How long does shipping take?"')
        return 2
    from quoteforge.ai.ange import ask_ange
    print("Ange: " + ask_ange(" ".join(args))["answer"])
    return 0


def _cmd_financial_report(args: list[str]) -> int:
    """Expanded financial report: fee-type breakdown (incl. Offsite Ads),
    refund/cancellation rates, and traffic source. Pass an Etsy STATEMENT csv
    for the fee breakdown: `financial-report [etsy_statement.csv]`."""
    from quoteforge.db.database import init_db, get_all_orders
    from quoteforge.analytics.financial_reports import format_financial_report
    init_db()
    fee_summary = None
    csvs = [a for a in args if a.lower().endswith(".csv")]
    if csvs:
        from quoteforge.etsy.etsy_finance_import import import_statement_csv
        fee_summary = import_statement_csv(csvs[0])
    print(format_financial_report(get_all_orders(5000), fee_summary))
    return 0


def _cmd_import_etsy_finance(args: list[str]) -> int:
    """Import REAL Etsy financials from an Etsy Orders/statement CSV:
    `import-etsy-finance <path-to-csv>`. Writes actual order total, shipping,
    sales tax, fees, and net payout onto matching orders."""
    paths = [a for a in args if a.lower().endswith(".csv")]
    if not paths:
        print("Usage: import-etsy-finance <path-to-etsy-orders.csv>")
        print("  Download from Etsy: Shop Manager -> Settings -> Options -> "
              "Download Data -> Orders (CSV).")
        return 1
    from quoteforge.etsy.etsy_finance_import import (import_orders_csv,
                                                     format_import_text)
    print(format_import_text(import_orders_csv(paths[0])))
    return 0


def _cmd_monitor_orders(args: list[str]) -> int:
    """End-to-end order compliance monitor: validates every order against the
    approval/production/cancellation/refund policy + state machine. `monitor-
    orders email` also alerts the owner on violations/review items."""
    from quoteforge.automation.order_monitor import run_monitor, format_monitor_text
    r = run_monitor(send="email" in args)
    print(format_monitor_text(r))
    return 0


def _cmd_classify_claim(args: list[str]) -> int:
    """Classify a return/refund claim against the policy: `classify-claim
    <order_id> <issue_type>` (issue_type: damaged|printing_error|wrong_product|
    lost|changed_mind|wrong_personalization|low_quality_photo|...)."""
    if len(args) < 2:
        print("Usage: classify-claim <order_id> <issue_type>")
        return 1
    from quoteforge.db.database import init_db, get_order
    from quoteforge.automation.order_monitor import classify_claim
    from quoteforge.etsy.resolution import format_resolution_text
    init_db()
    res = classify_claim(args[1], get_order(args[0]))
    if not res.get("recognized"):
        print(f"Unrecognized issue. Options: {', '.join(res.get('options', []))}")
        return 1
    print(format_resolution_text(res))
    return 0


def _cmd_file_claim(args: list[str]) -> int:
    """Stage a Gelato reprint claim for an order: `file-claim <order_id>
    <issue_type> [photo ...]`. Builds the Report-Problem checklist (mandatory
    photos, 30-day window, dashboard deep link) + the keep-the-item customer
    reply, and records claim_status. Gelato takes NO returns - covered issues
    are reprinted, so the customer never ships anything back."""
    if len(args) < 2:
        print("Usage: file-claim <order_id> <issue_type> [photo ...]")
        return 1
    from quoteforge.db.database import init_db, get_order
    from quoteforge.fulfillment.gelato_returns import (build_claim_package,
                                                      format_claim_text, record_claim)
    init_db()
    order = get_order(args[0])
    if not order:
        print(f"Order {args[0]} not found.")
        return 1
    pkg = build_claim_package(order, args[1], photos=args[2:] or None)
    print(format_claim_text(pkg))
    if pkg["gelato_covered"]:
        record_claim(args[0], pkg["category"],
                     "ready" if pkg["ready_to_file"] else "staged")
    return 0


def _cmd_claims(args: list[str]) -> int:
    """Show the open-claims review queue: `claims [state]` (e.g.
    supplier_review, needs_more_info, new). No arg = all open claims."""
    from quoteforge.db.database import init_db
    from quoteforge.fulfillment.claim_workflow import (format_claims_queue,
                                                      run_claims_digest)
    init_db()
    if "email" in args:
        r = run_claims_digest(send=True)
        print(r["text"])
        print(f"({r['actionable']} actionable; owner emailed if any)")
        return 0
    print(format_claims_queue(states=args or None))
    return 0


def _cmd_claim_decide(args: list[str]) -> int:
    """Record + act on a claim decision: `claim-decide <order_id> <decision>
    [note...]`. decision = approved_reprint|approved_refund|denied|
    needs_more_info (or an intermediate review state). approved_reprint
    auto-creates the Gelato replacement; the customer is emailed the outcome."""
    if len(args) < 2:
        print("Usage: claim-decide <order_id> <decision> [note...]")
        return 1
    from quoteforge.db.database import init_db
    from quoteforge.fulfillment.claim_workflow import decide_claim
    init_db()
    r = decide_claim(args[0], args[1], note=" ".join(args[2:]), send=True)
    if not r["ok"]:
        print(f"Blocked: {r['reason']}")
        return 1
    print(f"Order {args[0]} -> {r['status']}")
    if r.get("replacement"):
        rep = r["replacement"]
        print(f"  Replacement: {rep.get('status')} {rep.get('id', '') or rep.get('detail', '')}")
    if r.get("email"):
        print(f"  Customer email: {r['email'].get('status')}")
    return 0


def _cmd_claim_intake(args: list[str]) -> int:
    """Validate a customer service request against the order record and document
    it: `claim-intake <order_number> <email> <issue_type> [photo ...]`. Runs the
    order/email/supplier/window/evidence checks, prints the result, and records
    the recommended review status. (issue_type e.g. \"Damaged item\".)"""
    if len(args) < 3:
        print('Usage: claim-intake <order_number> <email> "<issue_type>" [photo ...]')
        return 1
    from quoteforge.db.database import init_db
    from quoteforge.fulfillment.claim_service import intake_claim, format_request_text
    init_db()
    result = intake_claim({"order_number": args[0], "email": args[1],
                           "issue_type": args[2], "photos": args[3:],
                           "description": "(via CLI)"})
    print(format_request_text(result))
    return 0


def _cmd_claim_photos(args: list[str]) -> int:
    """Record customer-supplied claim photos on an order so claims auto-attach
    them: `claim-photos <order_id> <product|packaging|shipping_label> ...`."""
    if len(args) < 2:
        print("Usage: claim-photos <order_id> <product|packaging|shipping_label> ...")
        return 1
    from quoteforge.db.database import init_db, get_order
    from quoteforge.fulfillment.gelato_returns import record_claim_photos
    init_db()
    if not get_order(args[0]):
        print(f"Order {args[0]} not found.")
        return 1
    record_claim_photos(args[0], args[1:])
    print(f"Recorded {len(args[1:])} claim photo(s) on {args[0]}: "
          f"{', '.join(args[1:])}")
    return 0


def _cmd_dispute(args: list[str]) -> int:
    """Flag a delivered order as DISPUTED (Etsy case / refund / complaint) so it
    isn't a clean completion and no review is requested: `dispute <order_id>
    [reason...]`."""
    if not args:
        print("Usage: dispute <order_id> [reason]")
        return 1
    from quoteforge.automation.fulfillment_tracker import mark_delivery_disputed
    mark_delivery_disputed(args[0], reason=" ".join(args[1:]))
    print(f"Order {args[0]} marked delivery_disputed (review suppressed).")
    return 0


def _set_order_flag(oid: str, field: str, usage: str) -> int:
    """Set one owner override flag (=1) on an order; shared by the flag commands."""
    if not oid:
        print(usage)
        return 1
    from quoteforge.db.database import init_db, update_order, get_order
    init_db()
    if not get_order(oid):
        print(f"Order {oid} not found.")
        return 1
    update_order(oid, **{field: 1})
    print(f"Order {oid}: {field}=1.")
    return 0


def _cmd_mark_delivered(args: list[str]) -> int:
    """Owner override: confirm delivery manually (counts as a confirmed
    delivery for the review flow): `mark-delivered <order_id>`."""
    return _set_order_flag(args[0] if args else "", "manual_delivery_confirmed",
                           "Usage: mark-delivered <order_id>")


def _cmd_no_review(args: list[str]) -> int:
    """Owner override: never request a review for this order:
    `no-review <order_id>`."""
    return _set_order_flag(args[0] if args else "", "do_not_request_review",
                           "Usage: no-review <order_id>")


def _cmd_verify_tracking(args: list[str]) -> int:
    """LIVE smoke test of the carrier tracking API: `verify-tracking
    <tracking_number> [carrier]`. Confirms the real AfterShip/17track JSON
    matches the parser - run once after setting TRACKING_API_KEY."""
    if not args:
        print("Usage: verify-tracking <tracking_number> [carrier]")
        return 1
    from quoteforge.config import TRACKING_API_KEY, TRACKING_API_PROVIDER
    if not TRACKING_API_KEY:
        print("TRACKING_API_KEY not set - add it to .env to enable carrier "
              "confirmation, then re-run this live smoke test.")
        return 1
    from quoteforge.fulfillment.tracking_api import carrier_status
    st = carrier_status(args[0], args[1] if len(args) > 1 else "")
    print(f"Provider: {TRACKING_API_PROVIDER}  Tracking: {args[0]}")
    print(f"Normalized carrier state: {st or '(none / unknown)'}")
    print("OK - the live response parsed." if st else
          "No usable state - check the tracking number/carrier or the parser.")
    return 0


def _cmd_export_bi(args: list[str]) -> int:
    """Build the BI deliverables from live data: the Excel workbooks (with
    charts) in Excel/, and the Power BI package (star-schema CSVs + DAX +
    model/report spec + exec presentation PDF) in 'Power BI/'."""
    from quoteforge.analytics.bi_exports import export_all
    r = export_all()
    print("Excel workbooks:")
    for p in r["excel"]:
        print(f"  {p}")
    print(f"Power BI data files : {len(r['powerbi']['data'])} CSVs + DAX + model + README")
    print(f"Power BI PBIP project: {r['pbip']['pbip']} ({len(r['pbip']['files'])} files)")
    print(f"Presentation (PDF)  : {r['presentation_pdf']}")
    print(f"Presentation (PPTX) : {r['presentation_pptx']}")
    return 0


def _cmd_scan_disputes(args: list[str]) -> int:
    """Auto-detect Etsy refunds/cases on delivered orders and flag them
    `delivery_disputed` (suppresses the review request). Pulls the recent Etsy
    receipts feed; disabled (no-op) without Etsy credentials."""
    from quoteforge.db.database import init_db
    from quoteforge.automation.dispute_scanner import scan_etsy_disputes
    init_db()
    r = scan_etsy_disputes()
    if r["status"] == "disabled":
        print("Dispute scan disabled — set Etsy API credentials in .env to enable.")
        return 0
    if r["disputed"]:
        print(f"Flagged {len(r['disputed'])} disputed order(s): "
              f"{', '.join(r['disputed'])}")
        try:
            from quoteforge.automation.emailer import _send_email
            _send_email("⚠️ Etsy dispute detected on delivered order(s)",
                        "<pre>Flagged delivery_disputed: "
                        + ", ".join(r["disputed"]) + "</pre>")
        except Exception:  # noqa: BLE001
            pass
    else:
        print("No new Etsy disputes detected.")
    return 0


def _cmd_winback(args: list[str]) -> int:
    """Staged lapsed-customer win-back (60d nudge / 90d 10% / 120d 15%).
    Dry-run by default; `winback send` actually emails + advances each stage."""
    from quoteforge.marketing.winback import run_winback, format_winback_text
    if "send" in args:
        r = run_winback(send=True)
        print(f"Win-back: {r['sent']} email(s) sent across stages.")
    else:
        print(format_winback_text())
    return 0


def _cmd_shipping_audit(args: list[str]) -> int:
    """Shipping-variance + profit-by-destination report. Emails the owner when
    orders are leaking margin on shipping (actual >> modeled/collected)."""
    from quoteforge.db.database import init_db, get_all_orders
    from quoteforge.etsy.shipping_audit import (format_shipping_audit_text,
                                                audit_shipping)
    init_db()
    orders = get_all_orders(1000)
    text = format_shipping_audit_text(orders)
    print(text)
    if "email" in args and audit_shipping(orders)["leak_count"]:
        try:
            from quoteforge.automation.emailer import _send_email
            _send_email("⚠️ Shipping margin leak detected", "<pre>" + text + "</pre>")
        except Exception:  # noqa: BLE001
            pass
    return 0


def _cmd_track_orders(args: list[str]) -> int:
    """Sync vendor tracking -> mark shipped/delivered + push tracking to buyers.
    Emails the owner when orders are stuck (no tracking past SLA) or polls errored."""
    from quoteforge.automation.fulfillment_tracker import sync_tracking, format_tracking_text
    r = sync_tracking()
    text = format_tracking_text(r)
    print(text)
    # Anything needing a human - stuck, missing tracking, stale in transit,
    # wrong-destination delivery, or poll errors - is the owner's to chase.
    if (r.get("stuck") or r.get("errors") or r.get("tracking_missing")
            or r.get("stale_in_transit") or r.get("address_mismatch")):
        try:
            from quoteforge.automation.emailer import _send_email
            _send_email("⚠️ Fulfillment needs attention",
                        "<pre>" + text + "</pre>")
        except Exception:  # noqa: BLE001
            pass
    return 0


def _cmd_order_by(args: list[str]) -> int:
    """Show the next gift order-by deadline. `order-by`."""
    from quoteforge.etsy.shipping_cutoff import upcoming_cutoff, banner_text
    c = upcoming_cutoff()
    print(banner_text(c) if c else "No gift deadline within the window.")
    return 0


def _cmd_analytics(args: list[str]) -> int:
    """Show the analytics block (Etsy stats + GA + Clarity) - also in the daily
    briefing. `analytics`."""
    from quoteforge.automation.analytics_report import (analytics_summary,
                                                        format_analytics_text)
    print(format_analytics_text(analytics_summary()))
    return 0


def _cmd_golive_pdf(args: list[str]) -> int:
    """Generate the Go-Live checklist PDF (ordered steps + commands). `golive-pdf`."""
    from quoteforge.etsy.golive_doc import build_golive_pdf
    out = build_golive_pdf()
    print(f"Go-Live checklist PDF: {out} ({out.stat().st_size // 1024} KB)")
    return 0


def _cmd_workflow_pdf(args: list[str]) -> int:
    """Generate the end-to-end workflow PDF (Etsy order -> delivery). `workflow-pdf`."""
    from quoteforge.etsy.workflow_doc import build_workflow_pdf
    out = build_workflow_pdf()
    print(f"Workflow PDF: {out} ({out.stat().st_size // 1024} KB)")
    return 0


def _cmd_exec_report(args: list[str]) -> int:
    """Build the executive report workbook (summary + charts + infra + roadmap).
    `exec-report [today|week|month|year|all]`."""
    from quoteforge.etsy.exec_report import build_exec_report
    period = next((a for a in args if a in
                   ("today", "week", "month", "year", "all")), "month")
    out = build_exec_report(period)
    print(f"Executive report: {out}")
    print("Tabs: Executive Summary (KPIs + charts) | P&L | Breakdown | "
          "Infrastructure (current state, AI workload, roadmap, opportunities).")
    return 0


def _cmd_monthly_review(args: list[str]) -> int:
    """Prior-month packet: reconciliation + ledger + exec report, archived +
    emailed. `monthly-review [email]`."""
    from quoteforge.automation.weekly_review import monthly_review
    r = monthly_review(email=("email" in args))
    print(f"Monthly report ({r['period']}) - {len(r['archive'])} file(s) archived:")
    for p in r["archive"]:
        print(f"  {p}")
    if r.get("emailed_to"):
        print(f"Emailed to {r['emailed_to']}.")
    return 0


def _cmd_weekly_review(args: list[str]) -> int:
    """Friday business review: TCO + key metrics + AI summary. `weekly-review [email]`."""
    from quoteforge.automation.weekly_review import weekly_review, format_review_text
    r = weekly_review(email=("email" in args))
    print(format_review_text(r))
    if r.get("emailed_to"):
        print(f"\nEmailed to {r['emailed_to']}.")
    return 0


def _cmd_ai_review(args: list[str]) -> int:
    """AI ops review: audit every step, flag issues, suggest improvements.
    `ai-review [email]`."""
    from quoteforge.automation.ai_ops_review import ai_review, format_review_text
    r = ai_review(email=("email" in args))
    print(format_review_text(r))
    if r.get("emailed"):
        print("\nEmailed.")
    return 0


def _cmd_vendors(args: list[str]) -> int:
    """List vendors + catalog counts. `vendors`."""
    from quoteforge.catalog.registry import vendor_summary
    print(vendor_summary())
    return 0


def _cmd_add_product(args: list[str]) -> int:
    """Add a product/service from any vendor.
    `add-product "Name" vendor [sku] [category] [type] [cost] [price]`."""
    if len(args) < 2:
        print('Usage: add-product "Name" vendor [sku] [category] [print|service|digital] [cost] [price]')
        return 2
    from quoteforge.catalog.registry import add_product
    name, vendor = args[0], args[1]
    sku = args[2] if len(args) > 2 else ""
    cat = args[3] if len(args) > 3 else ""
    typ = args[4] if len(args) > 4 else "print"
    cost = float(args[5]) if len(args) > 5 else 0.0
    price = float(args[6]) if len(args) > 6 else 0.0
    try:
        r = add_product(name, vendor, sku, cat, typ, cost, price)
    except ValueError as e:
        print(str(e))
        return 1
    print(f"Added #{r['id']}: {r['name']} ({r['vendor']}, {r['type']}).")
    return 0


def _cmd_list_products(args: list[str]) -> int:
    """List all sellable items across vendors. `list-products [vendor]`."""
    from quoteforge.catalog.registry import list_products
    vendor = args[0] if args else ""
    items = [p for p in list_products() if not vendor or p["vendor"] == vendor]
    print(f"Catalog items: {len(items)}")
    for p in items[:200]:
        print(f"  [{p['vendor']:8}] {p['name'][:34]:34} {p['item_type']:7} "
              f"cost ${p['cost']:.2f}  ({p['source']})")
    return 0


def _cmd_add_income(args: list[str]) -> int:
    """Record off-platform income (affiliate/wholesale). `add-income AMOUNT [channel] [source] [note]`."""
    if not args:
        print('Usage: add-income AMOUNT [affiliate|wholesale|other] [source] [note]')
        return 2
    from quoteforge.db.database import add_income, init_db
    init_db()
    amount = float(args[0])
    channel = args[1] if len(args) > 1 else "affiliate"
    source = args[2] if len(args) > 2 else ""
    note = args[3] if len(args) > 3 else ""
    iid = add_income(amount, channel, source, note)
    print(f"Recorded income #{iid}: ${amount:.2f} ({channel}).")
    return 0


def _cmd_ledger_excel(args: list[str]) -> int:
    """Export the full general ledger to Excel. `ledger-excel [period]`."""
    from quoteforge.etsy.ledger import export_ledger_excel
    period = next((a for a in args if a in
                   ("today", "week", "month", "year", "all")), "all")
    out = export_ledger_excel(period)
    print(f"Ledger exported: {out}")
    return 0


def _cmd_subscription_listing(args: list[str]) -> int:
    """Print the ready-to-publish Etsy membership/subscription listing."""
    from quoteforge.etsy.subscription_product import build_subscription_listing
    l = build_subscription_listing()
    print("=== ETSY LISTING: MEMBERSHIP / SUBSCRIPTION ===\n")
    print("TITLE:\n" + l["title"] + "\n")
    print("PLANS:")
    for p in l["plans"]:
        print(f"  - {p['name']}: ${p['price']:.0f}  (subscription_plan={p['id']})")
    print("\nTAGS (13):\n" + ", ".join(l["tags"]) + "\n")
    print("DESCRIPTION:\n" + l["description"])
    return 0


def _cmd_subscriptions(args: list[str]) -> int:
    """Manage subscriptions. `subscriptions` (list) |
    `subscriptions add EMAIL END_DATE [name] [plan]` | `subscriptions remind [days]`."""
    from quoteforge.db import database as db
    db.init_db()
    if args and args[0] == "add" and len(args) >= 3:
        sid = db.add_subscription(args[1], args[2],
                                  customer_name=args[3] if len(args) > 3 else "",
                                  plan=args[4] if len(args) > 4 else "monthly")
        print(f"Added subscription #{sid} for {args[1]} ending {args[2]}.")
        return 0
    if args and args[0] == "remind":
        from quoteforge.etsy.subscriptions import send_expiry_reminders, format_reminders_text
        days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 7
        print(format_reminders_text(send_expiry_reminders(within_days=days)))
        return 0
    subs = db.get_subscriptions()
    print(f"Subscriptions: {len(subs)}")
    for s in subs[:50]:
        print(f"  #{s['id']} {s['customer_email']}  {s['plan']}  ends {s['end_date']}"
              f"  [{s['status']}]")
    return 0


def _cmd_gift_note(args: list[str]) -> int:
    """AI-write a free personal gift note. `gift-note RECIPIENT FROM OCCASION [msg]`."""
    from quoteforge.ai.assistant import gift_note
    if len(args) < 3:
        print('Usage: gift-note "Recipient" "From" "Occasion" ["optional message"]')
        return 2
    note = gift_note(args[0], args[1], args[2], args[3] if len(args) > 3 else "")
    print(note)
    return 0


def _cmd_gift_addon_listing(args: list[str]) -> int:
    """Print the ready-to-publish Etsy 'Add a gift e-card & free note' listing."""
    from quoteforge.etsy.gift_ecard import build_addon_listing
    l = build_addon_listing()
    print("=== ETSY ADD-ON LISTING: GIFT E-CARD + FREE NOTE ===")
    print(f"PRICE: ${l['price']:.2f}  (digital add-on)\n")
    print("TITLE:\n" + l["title"] + "\n")
    print("TAGS (13):\n" + ", ".join(l["tags"]) + "\n")
    print("PERSONALIZATION PROMPT:\n" + l["personalization"] + "\n")
    print("DESCRIPTION:\n" + l["description"])
    return 0


def _cmd_affiliates(args: list[str]) -> int:
    """Print the apply-ready directory of major affiliate programs/networks,
    marking which you've already configured. `affiliates`."""
    from quoteforge.marketing.affiliate_programs import apply_checklist
    print(apply_checklist())
    return 0


def _cmd_gelato_sync(args: list[str]) -> int:
    """Sync prices + availability from Gelato into catalog_state (auto-reprices
    to 60% and disables discontinued frames/products). `gelato-sync`."""
    from quoteforge.automation.gelato_sync import sync_catalog, format_sync_text
    r = sync_catalog()
    print(format_sync_text(r))
    return 0


def _cmd_rebuild_site(args: list[str]) -> int:
    """Rebuild the public GitHub Pages shop-home page (docs/index.html) with the
    latest listings + analytics tags. Run by backup-all's push, fully hands-free."""
    from pathlib import Path
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(out_path=Path("docs/index.html"), external_assets=True)
    print(f"Rebuilt {out} ({out.stat().st_size // 1024} KB, lazy-loaded assets)")
    return 0


def _cmd_email_capture(args: list[str]) -> int:
    """Build the email-capture kit (QR, announcement, Linktree, signup snippet)."""
    from quoteforge.marketing.email_capture import build_capture_kit
    r = build_capture_kit()
    print(f"Email-capture kit -> {r['dir']}")
    print(f"  Signup URL : {r['signup_url'] or '(set SIGNUP_URL in .env)'}")
    print(f"  QR         : {r['qr_status']}")
    for f in r["files"]:
        print(f"  - {f}")
    return 0


def _cmd_subscribers(args: list[str]) -> int:
    """List subscribers, or `subscribers add EMAIL [source]`."""
    from quoteforge.db import database as db
    db.init_db()
    if args and args[0] == "add" and len(args) >= 2:
        ok = db.add_subscriber(args[1], args[2] if len(args) > 2 else "manual")
        print("Added." if ok else "Skipped (duplicate or invalid email).")
        return 0 if ok else 1
    subs = db.get_subscribers()
    print(f"Subscribers: {len(subs)}")
    for s in subs[:50]:
        print(f"  {s['created_at']}  {s['email']}  ({s['source']})")
    return 0


COMMANDS = {
    "variations": _cmd_variations,
    "frame-preview": _cmd_frame_preview,
    "affiliates": _cmd_affiliates,
    "subscriptions": _cmd_subscriptions,
    "subscription-listing": _cmd_subscription_listing,
    "ledger": _cmd_ledger,
    "ledger-excel": _cmd_ledger_excel,
    "ledger-breakdown": _cmd_ledger_breakdown,
    "clv": _cmd_clv,
    "quote-performance": _cmd_quote_performance,
    "dynamic-pricing": _cmd_dynamic_pricing,
    "gift-profiles": _cmd_gift_profiles,
    "profit": _cmd_profit,
    "recover-customizations": _cmd_recover_customizations,
    "preferences": _cmd_preferences,
    "journey": _cmd_journey,
    "crm": _cmd_crm,
    "leaderboard": _cmd_leaderboard,
    "capacity": _cmd_capacity,
    "ab": _cmd_ab,
    "competitors": _cmd_competitors,
    "trends": _cmd_trends,
    "check-print": _cmd_check_print,
    "validate-order": _cmd_validate_order,
    "deploy-status": _cmd_deploy_status,
    "vendors": _cmd_vendors,
    "add-review": _cmd_add_review,
    "reviews": _cmd_reviews,
    "ask": _cmd_ask,
    "collage": _cmd_collage,
    "order-by": _cmd_order_by,
    "track-orders": _cmd_track_orders,
    "shipping-audit": _cmd_shipping_audit,
    "winback": _cmd_winback,
    "import-etsy-finance": _cmd_import_etsy_finance,
    "financial-report": _cmd_financial_report,
    "monitor-orders": _cmd_monitor_orders,
    "classify-claim": _cmd_classify_claim,
    "file-claim": _cmd_file_claim,
    "claim-photos": _cmd_claim_photos,
    "claim-intake": _cmd_claim_intake,
    "claims": _cmd_claims,
    "claim-decide": _cmd_claim_decide,
    "dispute": _cmd_dispute,
    "mark-delivered": _cmd_mark_delivered,
    "no-review": _cmd_no_review,
    "verify-tracking": _cmd_verify_tracking,
    "scan-disputes": _cmd_scan_disputes,
    "export-bi": _cmd_export_bi,
    "ai-review": _cmd_ai_review,
    "weekly-review": _cmd_weekly_review,
    "monthly-review": _cmd_monthly_review,
    "exec-report": _cmd_exec_report,
    "workflow-pdf": _cmd_workflow_pdf,
    "golive-pdf": _cmd_golive_pdf,
    "analytics": _cmd_analytics,
    "add-product": _cmd_add_product,
    "list-products": _cmd_list_products,
    "add-income": _cmd_add_income,
    "gift-note": _cmd_gift_note,
    "gift-addon-listing": _cmd_gift_addon_listing,
    "gelato-sync": _cmd_gelato_sync,
    "pinterest": _cmd_pinterest,
    "pinterest-publish": _cmd_pinterest_publish,
    "rebuild-site": _cmd_rebuild_site,
    "email-capture": _cmd_email_capture,
    "subscribers": _cmd_subscribers,
    "gen-secret": lambda args: _cmd_gen_secret(),
    "backup": lambda args: _cmd_backup(),
    "backup-all": _cmd_backup_all,
    "restore": _cmd_restore,
    "restore-all": _cmd_restore_all,
    "site-doctor": _cmd_site_doctor,
    "launch-dash": _cmd_launch_dash,
    "list-backups": lambda args: _cmd_list_backups(),
    "daily-report": lambda args: _cmd_daily_report(),
    "preflight": lambda args: _cmd_preflight(),
    "verify-keys": lambda args: _cmd_verify_keys(),
    "sample-quote": lambda args: _cmd_sample_quote(),
    "email-report": lambda args: _cmd_email_report(),
    "report": _cmd_report,
    "healthcheck": _cmd_healthcheck,
    "install-schedule": _cmd_install_schedule,
    "maintenance": _cmd_maintenance,
    "mockup": _cmd_mockup,
    "bundles": _cmd_bundles,
    "margins": _cmd_margins,
    "resolve": _cmd_resolve,
    "policy": _cmd_policy,
    "costs": _cmd_costs,
    "preflight-art": _cmd_preflight_art,
    "listing-pack": _cmd_listing_pack,
    "seo": _cmd_seo,
    "seasonal-seo": _cmd_seasonal_seo,
    "retention": _cmd_retention,
    "growth": _cmd_growth,
    "build-batch": _cmd_build_batch,
    "launch-kit": _cmd_launch_kit,
    "listing-video": _cmd_listing_video,
    "preview-listing": _cmd_preview_listing,
    "showroom": _cmd_showroom,
    "publish-listings": _cmd_publish_listings,
    "delight": _cmd_delight,
    "check-photo": _cmd_check_photo,
    "custom-copy": _cmd_custom_copy,
    "remind": _cmd_remind,
    "briefing": _cmd_briefing,
    "shop-plan": _cmd_shop_plan,
    "fix-photo": _cmd_fix_photo,
    "sample-batch": _cmd_sample_batch,
    "artwork-qa": _cmd_artwork_qa,
    "poll-etsy": _cmd_poll_etsy,
    "autopilot": _cmd_autopilot,
    "approvals": _cmd_approvals,
    "plan": _cmd_plan,
    "campaign": _cmd_campaign,
    "sales": _cmd_sales,
    "calendar": _cmd_calendar,
    "products": _cmd_products,
    "tco": _cmd_tco,
    "launch": _cmd_launch,
    "reconcile": _cmd_reconcile,
    "show-proof": _cmd_show_proof,
    "customer-approved": _cmd_customer_approved,
}


def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch `python -m quoteforge.admin <command>` (prints usage
    when the command is missing or unknown)."""
    try:
        from quoteforge.automation.monitoring import init_monitoring
        init_monitoring()
    except Exception:  # noqa: BLE001 — monitoring is never load-bearing
        pass
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 0 if not argv else 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
