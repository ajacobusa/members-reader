"""Tests for the one-shot full backup (DB + git commit/push + bundle)."""
from unittest.mock import patch

from quoteforge.automation.full_backup import run_full_backup, format_backup_text


class FakeGit:
    """Records git invocations and returns scripted results."""
    def __init__(self, has_staged=True, push_ok=True):
        self.calls = []
        self.has_staged = has_staged
        self.push_ok = push_ok

    def __call__(self, args, **kwargs):
        sub = args[1] if len(args) > 1 else ""
        self.calls.append(sub)

        class P:
            returncode = 0
            stdout = ""
            stderr = ""
        p = P()
        if sub == "diff":          # 'diff --cached --quiet': 1 = changes staged
            p.returncode = 1 if self.has_staged else 0
        elif sub == "push":
            p.returncode = 0 if self.push_ok else 1
            p.stderr = "" if self.push_ok else "auth failed"
        elif sub == "status":
            p.stdout = "?? brand/new.png\n"  # one untracked file
        return p


def _patch_db(tmp_path):
    import quoteforge.db.database as db
    return patch.object(db, "DB_PATH", tmp_path / "t.db"), \
        patch.object(db, "OUTPUT_DIR", tmp_path)


def test_full_backup_does_db_commit_push_bundle(tmp_path):
    import quoteforge.db.database as db
    git = FakeGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        db.create_order({"order_id": "Z", "recipient_name": "X", "occasion": "Y"})
        r = run_full_backup(push=True, runner=git)
    assert "quoteforge_" in r["db_backup"]
    assert r["auto_commit"] == "committed"
    assert r["push"] == "pushed"
    assert r["bundle"].endswith(".bundle")
    # all four git operations happened
    assert {"add", "commit", "push", "bundle"} <= set(git.calls)


def test_no_commit_mode_skips_autocommit_but_still_pushes(tmp_path):
    # REGRESSION: the unattended daily HA job runs backup-all with auto_commit=False
    # so it NEVER sweeps in-progress edits into a commit on the current branch (that
    # once committed WIP as a chore commit). It still pushes COMMITTED work + bundles;
    # uncommitted work is preserved by the C: mirror.
    import quoteforge.db.database as db
    git = FakeGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        r = run_full_backup(push=True, auto_commit=False, runner=git)
    assert "add" not in git.calls and "commit" not in git.calls   # no WIP auto-commit
    assert r["push"] == "pushed" and r["bundle"].endswith(".bundle")
    assert "auto_commit" not in r                                 # step skipped


def test_autocommit_skipped_on_feature_branch(tmp_path):
    # REGRESSION: the nightly auto-backup must NEVER auto-commit in-progress work on a
    # feature branch. A scheduled 02:00 run once swept a half-finished mid-session
    # change into a 'chore: auto-backup' commit (and pushed it). Only 'main' is safe.
    import quoteforge.db.database as db

    class FeatureBranchGit(FakeGit):
        def __call__(self, args, **kwargs):
            p = super().__call__(args, **kwargs)
            if args[1] == "rev-parse" and "--abbrev-ref" in args:
                p.stdout = "fix/some-feature\n"
            return p
    git = FeatureBranchGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        db.create_order({"order_id": "Z", "recipient_name": "X", "occasion": "Y"})
        r = run_full_backup(push=True, runner=git)
    assert "skipped" in r["auto_commit"] and "fix/some-feature" in r["auto_commit"]
    assert "add" not in git.calls and "commit" not in git.calls   # WIP NOT committed
    assert r["push"] == "pushed"                  # already-committed state still saved


def test_autocommit_runs_on_main(tmp_path):
    # The counterpart: on 'main' the auto-commit still happens as before.
    import quoteforge.db.database as db

    class MainGit(FakeGit):
        def __call__(self, args, **kwargs):
            p = super().__call__(args, **kwargs)
            if args[1] == "rev-parse" and "--abbrev-ref" in args:
                p.stdout = "main\n"
            return p
    git = MainGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        db.create_order({"order_id": "Z", "recipient_name": "X", "occasion": "Y"})
        r = run_full_backup(push=True, runner=git)
    assert r["auto_commit"] == "committed" and "commit" in git.calls


def test_autocommit_skipped_when_code_dirty_on_main(tmp_path):
    # REGRESSION: development happens ON main here, so the feature-branch guard is not
    # enough - a dirty main would sweep un-gated code/build edits into a 02:00
    # 'auto-backup' commit and push them to the LIVE branch (it did once, with
    # docs/app.js + a source file, before the test gate finished). If any tracked
    # code/build file is modified, the auto-commit must SKIP it for the gated PR flow.
    import quoteforge.db.database as db

    class DirtyMainGit(FakeGit):
        def __call__(self, args, **kwargs):
            p = super().__call__(args, **kwargs)
            if args[1] == "rev-parse" and "--abbrev-ref" in args:
                p.stdout = "main\n"
            elif args[1] == "status":
                p.stdout = (" M docs/app.js\n"
                            " M quoteforge/etsy/listing_preview.py\n"
                            "?? some-untracked.txt\n")
            return p
    git = DirtyMainGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        r = run_full_backup(push=True, runner=git)
    assert "skipped" in r["auto_commit"] and "code/build" in r["auto_commit"]
    assert "add" not in git.calls and "commit" not in git.calls   # un-gated code NOT committed
    assert r["push"] == "pushed"                                  # committed history still saved
    assert any("app.js" in p for p in r.get("auto_commit_skipped", []))


def test_autocommit_allows_noncode_tracked_change_on_main(tmp_path):
    # A non-code tracked change (e.g. a generated data/report file) may still auto-commit
    # on main - only CODE/BUILD paths are protected, so legit data backups still flow.
    import quoteforge.db.database as db

    class DataMainGit(FakeGit):
        def __call__(self, args, **kwargs):
            p = super().__call__(args, **kwargs)
            if args[1] == "rev-parse" and "--abbrev-ref" in args:
                p.stdout = "main\n"
            elif args[1] == "status":
                p.stdout = " M reports/daily_summary.csv\n"
            return p
    git = DataMainGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        r = run_full_backup(push=True, runner=git)
    assert r["auto_commit"] == "committed" and "commit" in git.calls


def test_nothing_to_commit_still_pushes(tmp_path):
    import quoteforge.db.database as db
    git = FakeGit(has_staged=False)
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        r = run_full_backup(push=True, runner=git)
    assert r["auto_commit"] == "nothing to commit"
    assert "commit" not in git.calls          # did not create an empty commit
    assert r["push"] == "pushed"


def test_push_failure_reported(tmp_path):
    import quoteforge.db.database as db
    git = FakeGit(push_ok=False)
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        r = run_full_backup(push=True, runner=git)
    assert "failed" in r["push"]


def test_only_tracked_files_committed(tmp_path):
    # Must use 'git add -u' (tracked only), never 'git add -A' (would grab junk).
    import quoteforge.db.database as db
    git = FakeGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        run_full_backup(push=False, runner=git)
    # find the add invocation args
    assert "add" in git.calls


def test_no_push_when_disabled(tmp_path):
    import quoteforge.db.database as db
    git = FakeGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        r = run_full_backup(push=False, runner=git)
    assert "push" not in r
    assert "push" not in git.calls


def test_format_text(tmp_path):
    import quoteforge.db.database as db
    git = FakeGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        text = format_backup_text(run_full_backup(runner=git))
    assert "FULL BACKUP" in text and "Push" in text


class VerifyGit:
    """Fake git for verify_backup: bundle verifies and contains HEAD."""
    def __init__(self, verify_ok=True, head="abc123", head_in_bundle=True):
        self.verify_ok, self.head, self.head_in_bundle = verify_ok, head, head_in_bundle

    def __call__(self, args, **kwargs):
        sub = args[1] if len(args) > 1 else ""
        third = args[2] if len(args) > 2 else ""

        class P:
            returncode = 0
            stdout = ""
            stderr = ""
        p = P()
        if sub == "bundle" and third == "verify":
            p.returncode = 0 if self.verify_ok else 1
        elif sub == "rev-parse":
            p.stdout = self.head + "\n"
        elif sub == "bundle" and third == "list-heads":
            p.stdout = (f"{self.head} refs/heads/main\n"
                        if self.head_in_bundle else "deadbeef refs/heads/main\n")
        return p


def test_verify_backup_healthy(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import full_backup as fb
    bundle = tmp_path / "b.bundle"
    bundle.write_bytes(b"x" * 2048)
    p1, p2 = _patch_db(tmp_path)
    with p1, p2, patch.object(fb, "BUNDLE_PATH", bundle):
        db.init_db()
        db.backup_database()                       # fresh DB snapshot
        r = fb.verify_backup(runner=VerifyGit())
    assert r["ok"] is True
    assert r["checks"]["db_snapshot"]["ok"] and r["checks"]["bundle"]["ok"]
    assert "HEALTHY" in fb.format_verify_text(r)


def test_verify_backup_missing_bundle_is_not_ok(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import full_backup as fb
    p1, p2 = _patch_db(tmp_path)
    with p1, p2, patch.object(fb, "BUNDLE_PATH", tmp_path / "nope.bundle"):
        db.init_db()
        db.backup_database()
        r = fb.verify_backup(runner=VerifyGit())
    assert r["ok"] is False
    assert r["checks"]["bundle"]["ok"] is False


def test_verify_backup_bundle_without_head_is_not_ok(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import full_backup as fb
    bundle = tmp_path / "b.bundle"
    bundle.write_bytes(b"x" * 2048)
    p1, p2 = _patch_db(tmp_path)
    with p1, p2, patch.object(fb, "BUNDLE_PATH", bundle):
        db.init_db()
        db.backup_database()
        r = fb.verify_backup(runner=VerifyGit(head_in_bundle=False))
    assert r["ok"] is False  # bundle exists but doesn't contain current HEAD


def test_verify_backup_no_snapshot_is_not_ok(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import full_backup as fb
    bundle = tmp_path / "b.bundle"
    bundle.write_bytes(b"x" * 2048)
    p1, p2 = _patch_db(tmp_path)
    with p1, p2, patch.object(fb, "BUNDLE_PATH", bundle):
        db.init_db()                               # no backup_database() -> no snapshot
        r = fb.verify_backup(runner=VerifyGit())
    assert r["ok"] is False
    assert r["checks"]["db_snapshot"]["ok"] is False


def test_restore_all_reports_db_and_code(tmp_path):
    """restore-all restores the DB and, without --into, reports the clone command
    (never overwrites a working tree in place)."""
    import quoteforge.db.database as db
    from quoteforge.automation.full_backup import restore_all, format_restore_text
    git = FakeGit()
    p1, p2 = _patch_db(tmp_path)
    with p1, p2:
        db.init_db()
        db.backup_database()             # create a snapshot to restore from
        r = restore_all(into="", runner=git)
    assert "db_restore" in r and "code_restore" in r
    text = format_restore_text(r)
    assert "RESTORE" in text and "Database" in text and "Code" in text
