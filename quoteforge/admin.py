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
