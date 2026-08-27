#!/usr/bin/env python3
"""Dependency-free repository completeness checks used by scaffolding and CI."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def validate_project(root: Path) -> list[Check]:
    required_files = (
        "README.md",
        ".gitignore",
        "pyproject.toml",
        "crisis_dashboard.py",
        "schemas/report.schema.json",
        "METHODOLOGY.md",
        "MODEL_CARD.md",
        "CRISIS_TAXONOMY.md",
        "ALERT_POLICY.md",
        "BACKTESTING.md",
    )
    checks = [
        Check(
            f"file:{relative}",
            (root / relative).is_file() and (root / relative).stat().st_size > 0,
            relative,
        )
        for relative in required_files
    ]
    python_files = tuple((root / "fx_cpm").rglob("*.py"))
    test_files = tuple((root / "tests").rglob("test_*.py"))
    checks.append(Check("python-package", bool(python_files), f"{len(python_files)} Python files"))
    checks.append(Check("tests", bool(test_files), f"{len(test_files)} test files"))
    checks.append(Check("no-env", not (root / ".env").exists(), ".env must not be committed"))

    placeholder_pattern = re.compile(r"\b(?:TODO|FIXME)\b|NotImplementedError|^\s*pass\s*(?:#.*)?$", re.MULTILINE)
    placeholders: list[str] = []
    for path in python_files:
        if placeholder_pattern.search(path.read_text(encoding="utf-8")):
            placeholders.append(str(path.relative_to(root)))
    checks.append(
        Check(
            "no-placeholders",
            not placeholders,
            "none" if not placeholders else ", ".join(placeholders),
        )
    )
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate FX-CPM repository completeness.")
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = validate_project(args.root.resolve())
    if args.format == "json":
        print(json.dumps([asdict(item) for item in checks], indent=2))
    else:
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"{marker:<4} {check.name}: {check.detail}")
    return int(not all(item.passed for item in checks))


if __name__ == "__main__":
    raise SystemExit(main())

