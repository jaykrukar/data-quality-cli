from pathlib import Path
import json
import pytest
from qualitygate.core import load_schema, validate_csv

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_valid_data():
    result = validate_csv(EXAMPLES / "clean.csv", load_schema(EXAMPLES / "schema.json"))
    assert result["valid"]
    assert result["rows_checked"] == 2
    assert result["issues_count"] == 0


def test_invalid_data_reports_individual_issues():
    result = validate_csv(EXAMPLES / "dirty.csv", load_schema(EXAMPLES / "schema.json"))
    assert not result["valid"]
    assert result["issues_by_code"] == {
        "range": 2, "type": 2, "duplicate": 1, "missing": 1,
    }
    assert result["rows_checked"] == 3
    assert {issue["row"] for issue in result["issues"]} == {2, 3, 4}


def test_reject_duplicate_schema_fields(tmp_path):
    p = tmp_path / "schema.json"
    p.write_text(json.dumps({"columns": [{"name": "x"}, {"name": "x"}]}))
    with pytest.raises(ValueError, match="Duplicate"):
        load_schema(p)


def test_reject_missing_csv_headers(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("foo,bar\na,b\n")
    with pytest.raises(ValueError, match="Missing required"):
        validate_csv(p, load_schema(EXAMPLES / "schema.json"))


def test_nonfinite_values_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text((EXAMPLES / "clean.csv").read_text().replace("0.98", "NaN"))
    report = validate_csv(p, load_schema(EXAMPLES / "schema.json"))
    assert not report["valid"]
    assert "type" in report["issues_by_code"]


def test_cross_field_numeric_constraint(tmp_path):
    schema = {
        "columns": [
            {"name": "start", "type": "int"},
            {"name": "end", "type": "int"},
        ],
        "cross_field": [{"left": "start", "op": "le", "right": "end"}],
    }
    path = tmp_path / "intervals.csv"
    path.write_text("start,end\n1,2\n4,3\ninvalid,5\n")
    report = validate_csv(path, schema)
    assert report["issues_by_code"] == {"cross_field": 1, "type": 1}
    assert report["issues"][0]["row"] == 3


def test_issue_detail_limit_preserves_total_counts():
    report = validate_csv(EXAMPLES / "dirty.csv", load_schema(EXAMPLES / "schema.json"), max_issues=1)
    assert not report["valid"]
    assert report["issues_count"] == 6
    assert report["issues_reported"] == 1
    assert report["issues_truncated"]
    assert report["issues_by_code"] == {
        "range": 2, "type": 2, "duplicate": 1, "missing": 1,
    }


def test_invalid_issue_limit_rejected():
    with pytest.raises(ValueError, match="max_issues"):
        validate_csv(EXAMPLES / "clean.csv", load_schema(EXAMPLES / "schema.json"), max_issues=-1)


@pytest.mark.parametrize("cross_field", [
    [{"left": ["x"], "op": "le", "right": "y"}],
    [{"left": "x", "op": "approx", "right": "y"}],
    [{"left": "x", "op": "le", "right": "missing"}],
])
def test_invalid_cross_field_schema_rejected(tmp_path, cross_field):
    path = tmp_path / "schema.json"
    path.write_text(json.dumps({
        "columns": [{"name": "x", "type": "int"}, {"name": "y", "type": "int"}],
        "cross_field": cross_field,
    }))
    with pytest.raises(ValueError):
        load_schema(path)
