import pytest
from pathlib import Path

from members_reader.reader import find_name_columns, get_member_names, read_members


class TestFindNameColumns:
    def test_standard_snake_case(self):
        first, last = find_name_columns(["id", "first_name", "last_name", "email"])
        assert first == "first_name"
        assert last == "last_name"

    def test_camel_case_aliases(self):
        first, last = find_name_columns(["firstname", "lastname"])
        assert first == "firstname"
        assert last == "lastname"

    def test_short_aliases(self):
        first, last = find_name_columns(["first", "last"])
        assert first == "first"
        assert last == "last"

    def test_extra_columns_ignored(self):
        first, last = find_name_columns(["id", "email", "first_name", "dob", "last_name"])
        assert first == "first_name"
        assert last == "last_name"

    def test_missing_first_name_raises(self):
        with pytest.raises(ValueError, match="first-name"):
            find_name_columns(["id", "last_name"])

    def test_missing_last_name_raises(self):
        with pytest.raises(ValueError, match="last-name"):
            find_name_columns(["id", "first_name"])

    def test_no_columns_raises(self):
        with pytest.raises(ValueError):
            find_name_columns([])


class TestReadMembers:
    def test_returns_all_rows(self, sample_csv):
        members = read_members(sample_csv)
        assert len(members) == 2

    def test_rows_are_dicts(self, sample_csv):
        members = read_members(sample_csv)
        assert isinstance(members[0], dict)

    def test_all_fields_present(self, sample_csv):
        members = read_members(sample_csv)
        assert set(members[0].keys()) == {"id", "first_name", "last_name", "email"}

    def test_empty_csv_returns_empty_list(self, empty_csv):
        assert read_members(empty_csv) == []

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_members(tmp_path / "missing.csv")

    def test_accepts_string_path(self, sample_csv):
        members = read_members(str(sample_csv))
        assert len(members) == 2


class TestGetMemberNames:
    def test_returns_full_names(self, sample_csv):
        names = get_member_names(sample_csv)
        assert names == ["Alice Smith", "Bob Jones"]

    def test_alternate_column_names(self, alternate_columns_csv):
        names = get_member_names(alternate_columns_csv)
        assert names == ["Carol White"]

    def test_empty_csv_returns_empty_list(self, empty_csv):
        assert get_member_names(empty_csv) == []

    def test_returns_list_of_strings(self, sample_csv):
        names = get_member_names(sample_csv)
        assert all(isinstance(n, str) for n in names)
