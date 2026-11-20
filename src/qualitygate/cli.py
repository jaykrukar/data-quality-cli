"""Validate a CSV, emit JSON, and return process exit code 1 on validation failure."""
import argparse
import json
from pathlib import Path
from .core import load_schema, validate_csv


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate CSV data with a JSON schema")
    parser.add_argument("csv", type=Path)
    parser.add_argument("schema", type=Path)
    parser.add_argument("--report", type=Path, help="Write JSON report to file")
    args = parser.parse_args(argv)
    try:
        report = validate_csv(args.csv, load_schema(args.schema))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    output = json.dumps(report, indent=2)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
