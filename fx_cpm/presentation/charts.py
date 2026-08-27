"""Dependency-free, accessible SVG charts for the FX-CPM HTML report.

The chart functions deliberately return complete static SVG.  The report does not
need JavaScript to communicate a value, uncertainty interval, or label.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from html import escape

_INK = "#f4f1e8"
_MUTED = "#b9c6d2"
_GRID = "#43576a"
_CYAN = "#6ecce6"
_VERMILION = "#db7564"
_POSITIVE = "#df9b69"
_NEGATIVE = "#77b9ce"


def _text(value: object) -> str:
    return escape("Not available" if value is None or value == "" else str(value), quote=True)


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _ratio(value: object) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if abs(number) > 1 and abs(number) <= 100:
        number /= 100
    return number if 0 <= number <= 1 else None


def _slug(value: object, fallback: str = "chart") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug[:54] or fallback


def _record_value(record: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _hazard_family(value: object) -> str:
    token = _slug(value, "event")
    if token in {"fx", "bop"} or "currency" in token or "balance-of-payments" in token:
        return "currency"
    if token == "bank" or "banking" in token:
        return "banking"
    if token == "sov" or "sovereign" in token or "default" in token or "debt" in token:
        return "sovereign"
    if token in {"pol", "coup"} or "political" in token or "government" in token:
        return "political"
    if token in {"civ", "war"} or "conflict" in token or "armed" in token:
        return "conflict"
    return "other"


def _event_marker_svg(family: str, x: float, y: float) -> str:
    css_class = f"event-marker event-marker--{family}"
    if family == "currency":
        shape = f'<path d="M{x - 5:.1f} {y + 4:.1f}h10l-5-9z" fill="{_VERMILION}"/>'
    elif family == "banking":
        shape = (
            f'<rect x="{x - 4.5:.1f}" y="{y - 4.5:.1f}" width="9" height="9" '
            f'fill="none" stroke="{_VERMILION}" stroke-width="2"/>'
        )
    elif family == "sovereign":
        shape = (
            f'<path d="M{x:.1f} {y - 6:.1f}l6 6-6 6-6-6z" fill="{_VERMILION}" '
            f'fill-opacity=".72" stroke="{_VERMILION}"/>'
        )
    elif family == "political":
        shape = (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="none" '
            f'stroke="{_VERMILION}" stroke-width="2"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.5" fill="{_VERMILION}"/>'
        )
    elif family == "conflict":
        shape = (
            f'<path d="M{x - 5:.1f} {y - 5:.1f}l10 10M{x + 5:.1f} {y - 5:.1f}l-10 10" '
            f'fill="none" stroke="{_VERMILION}" stroke-width="2"/>'
        )
    else:
        shape = (
            f'<path d="M{x - 5:.1f} {y:.1f}h10M{x:.1f} {y - 5:.1f}v10" '
            f'fill="none" stroke="{_VERMILION}" stroke-width="2"/>'
        )
    return f'<g class="{css_class}">{shape}</g>'


def hazard_icon_svg(hazard: object, *, size: int = 24) -> str:
    """Return a restrained schematic hazard icon with no externally loaded assets."""

    name = str(hazard or "").lower()
    common = (
        f'<svg class="hazard-icon" viewBox="0 0 24 24" width="{size}" height="{size}" '
        'aria-hidden="true" focusable="false">'
    )
    if "currency" in name or "balance" in name or "fx" in name:
        body = (
            '<path d="M4 7.5h16M4 16.5h16M8 4.5 4 7.5l4 3M16 13.5l4 3-4 3"/>'
        )
    elif "bank" in name:
        body = '<path d="m3 9 9-5 9 5M5 10v7m4-7v7m6-7v7m4-7v7M3 20h18"/>'
    elif "sovereign" in name or "debt" in name or "default" in name:
        body = '<path d="M5 4h14v16H5zM8 8h8M8 12h5M8 16h3"/><path d="m15 14 3 3"/>'
    elif "inflation" in name or "monetary" in name:
        body = '<path d="M4 18 9 12l4 3 7-10M16 5h4v4"/><path d="M4 21h16"/>'
    elif "coup" in name or "government" in name:
        body = '<path d="m4 9 8-5 8 5M6 10v8m12-8v8M3 20h18M10 10v8m4-8v8"/>'
    elif "political" in name:
        body = '<path d="M4 18V6l8 3 8-3v12l-8 3zM12 9v12"/>'
    elif "interstate" in name:
        body = '<path d="M5 5 19 19M19 5 5 19M4 4l4 1-3 3m15-4-4 1 3 3"/>'
    elif "conflict" in name or "armed" in name:
        body = '<path d="m4 19 6-6m4-4 6-6M6 3l15 15M3 6l15 15M4 3l3 1-3 3"/>'
    else:
        body = '<path d="M12 3 3.5 19h17zM12 8v5m0 3v.1"/>'
    return (
        common
        + f'<g fill="none" stroke="{_CYAN}" stroke-width="1.5" '
        'stroke-linecap="square" stroke-linejoin="miter">'
        + body
        + "</g></svg>"
    )


def term_structure_svg(
    points: Sequence[Mapping[str, object]],
    *,
    title: str,
    chart_id: str = "term-structure",
    value_keys: Sequence[str] = (
        "calibrated_probability",
        "risk_estimate",
        "raw_probability",
        "probability",
        "score",
    ),
    value_label: str = "Estimate",
) -> str:
    """Render a horizon term structure with optional uncertainty intervals."""

    clean: list[tuple[str, float, float | None, float | None]] = []
    for index, point in enumerate(points):
        horizon = _record_value(point, "horizon", "forecast_horizon", "label")
        raw = _record_value(point, *value_keys)
        value = _ratio(raw)
        if value is None:
            continue
        low = _ratio(_record_value(point, "lower", "lower_bound", "ci_low", "p05"))
        high = _ratio(_record_value(point, "upper", "upper_bound", "ci_high", "p95"))
        clean.append((str(horizon or f"H{index + 1}"), value, low, high))

    svg_id = _slug(chart_id)
    title_id = f"{svg_id}-title"
    desc_id = f"{svg_id}-desc"
    if not clean:
        return (
            f'<svg class="chart chart--empty" viewBox="0 0 720 230" role="img" '
            f'aria-labelledby="{title_id} {desc_id}">'
            f'<title id="{title_id}">{_text(title)}</title>'
            f'<desc id="{desc_id}">No numerical term-structure observations are available.</desc>'
            '<rect x="52" y="22" width="644" height="164" fill="none" '
            f'stroke="{_GRID}" stroke-dasharray="5 5"/>'
            f'<text x="374" y="111" fill="{_MUTED}" text-anchor="middle" '
            'font-size="14">Not available</text></svg>'
        )

    left, top, width, height = 58.0, 18.0, 630.0, 166.0
    baseline = top + height
    step = width / max(1, len(clean) - 1)

    def x_at(index: int) -> float:
        return left + (step * index if len(clean) > 1 else width / 2)

    def y_at(value: float) -> float:
        return top + height - (value * height)

    description = "; ".join(f"{label}: {value * 100:.1f}%" for label, value, _, _ in clean)
    parts = [
        f'<svg class="chart" viewBox="0 0 720 230" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{_text(title)}</title>',
        f'<desc id="{desc_id}">{_text(value_label)} by horizon. {_text(description)}.</desc>',
        '<defs>',
        f'<pattern id="{svg_id}-uncertainty" width="6" height="6" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">',
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{_CYAN}" stroke-width="1" '
        'opacity=".38"/></pattern>',
        '</defs>',
    ]
    for tick in (0, 0.25, 0.5, 0.75, 1):
        y = y_at(tick)
        parts.append(
            f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{left + width:.1f}" '
            f'y2="{y:.1f}" stroke="{_GRID}" stroke-width=".8" '
            f'stroke-dasharray="{("0" if tick == 0 else "3 5")}"/>'
        )
        parts.append(
            f'<text x="{left - 10:.1f}" y="{y + 4:.1f}" fill="{_MUTED}" '
            f'text-anchor="end" font-size="10">{tick * 100:.0f}%</text>'
        )

    if all(low is not None and high is not None for _, _, low, high in clean):
        upper = " ".join(
            f"{x_at(i):.1f},{y_at(high or 0):.1f}" for i, (_, _, _, high) in enumerate(clean)
        )
        lower = " ".join(
            f"{x_at(i):.1f},{y_at(low or 0):.1f}"
            for i, (_, _, low, _) in reversed(list(enumerate(clean)))
        )
        parts.append(
            f'<polygon points="{upper} {lower}" fill="url(#{svg_id}-uncertainty)" '
            f'stroke="{_CYAN}" stroke-width=".7" opacity=".8"/>'
        )

    line_points = " ".join(
        f"{x_at(i):.1f},{y_at(value):.1f}" for i, (_, value, _, _) in enumerate(clean)
    )
    parts.append(
        f'<polyline points="{line_points}" fill="none" stroke="{_CYAN}" '
        'stroke-width="2.4" stroke-linecap="square" stroke-linejoin="miter"/>'
    )
    for index, (label, value, _, _) in enumerate(clean):
        x, y = x_at(index), y_at(value)
        parts.extend(
            [
                f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" '
                f'fill="{_INK}" stroke="{_CYAN}" stroke-width="2"/>',
                f'<text x="{x:.1f}" y="{baseline + 22:.1f}" fill="{_INK}" '
                f'text-anchor="middle" font-size="10">{_text(label)}</text>',
                f'<text x="{x:.1f}" y="{max(top + 11, y - 10):.1f}" fill="{_INK}" '
                f'text-anchor="middle" font-size="10" font-weight="700">'
                f'{value * 100:.1f}%</text>',
            ]
        )
    parts.append(
        f'<text x="{left + width / 2:.1f}" y="225" fill="{_MUTED}" '
        'text-anchor="middle" font-size="10">Forecast horizon</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def diverging_bars_svg(
    contributors: Sequence[Mapping[str, object]],
    *,
    title: str = "Predictive contributors",
    chart_id: str = "contributors",
) -> str:
    """Render signed predictive contributions; negative values are contrary evidence."""

    clean: list[tuple[str, float]] = []
    for item in contributors:
        name = _record_value(item, "name", "feature", "label", "indicator")
        value = _number(_record_value(item, "contribution", "value", "effect", "score"))
        if name not in (None, "") and value is not None:
            clean.append((str(name), value))
    clean = clean[:12]
    svg_id = _slug(chart_id)
    title_id = f"{svg_id}-title"
    desc_id = f"{svg_id}-desc"
    if not clean:
        return (
            f'<svg class="chart chart--empty" viewBox="0 0 720 210" role="img" '
            f'aria-labelledby="{title_id} {desc_id}"><title id="{title_id}">{_text(title)}</title>'
            f'<desc id="{desc_id}">No contributor estimates are available.</desc>'
            f'<text x="360" y="105" fill="{_MUTED}" text-anchor="middle" '
            'font-size="14">Not available</text></svg>'
        )

    row_height = 27
    chart_height = max(210, 48 + row_height * len(clean))
    center, max_width = 390.0, 270.0
    scale = max(abs(value) for _, value in clean) or 1
    description = "; ".join(f"{name}: {value:+.2f}" for name, value in clean)
    parts = [
        f'<svg class="chart" viewBox="0 0 720 {chart_height}" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{_text(title)}</title>',
        f'<desc id="{desc_id}">Signed model contributions, not causal effects. '
        f'{_text(description)}.</desc>',
        f'<line x1="{center}" y1="22" x2="{center}" y2="{chart_height - 24}" '
        f'stroke="{_INK}" stroke-width="1"/>',
        f'<text x="{center - 10}" y="14" fill="{_MUTED}" text-anchor="end" '
        'font-size="10">Contrary evidence ←</text>',
        f'<text x="{center + 10}" y="14" fill="{_MUTED}" text-anchor="start" '
        'font-size="10">→ Raises estimate</text>',
    ]
    for index, (name, value) in enumerate(clean):
        y = 32 + index * row_height
        bar_width = abs(value) / scale * max_width
        x = center if value >= 0 else center - bar_width
        color = _POSITIVE if value >= 0 else _NEGATIVE
        dash = "" if value >= 0 else ' stroke-dasharray="4 2"'
        parts.extend(
            [
                f'<text x="108" y="{y + 12}" fill="{_INK}" text-anchor="end" '
                f'font-size="10">{_text(name)}</text>',
                f'<rect x="{x:.1f}" y="{y}" width="{max(1.5, bar_width):.1f}" height="15" '
                f'fill="{color}" fill-opacity=".68" stroke="{color}"{dash}/>',
                f'<text x="{(x + bar_width + 6 if value >= 0 else x - 6):.1f}" '
                f'y="{y + 12}" fill="{_INK}" '
                f'text-anchor="{("start" if value >= 0 else "end")}" font-size="10">'
                f'{value:+.2f}</text>',
            ]
        )
    parts.append("</svg>")
    return "".join(parts)


def reliability_svg(
    bins: Sequence[Mapping[str, object]],
    *,
    title: str = "Calibration reliability",
    chart_id: str = "reliability",
) -> str:
    """Render expected versus observed event rates with a perfect-calibration reference."""

    clean: list[tuple[float, float, int | None]] = []
    for item in bins:
        predicted = _ratio(_record_value(item, "predicted", "mean_predicted", "forecast", "x"))
        observed = _ratio(_record_value(item, "observed", "event_rate", "actual", "y"))
        count_num = _number(_record_value(item, "count", "n", "samples"))
        if predicted is not None and observed is not None:
            clean.append((predicted, observed, int(count_num) if count_num is not None else None))
    clean.sort(key=lambda item: item[0])
    svg_id = _slug(chart_id)
    title_id = f"{svg_id}-title"
    desc_id = f"{svg_id}-desc"
    if not clean:
        return (
            f'<svg class="chart chart--empty" viewBox="0 0 540 300" role="img" '
            f'aria-labelledby="{title_id} {desc_id}"><title id="{title_id}">{_text(title)}</title>'
            f'<desc id="{desc_id}">No calibration bins are available.</desc>'
            f'<text x="270" y="150" fill="{_MUTED}" text-anchor="middle" '
            'font-size="14">Reliability data not available</text></svg>'
        )

    left, top, size = 62.0, 20.0, 220.0

    def xy(predicted: float, observed: float) -> tuple[float, float]:
        return left + predicted * size, top + size - observed * size

    description = "; ".join(
        f"predicted {predicted * 100:.1f}%, observed {observed * 100:.1f}%"
        for predicted, observed, _ in clean
    )
    parts = [
        f'<svg class="chart chart--reliability" viewBox="0 0 540 300" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{_text(title)}</title>',
        f'<desc id="{desc_id}">Observed event rate against mean forecast. '
        f'{_text(description)}.</desc>',
    ]
    for tick in (0, 0.25, 0.5, 0.75, 1):
        x = left + tick * size
        y = top + size - tick * size
        parts.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + size}" y2="{y:.1f}" '
                f'stroke="{_GRID}" stroke-width=".7" stroke-dasharray="3 4"/>',
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + size}" '
                f'stroke="{_GRID}" stroke-width=".7" stroke-dasharray="3 4"/>',
                f'<text x="{left - 8}" y="{y + 4:.1f}" fill="{_MUTED}" '
                f'text-anchor="end" font-size="9">{tick * 100:.0f}%</text>',
                f'<text x="{x:.1f}" y="{top + size + 18}" fill="{_MUTED}" '
                f'text-anchor="middle" font-size="9">{tick * 100:.0f}%</text>',
            ]
        )
    parts.append(
        f'<line x1="{left}" y1="{top + size}" x2="{left + size}" y2="{top}" '
        f'stroke="{_MUTED}" stroke-width="1" stroke-dasharray="6 5"/>'
    )
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(p, o) for p, o, _ in clean))
    parts.append(
        f'<polyline points="{polyline}" fill="none" stroke="{_CYAN}" stroke-width="2.2"/>'
    )
    max_count = max((count or 1) for _, _, count in clean)
    for predicted, observed, count in clean:
        x, y = xy(predicted, observed)
        radius = 4 + (5 * math.sqrt((count or 1) / max_count))
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{_INK}" '
            f'stroke="{_CYAN}" stroke-width="2"/>'
        )
    parts.extend(
        [
            f'<text x="{left + size / 2}" y="286" fill="{_MUTED}" '
            'text-anchor="middle" font-size="10">Mean forecast</text>',
            f'<text x="18" y="{top + size / 2}" fill="{_MUTED}" text-anchor="middle" '
            'font-size="10" transform="rotate(-90 18 130)">Observed event rate</text>',
            f'<line x1="332" y1="67" x2="365" y2="67" stroke="{_MUTED}" '
            'stroke-dasharray="6 5"/>',
            f'<text x="375" y="71" fill="{_MUTED}" font-size="10">Perfect calibration</text>',
            f'<line x1="332" y1="96" x2="365" y2="96" stroke="{_CYAN}" '
            'stroke-width="2"/>',
            f'<text x="375" y="100" fill="{_INK}" font-size="10">Observed reliability</text>',
            f'<text x="332" y="135" fill="{_MUTED}" font-size="10">Marker size reflects bin count</text>',
            "</svg>",
        ]
    )
    return "".join(parts)


def timeline_svg(
    points: Sequence[Mapping[str, object]],
    events: Sequence[Mapping[str, object]],
    *,
    title: str = "Historical risk timeline",
    chart_id: str = "history",
) -> str:
    """Render a historical estimate timeline and separately labelled event markers."""

    clean: list[tuple[str, float, str]] = []
    for index, point in enumerate(points):
        date = _record_value(point, "date", "period", "analysis_date", "timestamp")
        value = _ratio(
            _record_value(
                point,
                "calibrated_probability",
                "risk_estimate",
                "estimate",
                "probability",
                "value",
                "score",
            )
        )
        vintage = str(
            _record_value(
                point,
                "vintage_state",
                "vintage_status",
                "estimate_type",
                "vintage",
            )
            or "unspecified"
        )
        if value is not None:
            clean.append((str(date or index + 1), value, vintage))
    svg_id = _slug(chart_id)
    title_id = f"{svg_id}-title"
    desc_id = f"{svg_id}-desc"
    if not clean:
        return (
            f'<svg class="chart chart--empty" viewBox="0 0 760 250" role="img" '
            f'aria-labelledby="{title_id} {desc_id}"><title id="{title_id}">{_text(title)}</title>'
            f'<desc id="{desc_id}">No historical estimates are available.</desc>'
            f'<text x="380" y="125" fill="{_MUTED}" text-anchor="middle" '
            'font-size="14">Historical series not available</text></svg>'
        )

    left, top, width, height = 54.0, 22.0, 674.0, 155.0
    step = width / max(1, len(clean) - 1)

    def x_at(index: int) -> float:
        return left + (index * step if len(clean) > 1 else width / 2)

    def y_at(value: float) -> float:
        return top + height - value * height

    reconstructed = any("reconstruct" in vintage.lower() for _, _, vintage in clean)
    description = "; ".join(
        f"{date}: {value * 100:.1f}% ({vintage})" for date, value, vintage in clean
    )
    event_description = "; ".join(
        f'{_hazard_family(_record_value(event, "hazard", "hazard_type", "type"))} '
        f'{_record_value(event, "date", "onset", "onset_canonical") or "date unavailable"}'
        for event in events[:18]
    )
    parts = [
        f'<svg class="chart" viewBox="0 0 760 285" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{_text(title)}</title>',
        f'<desc id="{desc_id}">Historical model estimates. {_text(description)}. '
        f'Documented event markers: {_text(event_description or "none supplied")}.</desc>',
    ]
    for tick in (0, 0.25, 0.5, 0.75, 1):
        y = y_at(tick)
        parts.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" '
                f'stroke="{_GRID}" stroke-width=".7" stroke-dasharray="3 5"/>',
                f'<text x="{left - 8}" y="{y + 3:.1f}" fill="{_MUTED}" '
                f'text-anchor="end" font-size="9">{tick * 100:.0f}%</text>',
            ]
        )
    polyline = " ".join(
        f"{x_at(index):.1f},{y_at(value):.1f}" for index, (_, value, _) in enumerate(clean)
    )
    line_pattern = 'stroke-dasharray="6 3"' if reconstructed else ""
    parts.append(
        f'<polyline points="{polyline}" fill="none" stroke="{_CYAN}" '
        f'stroke-width="2" {line_pattern}/>'
    )
    # Place events at an exact matching point where possible, otherwise distribute markers.
    date_indexes = {date: index for index, (date, _, _) in enumerate(clean)}
    for event_index, event in enumerate(events[:18]):
        event_date = str(_record_value(event, "date", "onset", "onset_canonical") or "")
        hazard = str(_record_value(event, "hazard", "hazard_type", "type") or "Crisis onset")
        index = date_indexes.get(event_date)
        if index is None:
            index = round(event_index * (len(clean) - 1) / max(1, len(events) - 1))
        x = x_at(index)
        family = _hazard_family(hazard)
        marker = _event_marker_svg(family, x, top + 9)
        parts.append(
            f'<g class="event-onset event-onset--{family}"><title>'
            f'{_text(hazard)} — {_text(event_date)}</title>'
            f'<line x1="{x:.1f}" y1="{top + 15:.1f}" x2="{x:.1f}" '
            f'y2="{top + height}" stroke="{_VERMILION}" stroke-width=".8" '
            f'stroke-dasharray="2 4"/>{marker}</g>'
        )
    label_indexes = sorted({0, len(clean) // 2, len(clean) - 1})
    for index in label_indexes:
        date = clean[index][0]
        parts.append(
            f'<text x="{x_at(index):.1f}" y="{top + height + 20:.1f}" fill="{_MUTED}" '
            f'text-anchor="middle" font-size="9">{_text(date)}</text>'
        )
    vintage_label = "Reconstructed estimate" if reconstructed else "True-vintage / as-of estimate"
    parts.extend(
        [
            f'<line x1="{left}" y1="224" x2="{left + 28}" y2="224" stroke="{_CYAN}" '
            f'stroke-width="2" {line_pattern}/>',
            f'<text x="{left + 36}" y="228" fill="{_MUTED}" font-size="9">'
            f'{_text(vintage_label)}</text>',
        ]
    )
    legend = (
        ("currency", "Currency"),
        ("banking", "Banking"),
        ("sovereign", "Sovereign"),
        ("political", "Political"),
        ("conflict", "Conflict"),
    )
    for legend_index, (family, label) in enumerate(legend):
        x = left + legend_index * 132
        parts.append(_event_marker_svg(family, x, 258))
        parts.append(
            f'<text x="{x + 10:.1f}" y="261" fill="{_MUTED}" font-size="9">'
            f'{_text(label)} onset</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


__all__ = [
    "diverging_bars_svg",
    "hazard_icon_svg",
    "reliability_svg",
    "term_structure_svg",
    "timeline_svg",
]
