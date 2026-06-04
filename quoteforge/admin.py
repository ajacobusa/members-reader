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
  python -m quoteforge.admin plan              # which occasions to create listings for now
  python -m quoteforge.admin campaign [Month]  # batch listing plan + publish-by dates (Excel)
  python -m quoteforge.admin sales             # today's upsell/review/win-back actions to send
  python -m quoteforge.admin calendar          # annual retailer timeline: list/market dates due
  python -m quoteforge.admin products [Occasion]  # full product range + 1-story-to-many bundle
  python -m quoteforge.admin tco [listings] [orders/mo]  # total cost of ownership breakdown
  python -m quoteforge.admin launch [scale N]  # the 20 starter listings; or next batch to add
  python -m quoteforge.admin reconcile [YYYY-MM]  # monthly bookkeeping Excel
  python -m quoteforge.admin show-proof ID    # show the proof message to send the buyer
  python -m quoteforge.admin customer-approved ID  # buyer approved -> release to print
"""
import sys

from quoteforge.secrets_util import generate_webhook_secret


def _cmd_gen_secret() -> int:
    secret = generate_webhook_secret()
    print("Generated webhook signing secret:\n")
    print(f"  {secret}\n")
    print("Add this to BOTH places (same value):")
    print("  1. .env  →  ETSY_WEBHOOK_SECRET=" + secret)
    print("  2. Make.com/Zapier HTTP module → sign body with HMAC-SHA256 →")
    print("     send as header  X-Webhook-Signature")
    return 0


def _cmd_backup() -> int:
    from quoteforge.db.database import backup_database, prune_old_backups
    path = backup_database()
    if not path:
        print("No database found to back up.")
        return 1
    deleted = prune_old_backups(keep=14)
    print(f"Backup created: {path}")
    if deleted:
        print(f"Pruned {deleted} old backup(s), keeping the most recent 14.")
    return 0


def _cmd_restore(args: list[str]) -> int:
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


def _cmd_list_backups() -> int:
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

    print()
    if anthropic_ok and g["ok"]:
        print("Both minimum keys verified live. You can run the real sample flow")
        print("(keep TEST_MODE=true — Gelato fulfillment stays manual).")
        return 0
    print("Not all keys verified. Add/fix keys in .env and re-run.")
    return 1


def _cmd_show_proof(args: list[str]) -> int:
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


COMMANDS = {
    "gen-secret": lambda args: _cmd_gen_secret(),
    "backup": lambda args: _cmd_backup(),
    "restore": _cmd_restore,
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
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 0 if not argv else 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
