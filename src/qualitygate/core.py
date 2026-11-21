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
_NUMERIC_TYPES = {"int", "float"}
_COMPARISONS = {
    "lt": lambda left, right: left < right,
    "le": lambda left, right: left <= right,
    "eq": lambda left, right: left == right,
    "ne": lambda left, right: left != right,
    "ge": lambda left, right: left >= right,
    "gt": lambda left, right: left > right,
}


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
        if (not isinstance(column, dict) or not isinstance(column.get("name"), str)
                or not column["name"].strip()):
            raise ValueError("Each column requires a name")
        if column.get("type", "str") not in _ALLOWED_TYPES:
            raise ValueError(f"Invalid type for {column['name']}")
        if "required" in column and not isinstance(column["required"], bool):
            raise ValueError(f"required for {column['name']} must be boolean")
        if "choices" in column and not isinstance(column["choices"], list):
            raise ValueError(f"choices for {column['name']} must be an array")
        if column.get("type", "str") in _NUMERIC_TYPES:
            for bound in ("min", "max"):
                if bound in column:
                    try:
                        number = Decimal(str(column[bound]))
                    except InvalidOperation as exc:
                        raise ValueError(f"{bound} for {column['name']} must be numeric") from exc
                    if not number.is_finite():
                        raise ValueError(f"{bound} for {column['name']} must be finite")
        names.append(column["name"])
    if len(names) != len(set(names)):
        raise ValueError("Duplicate schema column name")
    unique = schema.get("unique_by", [])
    if (not isinstance(unique, list) or any(not isinstance(item, str) for item in unique)
            or len(unique) != len(set(unique)) or not set(unique).issubset(names)):
        raise ValueError("unique_by must refer to existing column names")
    rules = {column["name"]: column for column in schema["columns"]}
    for column in schema["columns"]:
        if "min" in column and "max" in column:
            if Decimal(str(column["min"])) > Decimal(str(column["max"])):
                raise ValueError(f"min exceeds max for {column['name']}")
    cross_field = schema.get("cross_field", [])
    if not isinstance(cross_field, list):
        raise ValueError("cross_field must be an array")
    for constraint in cross_field:
        if not isinstance(constraint, dict):
            raise ValueError("Each cross_field constraint must be an object")
        left, right, op = (constraint.get("left"), constraint.get("right"), constraint.get("op"))
        if not isinstance(left, str) or not isinstance(right, str) or not isinstance(op, str):
            raise ValueError("cross_field left, right, and op must be strings")
        if left not in rules or right not in rules:
            raise ValueError("cross_field must refer to existing columns")
        if rules[left].get("type", "str") not in _NUMERIC_TYPES or rules[right].get("type", "str") not in _NUMERIC_TYPES:
            raise ValueError("cross_field comparisons currently require numeric columns")
        if op not in _COMPARISONS:
            raise ValueError("cross_field op must be one of lt, le, eq, ne, ge, gt")
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


def validate_csv(csv_path: str | Path, schema: dict, max_issues: int | None = 1000) -> dict:
    """Validate a CSV row by row, retaining at most ``max_issues`` details.

    Set ``max_issues=None`` to retain every issue. Unique-key checks still keep
    their seen-key set in memory because exact duplicate detection requires it.
    """
    if max_issues is not None and (type(max_issues) is not int or max_issues < 0):
        raise ValueError("max_issues must be a nonnegative integer or None")
    rules = {col["name"]: col for col in schema["columns"]}
    unique_cols = schema.get("unique_by", [])
    cross_field = schema.get("cross_field", [])
    issues: list[Issue] = []
    issue_counts = Counter()
    total_issues = 0
    seen_keys: set[tuple[str,...]] = set()
    counters = Counter()
    n_rows = 0

    def record(issue: Issue) -> None:
        nonlocal total_issues
        total_issues += 1
        issue_counts[issue.code] += 1
        if max_issues is None or len(issues) < max_issues:
            issues.append(issue)

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
            parsed_values = {}
            if None in row:
                record(Issue(row_num, "", "extra_values", "More values than columns"))
            for name, rule in rules.items():
                raw = row.get(name)
                if raw is None:
                    record(Issue(row_num, name, "missing", "Column value missing"))
                    counters[name] += 1
                    continue
                raw = raw.strip()
                if not raw:
                    if rule.get("required", True):
                        record(Issue(row_num, name, "missing", "Required value empty"))
                        counters[name] += 1
                    continue
                try:
                    val = _parse_value(raw, rule.get("type", "str"))
                except (ValueError, InvalidOperation, OverflowError):
                    record(Issue(row_num, name, "type", f"Invalid {rule.get('type', 'str')} value"))
                    continue
                parsed_values[name] = val
                if "choices" in rule and val not in rule["choices"]:
                    record(Issue(row_num, name, "choice", "Value outside allowed set"))
                if rule.get("type") in ("int", "float"):
                    for key, description, fn in (("min", "minimum", lambda x,lim: x<lim),
                                                 ("max", "maximum", lambda x,lim: x>lim)):
                        if key in rule and fn(val, Decimal(str(rule[key]))):
                            record(Issue(row_num, name, "range", f"Outside {description} bound"))
            for constraint in cross_field:
                left, right, op = constraint["left"], constraint["right"], constraint["op"]
                if left in parsed_values and right in parsed_values:
                    if not _COMPARISONS[op](parsed_values[left], parsed_values[right]):
                        record(Issue(row_num, f"{left},{right}", "cross_field",
                                     f"Cross-field comparison {op} failed"))
            if unique_cols:
                key = tuple((row.get(name) or "").strip() for name in unique_cols)
                if key in seen_keys:
                    record(Issue(row_num, ",".join(unique_cols), "duplicate", "Repeated unique key"))
                seen_keys.add(key)
    return {
        "valid": total_issues == 0, "rows_checked": n_rows, "issues_count": total_issues,
        "issues_reported": len(issues), "issues_truncated": len(issues) < total_issues,
        "issues_by_code": dict(issue_counts),
        "missing_values_by_column": dict(counters),
        "issues": [issue.as_dict() for issue in issues],
    }
