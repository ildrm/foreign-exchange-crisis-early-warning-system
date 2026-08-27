#!/usr/bin/env python3
"""Export a self-contained FX-CPM HTML report to a print-faithful PDF."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fx_cpm.presentation.pdf import export_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export an FX-CPM self-contained HTML report to A4 landscape PDF."
    )
    parser.add_argument("html", type=Path, help="input HTML report")
    parser.add_argument("pdf", type=Path, help="output PDF path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        export_pdf(args.html, args.pdf)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"fx-cpm PDF export failed: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {args.pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
