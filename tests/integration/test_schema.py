from __future__ import annotations

import json
from pathlib import Path

import pytest

from fx_cpm.demo import build_demo_report


def test_demo_matches_versioned_json_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parents[2] / "schemas" / "report.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        build_demo_report()
    )

