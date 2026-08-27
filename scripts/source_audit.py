#!/usr/bin/env python3
"""Audit provenance records in an FX-CPM canonical report."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from fx_cpm.provenance import audit_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit provenance in an FX-CPM report JSON file.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--json", action="store_true", help="emit machine-readable findings")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failure")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"source audit failed: {exc}", file=sys.stderr)
        return 2
    records = payload.get("provenance")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        print("source audit failed: report.provenance must be an array of objects", file=sys.stderr)
        return 2

    findings = audit_records(records)
    errors = sum(item.level == "ERROR" for item in findings)
    warnings = sum(item.level == "WARNING" for item in findings)
    if args.json:
        print(
            json.dumps(
                {
                    "records": len(records),
                    "errors": errors,
                    "warnings": warnings,
                    "findings": [asdict(item) for item in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for item in findings:
            print(f"{item.level:<7} {item.code:<28} record={item.record}: {item.message}")
        print(f"Audited {len(records)} record(s): {errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
