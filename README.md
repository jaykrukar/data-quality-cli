# QualityGate — explainable CSV data validation

[![Tests](https://github.com/jaykrukar/data-quality-cli/actions/workflows/tests.yml/badge.svg)](https://github.com/jaykrukar/data-quality-cli/actions/workflows/tests.yml)

A small dependency-free Python CLI that validates CSV datasets using JSON-defined field rules and produces machine-readable reports. An accessible demonstration of **reproducible data quality**, useful in both ML and scientific computing workflows.

## Run

```bash
python -m pip install -e '.[dev]'
python -m qualitygate examples/clean.csv examples/schema.json
python -m qualitygate examples/dirty.csv examples/schema.json --report report.json
# The dirty dataset intentionally returns nonzero exit code (validation failure).
python -m pytest -q
```

[Generated example validation report](docs/dirty_data_report.json).

## Features

- Required fields, strict type checks (`str`, `int`, `float`, ISO date, boolean).
- Numeric min/max, allowed choices, compound uniqueness keys, and configurable numeric cross-field comparisons.
- Human-readable issue reasons and JSON output useful in CI.
- Row-by-row CSV reading and a bounded issue-detail report (`--max-issues`); total counts remain complete. Exact unique-key validation retains its key set in memory.
- Non-zero exit status for schema failures and invalid datasets.
- No external runtime dependencies.

## Structure

- `src/qualitygate/core.py` — explicit validation rules and issue models.
- `src/qualitygate/cli.py` — reproducible CLI output and exit status.
- `examples/` — fully synthetic, non-sensitive example data with errors to detect.
- `tests/` — positive and negative validation tests.

## Limits

This is a lightweight prototype, **not** a full JSON Schema or production data governance system. Cross-field comparisons currently support numeric columns only. Exact uniqueness checks use memory proportional to unique keys, and the issue detail limit does not cap memory used by those keys. Regular expressions, advanced schema compatibility, and incremental database output are not included. All examples are fictitious and contain no patient data.

## Provenance

Initial implementation scaffolded with AI assistance. Review and extend it before claiming independent development. License: MIT.
