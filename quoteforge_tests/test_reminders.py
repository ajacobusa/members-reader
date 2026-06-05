"""Tests for persistent setup reminders."""
from unittest.mock import patch

import quoteforge.reminders as rem
from quoteforge import admin


def test_seeds_support_gmail_reminder(tmp_path):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path):
        items = rem.get_reminders()
    assert any("support" in i["text"].lower() and "gmail" in i["text"].lower()
               for i in items)


def test_add_and_done(tmp_path):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path):
        rid = rem.add_reminder("set up Pinterest")
        assert any(i["id"] == rid for i in rem.get_reminders())
        assert rem.done_reminder(rid) is True
        assert not any(i["id"] == rid for i in rem.get_reminders())


def test_persists_across_calls(tmp_path):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path):
        rem.add_reminder("X")
        n = len(rem.get_reminders())
        assert len(rem.get_reminders()) == n   # stable on reload


def test_html_block_when_items_present(tmp_path):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path):
        html = rem.reminders_html()
    assert "Setup Reminders" in html


def test_html_empty_when_cleared(tmp_path):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path):
        for i in list(rem.get_reminders()):
            rem.done_reminder(i["id"])
        assert rem.reminders_html() == ""


def test_cli_remind(tmp_path, capsys):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path):
        rc = admin.main(["remind"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "reminder" in out.lower()
