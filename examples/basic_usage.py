"""
Basic usage examples for members-reader.

Run this file from the repo root:
    python examples/basic_usage.py
"""

from pathlib import Path
from members_reader import get_member_names, read_members

CSV_PATH = Path(__file__).parent.parent / "members.csv"


def example_get_names():
    """Print every member's full name."""
    print("=== Full Names ===")
    names = get_member_names(CSV_PATH)
    for name in names:
        print(f"  {name}")
    print(f"  Total: {len(names)}\n")


def example_read_all_fields():
    """Access every field for each member."""
    print("=== All Fields (first 3 rows) ===")
    members = read_members(CSV_PATH)
    for member in members[:3]:
        print(f"  {member}")
    print()


def example_filter_members():
    """Filter members by a field value."""
    print("=== Female Members (first 3) ===")
    members = read_members(CSV_PATH)
    female = [m for m in members if m.get("gender", "").lower() == "female"]
    for member in female[:3]:
        print(f"  {member['first_name']} {member['last_name']} — {member['email']}")
    print(f"  Total female members: {len(female)}\n")


def example_error_handling():
    """Demonstrate error handling."""
    print("=== Error Handling ===")
    try:
        get_member_names(Path("nonexistent.csv"))
    except FileNotFoundError as e:
        print(f"  Caught FileNotFoundError: {e}")

    try:
        from members_reader.reader import find_name_columns
        find_name_columns(["id", "email"])
    except ValueError as e:
        print(f"  Caught ValueError: {e}\n")


if __name__ == "__main__":
    example_get_names()
    example_read_all_fields()
    example_filter_members()
    example_error_handling()
