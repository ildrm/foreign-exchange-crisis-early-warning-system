#!/usr/bin/env sh
set -eu

# One-time PDF setup:
#   python3 -m pip install -e ".[pdf]"
#   python3 -m playwright install chromium

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
else
    echo "Python 3 was not found. Install Python 3 and try again." >&2
    exit 127
fi

"$PYTHON_BIN" "$SCRIPT_DIR/crisis_dashboard.py" \
    --countries tr \
    --as-of 2024-01-31 \
    --no-web \
    --event-database "$SCRIPT_DIR/examples/normalized_events.json" \
    --validate \
    --source-audit \
    --output "$SCRIPT_DIR/output/json/fx_cpm_report.json" \
    --html "$SCRIPT_DIR/output/html/fx_cpm_report.html" \
    --pdf "$SCRIPT_DIR/output/pdf/fx_cpm_report.pdf" \
    "$@"

echo "PDF report: $SCRIPT_DIR/output/pdf/fx_cpm_report.pdf"
