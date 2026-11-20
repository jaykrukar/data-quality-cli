"""Streaming-ish CSV validator using only the Python standard library."""
from __future__ import annotations
from collections import Counter
import csv
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

_ALLOWED_TYPES = {"str", "int", "float", "date", "bool"}


@dataclass(frozen=True)
class Issue:
    row: int
    column: str
    code: str
    message: str

    def as_dict(self):
        return asdict(self)


def load_schema(path: str | Path) -> dict:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(schema, dict) or not isinstance(schema.get("columns"), list):
        raise ValueError("Schema must be an object with columns array")
    names = []
    for column in schema["columns"]:
        if not isinstance(column, dict) or not isinstance(column.get("name"), str):
            raise ValueError("Each column requires a name")
        if column.get("type", "str") not in _ALLOWED_TYPES:
            raise ValueError(f"Invalid type for {column['name']}")
        names.append(column["name"])
    if len(names) != len(set(names)):
        raise ValueError("Duplicate schema column name")
    unique = schema.get("unique_by", [])
    if not isinstance(unique, list) or not set(unique).issubset(names):
        raise ValueError("unique_by must refer to existing column names")
    return schema


def _parse_value(raw: str, data_type: str):
    if data_type == "str":
        return raw
    if data_type == "int":
        value = int(raw)
        if str(value) != raw.strip() and raw.strip() not in (f"+{value}",):
            raise ValueError("Noncanonical integer")
        return value
    if data_type == "float":
        value = Decimal(raw)
        if not value.is_finite():
            raise ValueError("Nonfinite numeric value")
        return value
    if data_type == "date":
        return date.fromisoformat(raw)
    if data_type == "bool":
        if raw.lower() not in {"true", "false"}:
            raise ValueError("Expected true or false")
        return raw.lower() == "true"
    raise ValueError("Unsupported type")


def validate_csv(csv_path: str | Path, schema: dict) -> dict:
    rules = {col["name"]: col for col in schema["columns"]}
    unique_cols = schema.get("unique_by", [])
    issues: list[Issue] = []
    seen_keys: set[tuple[str,...]] = set()
    counters = Counter()
    n_rows = 0
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV must contain a header row")
        headers = reader.fieldnames
        missing = sorted(set(rules) - set(headers))
        if missing:
            raise ValueError("Missing required CSV columns: " + ", ".join(missing))
        if len(headers) != len(set(headers)):
            raise ValueError("CSV header contains duplicate column names")
        for row_num, row in enumerate(reader, start=2):
            n_rows += 1
            if None in row:
                issues.append(Issue(row_num, "", "extra_values", "More values than columns"))
            for name, rule in rules.items():
                raw = row.get(name)
                if raw is None:
                    issues.append(Issue(row_num, name, "missing", "Column value missing"))
                    counters[name] += 1
                    continue
                raw = raw.strip()
                if not raw:
                    if rule.get("required", True):
                        issues.append(Issue(row_num, name, "missing", "Required value empty"))
                        counters[name] += 1
                    continue
                try:
                    val = _parse_value(raw, rule.get("type", "str"))
                except (ValueError, InvalidOperation, OverflowError):
                    issues.append(Issue(row_num, name, "type", f"Invalid {rule.get('type', 'str')} value"))
                    continue
                if "choices" in rule and val not in rule["choices"]:
                    issues.append(Issue(row_num, name, "choice", "Value outside allowed set"))
                if rule.get("type") in ("int", "float"):
                    for key, description, fn in (("min", "minimum", lambda x,lim: x<lim),
                                                 ("max", "maximum", lambda x,lim: x>lim)):
                        if key in rule and fn(val, Decimal(str(rule[key]))):
                            issues.append(Issue(row_num, name, "range", f"Outside {description} bound"))
            if unique_cols:
                key = tuple((row.get(name) or "").strip() for name in unique_cols)
                if key in seen_keys:
                    issues.append(Issue(row_num, ",".join(unique_cols), "duplicate", "Repeated unique key"))
                seen_keys.add(key)
    return {
        "valid": not issues, "rows_checked": n_rows, "issues_count": len(issues),
        "issues_by_code": dict(Counter(issue.code for issue in issues)),
        "missing_values_by_column": dict(counters),
        "issues": [issue.as_dict() for issue in issues],
    }
