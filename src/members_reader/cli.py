import argparse
import json
import logging
import sys
from pathlib import Path

from members_reader.reader import get_member_names, read_members


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="members-reader",
        description="Read and display member records from a CSV file.",
    )
    parser.add_argument("csv_file", type=Path, help="Path to the CSV file")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--all-fields",
        action="store_true",
        help="Output all CSV fields, not just names",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    try:
        if args.all_fields:
            data = read_members(args.csv_file)
            if args.format == "json":
                print(json.dumps(data, indent=2))
            else:
                for row in data:
                    print("  ".join(f"{k}: {v}" for k, v in row.items()))
        else:
            names = get_member_names(args.csv_file)
            if args.format == "json":
                print(json.dumps(names, indent=2))
            else:
                for name in names:
                    print(name)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
