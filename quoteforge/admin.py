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
}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 0 if not argv else 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
