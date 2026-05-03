import csv
import json
import pytest

from members_reader.cli import main


class TestCLI:
    def test_prints_names(self, sample_csv, capsys):
        exit_code = main([str(sample_csv)])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Alice Smith" in out
        assert "Bob Jones" in out

    def test_json_output(self, sample_csv, capsys):
        exit_code = main([str(sample_csv), "--format", "json"])
        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data == ["Alice Smith", "Bob Jones"]

    def test_all_fields(self, sample_csv, capsys):
        exit_code = main([str(sample_csv), "--all-fields"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "alice@example.com" in out

    def test_all_fields_json(self, sample_csv, capsys):
        exit_code = main([str(sample_csv), "--all-fields", "--format", "json"])
        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert data[0]["first_name"] == "Alice"

    def test_missing_file_returns_exit_code_1(self, tmp_path, capsys):
        exit_code = main([str(tmp_path / "missing.csv")])
        assert exit_code == 1
        assert "Error" in capsys.readouterr().err

    def test_empty_csv(self, empty_csv, capsys):
        exit_code = main([str(empty_csv)])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_verbose_flag(self, sample_csv, capsys):
        exit_code = main([str(sample_csv), "--verbose"])
        assert exit_code == 0

    def test_bad_columns_returns_exit_code_1(self, tmp_path, capsys):
        bad_csv = tmp_path / "bad.csv"
        with open(bad_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "email"])
            writer.writeheader()
            writer.writerow({"id": "1", "email": "x@example.com"})
        exit_code = main([str(bad_csv)])
        assert exit_code == 1
        assert "Error" in capsys.readouterr().err
