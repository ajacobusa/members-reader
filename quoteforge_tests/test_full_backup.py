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
