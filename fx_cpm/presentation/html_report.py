"""Self-contained institutional HTML reporting for FX-CPM.

``render_html_report`` accepts only the canonical plain mapping.  It does not
reach into domain services and it deliberately has no template, charting, font,
or JavaScript dependencies.  That keeps research snapshots reproducible and
allows a saved report to remain useful offline with scripting disabled.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from html import escape
from urllib.parse import urlsplit

from .charts import (
    diverging_bars_svg,
    hazard_icon_svg,
    reliability_svg,
    term_structure_svg,
    timeline_svg,
)

_CANONICAL_HAZARDS: tuple[tuple[str, str], ...] = (
    ("currency-bop", "Currency / balance-of-payments crisis"),
    ("banking", "Systemic banking crisis"),
    ("sovereign", "Sovereign distress / default crisis"),
    ("inflation", "Monetary / inflation crisis"),
    ("political", "Major political-instability crisis"),
    ("coup", "Coup / unconstitutional government-change risk"),
    ("internal-conflict", "Internal armed-conflict onset / escalation"),
    ("interstate-conflict", "Interstate armed-conflict onset / escalation"),
)

_DEFAULT_HORIZONS = ("30 days", "90 days", "180 days", "12 months", "24 months", "36 months")

_SEVERITY_RANK = {
    "insufficient": -1,
    "low": 0,
    "watch": 1,
    "elevated": 2,
    "high": 3,
    "critical": 4,
}

_STYLE = r"""
:root {
  color-scheme: dark;
  --page: #07111b;
  --page-raised: #0a1622;
  --paper: #0d1925;
  --panel: #112131;
  --panel-quiet: #0c1a27;
  --ink: #f4f1e8;
  --ink-soft: #d7dce0;
  --muted: #b7c3cf;
  --line: #43586c;
  --line-strong: #667b8e;
  --info: #6ecce6;
  --low: #8cc8a9;
  --watch: #dfc36f;
  --elevated: #e2a06f;
  --high: #dd806f;
  --critical: #d76555;
  --unknown: #aeb9c4;
  --shadow: rgba(0, 0, 0, .26);
  --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --serif: Charter, "Bitstream Charter", Georgia, "Times New Roman", serif;
  --mono: ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  --content: 1420px;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; background: var(--page); }
body {
  margin: 0;
  min-width: 0;
  overflow-x: hidden;
  background-color: var(--page);
  color: var(--ink);
  font: 15px/1.58 var(--sans);
  -webkit-font-smoothing: antialiased;
}
body::before {
  position: fixed;
  inset: 0;
  z-index: -1;
  content: "";
  pointer-events: none;
  background-image:
    linear-gradient(rgba(110, 204, 230, .022) 1px, transparent 1px),
    linear-gradient(90deg, rgba(110, 204, 230, .018) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: linear-gradient(to bottom, black 0, transparent 72%);
}

a { color: var(--info); text-underline-offset: 3px; }
a:hover { color: var(--ink); }
:focus-visible { outline: 3px solid var(--info); outline-offset: 3px; }
.skip-link {
  position: fixed;
  z-index: 100;
  top: .75rem;
  left: .75rem;
  padding: .65rem 1rem;
  color: var(--page);
  background: var(--ink);
  transform: translateY(-180%);
}
.skip-link:focus { transform: translateY(0); }
.sr-only {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}
.js-only { display: none; }
.js .js-only { display: inline-flex; }

.report-header {
  position: relative;
  border-bottom: 1px solid var(--line);
  background: var(--page-raised);
}
.report-header::after {
  position: absolute;
  right: max(2rem, calc((100vw - var(--content)) / 2));
  bottom: -1px;
  width: min(35vw, 420px);
  height: 3px;
  content: "";
  background: var(--info);
}
.masthead {
  width: min(calc(100% - 3rem), var(--content));
  margin: 0 auto;
  padding: 2.2rem 0 1.55rem;
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(290px, .65fr);
  gap: 4rem;
  align-items: end;
}
.institution-mark {
  display: inline-flex;
  align-items: center;
  gap: .65rem;
  margin-bottom: 1.25rem;
  color: var(--info);
  font: 700 .7rem/1 var(--mono);
  letter-spacing: .16em;
  text-transform: uppercase;
}
.institution-mark::before {
  width: 34px;
  height: 9px;
  content: "";
  border-top: 2px solid var(--info);
  border-bottom: 1px solid var(--info);
}
h1, h2, h3, h4, p { margin-top: 0; }
.report-title {
  max-width: 900px;
  margin-bottom: .7rem;
  font: 400 clamp(3rem, 6.5vw, 6rem)/.84 var(--serif);
  letter-spacing: -.065em;
}
.report-title .dash { color: var(--info); }
.report-deck {
  max-width: 720px;
  margin-bottom: 0;
  color: var(--muted);
  font: 400 clamp(1rem, 1.5vw, 1.24rem)/1.5 var(--serif);
}
.mode-block {
  align-self: stretch;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 1.15rem 1.2rem;
  border: 1px solid var(--line-strong);
  border-left: 5px double var(--watch);
  background: #0a1723;
}
.mode-block[data-validated="true"] { border-left-color: var(--info); }
.kicker {
  display: block;
  margin-bottom: .5rem;
  color: var(--muted);
  font: 700 .67rem/1.25 var(--mono);
  letter-spacing: .13em;
  text-transform: uppercase;
}
.mode-value {
  margin: 0;
  color: var(--ink);
  font: 700 1.12rem/1.25 var(--mono);
  letter-spacing: .04em;
}
.mode-note { margin: .7rem 0 0; color: var(--muted); font-size: .83rem; }
.header-facts {
  width: min(calc(100% - 3rem), var(--content));
  margin: 0 auto;
  padding: .45rem 0;
  display: grid;
  grid-template-columns: minmax(220px, 1.7fr) repeat(3, minmax(145px, .75fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.header-fact { min-width: 0; padding: .85rem 1rem; background: var(--paper); }
.header-fact strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: .94rem;
  font-variant-numeric: tabular-nums;
}
.version-strip {
  width: min(calc(100% - 3rem), var(--content));
  margin: 0 auto;
  padding: 0 0 1.35rem;
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
}
.version-chip {
  display: inline-flex;
  gap: .45rem;
  padding: .35rem .55rem;
  border: 1px solid var(--line);
  color: var(--muted);
  background: var(--page);
  font: 650 .68rem/1.25 var(--mono);
  letter-spacing: .025em;
}
.version-chip b { color: var(--ink); font-weight: 700; }

.report-nav {
  position: sticky;
  z-index: 20;
  top: 0;
  border-bottom: 1px solid var(--line);
  background: rgba(7, 17, 27, .97);
}
.report-nav__inner {
  width: min(calc(100% - 3rem), var(--content));
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 1rem;
}
.report-nav ol {
  width: 100%;
  min-width: 0;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  overflow: visible;
  list-style: none;
  scrollbar-width: thin;
}
.report-nav a {
  display: block;
  min-height: 2rem;
  padding: .48rem .5rem;
  color: var(--muted);
  border-right: 1px solid rgba(67, 88, 108, .5);
  font: 700 .58rem/1.15 var(--mono);
  letter-spacing: .07em;
  text-decoration: none;
  text-transform: uppercase;
  white-space: nowrap;
}
.report-nav a:hover, .report-nav a:focus-visible { color: var(--ink); background: var(--panel); }
.control-button {
  flex: 0 0 auto;
  align-items: center;
  gap: .45rem;
  padding: .55rem .7rem;
  border: 1px solid var(--line-strong);
  border-radius: 0;
  color: var(--ink);
  background: var(--paper);
  font: 700 .7rem/1 var(--mono);
  cursor: pointer;
}
.control-button:hover { border-color: var(--info); background: var(--panel); }

main {
  width: min(calc(100% - 3rem), var(--content));
  margin: 0 auto;
}
.report-section {
  padding: clamp(2.35rem, 4vw, 4.15rem) 0;
  border-bottom: 1px solid var(--line);
  scroll-margin-top: 4rem;
}
.section-heading {
  margin-bottom: 1.45rem;
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) minmax(240px, .55fr);
  gap: 1.3rem;
  align-items: start;
}
.section-number {
  padding-top: .45rem;
  color: var(--info);
  font: 700 .78rem/1 var(--mono);
  letter-spacing: .13em;
}
.section-title {
  margin-bottom: 0;
  font: 400 clamp(2rem, 4vw, 4.15rem)/.98 var(--serif);
  letter-spacing: -.045em;
}
.section-intro {
  margin: .35rem 0 0;
  color: var(--muted);
  font-size: .9rem;
  line-height: 1.6;
}
.section-rule {
  width: 100%;
  height: 1px;
  margin-top: .85rem;
  background: linear-gradient(to right, var(--info) 0 18%, var(--line) 18% 100%);
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr);
  gap: 2rem;
}
.executive-copy {
  padding: 2rem;
  border-top: 3px solid var(--info);
  border-bottom: 1px solid var(--line);
  background: var(--paper);
}
.executive-copy p { max-width: 78ch; }
.lead { color: var(--ink); font: 400 1.32rem/1.55 var(--serif); }
.caution-statement {
  margin: 1.8rem 0 0;
  padding: 1rem 1.1rem;
  border-left: 3px double var(--watch);
  color: var(--ink-soft);
  background: #111d27;
  font-size: .88rem;
}
.overview-ledger { margin: 0; border-top: 1px solid var(--line); }
.overview-ledger > div {
  padding: 1.1rem 0;
  border-bottom: 1px solid var(--line);
}
.overview-ledger dt { color: var(--muted); font: 700 .67rem/1.2 var(--mono); letter-spacing: .1em; text-transform: uppercase; }
.overview-ledger dd { margin: .4rem 0 0; color: var(--ink); }
.limitation-callout {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: 170px 1fr;
  gap: 1.4rem;
  padding: 1.2rem 1.35rem;
  border: 1px dashed var(--watch);
  background: repeating-linear-gradient(-45deg, rgba(223,195,111,.035) 0 8px, transparent 8px 16px);
}
.limitation-callout strong { color: var(--watch); font: 700 .72rem/1.5 var(--mono); letter-spacing: .08em; text-transform: uppercase; }
.limitation-callout p { margin: 0; color: var(--ink-soft); }

.warning-stack { display: grid; gap: .8rem; }
.warning-card {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line-strong);
  border-left-width: 5px;
  background: var(--paper);
  box-shadow: 0 12px 35px var(--shadow);
}
.warning-card[data-risk="low"] { border-left-color: var(--low); border-left-style: solid; }
.warning-card[data-risk="watch"],
.warning-card[data-risk="watch-uncalibrated"] { border-left-color: var(--watch); border-left-style: dashed; }
.warning-card[data-risk="elevated"] { border-left-color: var(--elevated); border-left-style: double; }
.warning-card[data-risk="high"] { border-left-color: var(--high); border-left-style: ridge; }
.warning-card[data-risk="critical"] {
  border-left-color: var(--critical);
  border-left-style: double;
  background-image: repeating-linear-gradient(135deg, rgba(215,101,85,.035) 0 7px, transparent 7px 15px);
}
.warning-card[data-risk="insufficient"], .warning-card[data-risk="out-of-domain"] {
  border-left-color: var(--unknown);
  border-left-style: dotted;
}
.warning-header {
  padding: .78rem 1rem;
  display: flex;
  gap: 1rem;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--line);
  background: rgba(7, 17, 27, .5);
}
.hazard-label { min-width: 0; display: flex; align-items: center; gap: .85rem; }
.hazard-icon { flex: 0 0 auto; }
.hazard-label h3 { margin: 0; font: 600 1.22rem/1.2 var(--serif); }
.hazard-label p { margin: .25rem 0 0; color: var(--muted); font: 700 .7rem/1 var(--mono); text-transform: uppercase; }
.severity-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: .55rem;
  padding: .48rem .65rem;
  border: 1px solid currentColor;
  color: var(--watch);
  background: var(--page);
  font: 800 .7rem/1 var(--mono);
  letter-spacing: .045em;
  text-transform: uppercase;
}
.severity-badge[data-risk="low"] { color: var(--low); }
.severity-badge[data-risk="elevated"] { color: var(--elevated); border-style: double; }
.severity-badge[data-risk="high"] { color: var(--high); border-width: 2px; }
.severity-badge[data-risk="critical"] { color: var(--critical); border-style: double; border-width: 3px; }
.severity-badge[data-risk="insufficient"], .severity-badge[data-risk="out-of-domain"] { color: var(--unknown); border-style: dotted; }
.severity-symbol { font-size: 1rem; line-height: .6; }
.warning-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(250px, 330px); }
.warning-content { min-width: 0; padding: clamp(1rem, 1.8vw, 1.5rem); }
.estimate-row { display: flex; flex-wrap: wrap; align-items: end; gap: 1rem 2rem; }
.estimate-block { min-width: 220px; }
.estimate-value {
  display: block;
  color: var(--ink);
  font: 400 clamp(2.7rem, 6vw, 5.2rem)/.9 var(--serif);
  letter-spacing: -.045em;
  font-variant-numeric: tabular-nums;
}
.estimate-label { display: block; margin-top: .75rem; color: var(--muted); font: 700 .67rem/1.2 var(--mono); letter-spacing: .08em; text-transform: uppercase; }
.metric-grid {
  flex: 1;
  min-width: 260px;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(110px, 1fr));
  border-top: 1px solid var(--line);
  border-left: 1px solid var(--line);
}
.metric-grid > div { min-width: 0; padding: .7rem .8rem; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.metric-grid dt { color: var(--muted); font-size: .71rem; }
.metric-grid dd { margin: .2rem 0 0; color: var(--ink); font: 700 .96rem/1.35 var(--mono); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.warning-reading { margin-top: 1rem; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; }
.reading-note { padding-top: .8rem; border-top: 1px solid var(--line); }
.reading-note h4 { margin-bottom: .4rem; color: var(--muted); font: 700 .68rem/1.2 var(--mono); letter-spacing: .08em; text-transform: uppercase; }
.reading-note p { margin: 0; color: var(--ink-soft); }
.evidence-spine {
  position: relative;
  min-width: 0;
  padding: 1rem 1.1rem 1rem 2.25rem;
  border-left: 1px solid var(--line);
  background: var(--panel-quiet);
}
.evidence-spine::before {
  position: absolute;
  top: 1.8rem;
  bottom: 1.8rem;
  left: 1.25rem;
  width: 2px;
  content: "";
  background: var(--info);
}
.evidence-spine h4 { margin-bottom: 1rem; color: var(--info); font: 800 .72rem/1.2 var(--mono); letter-spacing: .1em; text-transform: uppercase; }
.evidence-spine ol { margin: 0; padding: 0; list-style: none; }
.evidence-spine li { position: relative; padding: 0 0 .9rem; }
.evidence-spine li::before {
  position: absolute;
  top: .35rem;
  left: -1.38rem;
  width: 8px;
  height: 8px;
  content: "";
  border: 2px solid var(--info);
  background: var(--panel-quiet);
}
.spine-key { display: block; color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; }
.spine-value { display: block; margin-top: .15rem; color: var(--ink); font-size: .82rem; overflow-wrap: anywhere; }

.table-region { width: 100%; overflow-x: auto; border: 1px solid var(--line); background: var(--paper); scrollbar-color: var(--line-strong) var(--page); }
.table-region:focus-visible { outline-offset: 4px; }
table { width: 100%; border-collapse: collapse; font-size: .79rem; font-variant-numeric: tabular-nums; }
caption { padding: .8rem 1rem; color: var(--muted); text-align: left; font: 700 .68rem/1.35 var(--mono); letter-spacing: .07em; text-transform: uppercase; }
th, td { padding: .7rem .75rem; border-right: 1px solid rgba(67,88,108,.65); border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--ink); background: #142637; font: 750 .68rem/1.35 var(--mono); letter-spacing: .035em; text-transform: uppercase; }
tbody th { min-width: 220px; color: var(--ink); background: var(--panel-quiet); text-transform: none; font-family: var(--sans); font-size: .79rem; letter-spacing: 0; }
tbody tr:last-child > * { border-bottom: 0; }
tr:hover > td, tr:hover > th { background-color: rgba(110, 204, 230, .045); }
.matrix-table { min-width: 980px; }
.matrix-cell { min-width: 125px; border-top: 3px solid var(--unknown); background: #0d1b28; }
.matrix-cell[data-risk="low"] { border-top-color: var(--low); }
.matrix-cell[data-risk="watch"], .matrix-cell[data-risk="watch-uncalibrated"] { border-top-color: var(--watch); border-top-style: dashed; }
.matrix-cell[data-risk="elevated"] { border-top-color: var(--elevated); border-top-style: double; }
.matrix-cell[data-risk="high"] { border-top-color: var(--high); }
.matrix-cell[data-risk="critical"] { border-top-color: var(--critical); border-top-style: double; }
.cell-estimate { display: block; color: var(--ink); font: 750 .93rem/1.2 var(--mono); }
.cell-status { display: block; margin-top: .28rem; color: var(--muted); font-size: .68rem; }
.cell-change { display: block; margin-top: .18rem; color: var(--ink-soft); font-size: .68rem; }
.unsupported { color: var(--muted); background: repeating-linear-gradient(135deg, rgba(174,185,196,.035) 0 5px, transparent 5px 10px); }
.sort-button { all: inherit; width: 100%; display: inline-flex; align-items: center; justify-content: space-between; gap: .5rem; cursor: pointer; }
.sort-button::after { content: "↕"; color: var(--info); }
.sort-button[aria-sort="ascending"]::after { content: "↑"; }
.sort-button[aria-sort="descending"]::after { content: "↓"; }

.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.25rem; }
.chart-panel, .analysis-panel {
  min-width: 0;
  break-inside: avoid;
  border: 1px solid var(--line);
  background: var(--paper);
}
.chart-panel__header, .panel-header { padding: 1rem 1.15rem; border-bottom: 1px solid var(--line); }
.chart-panel__header h3, .panel-header h3 { margin: 0; font: 600 1.18rem/1.25 var(--serif); }
.chart-panel__header p, .panel-header p { margin: .3rem 0 0; color: var(--muted); font-size: .76rem; }
.chart-wrap { min-width: 0; padding: .8rem .8rem .3rem; }
.chart { display: block; width: 100%; height: auto; overflow: visible; font-family: var(--sans); }
.chart--empty { border: 1px dashed var(--line); }
.chart-note { margin: 0; padding: .8rem 1rem 1rem; color: var(--muted); font-size: .76rem; }
.chart-data { margin: 0; border-top: 1px solid var(--line); }
.chart-data summary { padding: .75rem 1rem; color: var(--info); font: 700 .68rem/1 var(--mono); cursor: pointer; }
.chart-data .table-region { border-width: 1px 0 0; }
.full-span { grid-column: 1 / -1; }

.indicator-panel { padding: 1.2rem; border: 1px solid var(--line); background: var(--paper); }
.indicator-panel + .indicator-panel { margin-top: 1rem; }
.indicator-head { display: flex; gap: 1rem; align-items: start; justify-content: space-between; margin-bottom: 1rem; }
.indicator-head h3 { margin: 0; font: 600 1.25rem/1.2 var(--serif); }
.indicator-head p { margin: .2rem 0 0; color: var(--muted); font-size: .75rem; }
.status-label { padding: .35rem .5rem; border: 1px solid var(--line-strong); color: var(--ink); font: 700 .65rem/1 var(--mono); text-transform: uppercase; }
.indicator-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-top: 1px solid var(--line); border-left: 1px solid var(--line); }
.indicator { min-width: 0; min-height: 94px; padding: .75rem; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.indicator .kicker { margin-bottom: .6rem; }
.indicator-value { display: block; color: var(--ink); font: 600 1.17rem/1.2 var(--mono); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.indicator-note { display: block; margin-top: .35rem; color: var(--muted); font-size: .68rem; }
.indicator.is-missing { background: repeating-linear-gradient(-45deg, rgba(174,185,196,.025) 0 5px, transparent 5px 10px); }
.indicator.is-missing .indicator-value { color: var(--unknown); font: 650 .78rem/1.35 var(--sans); }
.two-column { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.25rem; }
.panel-body { padding: 1rem 1.15rem; }
.panel-body > :last-child { margin-bottom: 0; }
.definition-list { margin: 0; }
.definition-list > div { display: grid; grid-template-columns: minmax(120px, .35fr) minmax(0, 1fr); gap: 1rem; padding: .75rem 0; border-bottom: 1px solid var(--line); }
.definition-list > div:last-child { border-bottom: 0; }
.definition-list dt { color: var(--muted); font-size: .72rem; }
.definition-list dd { margin: 0; color: var(--ink); overflow-wrap: anywhere; }
.quality-meter { width: 100%; height: 11px; border: 1px solid var(--line-strong); border-radius: 0; background: var(--page); }
.quality-meter::-webkit-meter-bar { background: var(--page); border: 0; }
.quality-meter::-webkit-meter-optimum-value { background: repeating-linear-gradient(90deg, var(--info) 0 8px, #38798d 8px 10px); }
.quality-meter::-moz-meter-bar { background: var(--info); }
.provenance-table { min-width: 1150px; }
.source-link { max-width: 320px; overflow-wrap: anywhere; word-break: break-word; }
.unsafe-url { color: var(--muted); }
.limitations-list { margin: 0; padding: 0; counter-reset: limitations; list-style: none; border-top: 1px solid var(--line); }
.limitations-list li { position: relative; padding: 1rem 1rem 1rem 4rem; border-bottom: 1px solid var(--line); background: var(--paper); }
.limitations-list li::before { position: absolute; left: 1rem; top: 1rem; counter-increment: limitations; content: "L-" counter(limitations, decimal-leading-zero); color: var(--watch); font: 700 .7rem/1.5 var(--mono); }
.empty-state { padding: 2rem; border: 1px dashed var(--line-strong); background: repeating-linear-gradient(-45deg, rgba(174,185,196,.025) 0 7px, transparent 7px 14px); }
.empty-state h3 { margin-bottom: .4rem; font: 600 1.2rem/1.3 var(--serif); }
.empty-state p { max-width: 72ch; margin: 0; color: var(--muted); }

.report-footer {
  width: min(calc(100% - 3rem), var(--content));
  margin: 0 auto;
  padding: 2.5rem 0 3.5rem;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 2rem;
  color: var(--muted);
  font-size: .75rem;
}
.report-footer strong { color: var(--ink); }

@media (prefers-reduced-motion: no-preference) {
  .report-section { animation: section-reveal .28s ease-out both; }
  .report-section:nth-of-type(2n) { animation-delay: .04s; }
  @keyframes section-reveal { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: none; } }
}

@media (max-width: 940px) {
  .masthead { grid-template-columns: 1fr; gap: 2rem; }
  .header-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .section-heading { grid-template-columns: 58px minmax(0, 1fr); }
  .section-intro { grid-column: 2; }
  .overview-grid, .chart-grid, .two-column { grid-template-columns: 1fr; }
  .warning-layout { grid-template-columns: 1fr; }
  .evidence-spine { border-top: 1px solid var(--line); border-left: 0; }
  .indicator-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .report-nav ol { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}

@media (max-width: 560px) {
  body { font-size: 14px; }
  .masthead, .header-facts, .version-strip, .report-nav__inner, main, .report-footer { width: min(calc(100% - 1.4rem), var(--content)); }
  .masthead { padding-top: 2rem; }
  .report-title { font-size: clamp(3rem, 18vw, 5rem); }
  .header-facts { grid-template-columns: 1fr; }
  .report-nav__inner { width: 100%; padding-left: .7rem; }
  .report-nav { position: static; }
  .report-nav__inner { grid-template-columns: 1fr; padding: 0 .7rem; }
  .report-nav ol { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .report-nav a {
    min-height: 2.45rem;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .report-nav .control-button { margin: 0 0 .55rem; justify-self: start; }
  .report-section { padding: 2.6rem 0; }
  .section-heading { grid-template-columns: 1fr; gap: .8rem; }
  .section-intro { grid-column: 1; }
  .section-title { font-size: 2.2rem; }
  .section-number { padding-top: 0; }
  .overview-grid { gap: 1rem; }
  .executive-copy { padding: 1.25rem; }
  .limitation-callout { grid-template-columns: 1fr; gap: .5rem; }
  .warning-header { align-items: flex-start; flex-direction: column; }
  .severity-badge { align-self: flex-start; }
  .warning-content { padding: 1.1rem; }
  .estimate-value { font-size: 3.35rem; }
  .metric-grid, .warning-reading, .indicator-grid { grid-template-columns: 1fr; }
  .evidence-spine { padding-left: 2.25rem; }
  .definition-list > div { grid-template-columns: 1fr; gap: .25rem; }
  .report-footer { grid-template-columns: 1fr; }
}

@page { size: A4 landscape; margin: 10mm; }
@media print {
  html, body {
    width: auto !important;
    min-width: 0 !important;
    overflow: visible !important;
    background: var(--page) !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  body::before { position: absolute; }
  .screen-only, .js-only, .report-nav, .skip-link { display: none !important; }
  .masthead, .header-facts, .version-strip, main, .report-footer { width: 100%; }
  .masthead { padding-top: 0; }
  .report-title { font-size: 54pt; }
  .report-section { padding: 9mm 0; animation: none !important; break-before: auto; }
  .section-heading { margin-bottom: 5mm; }
  .section-title { font-size: 25pt; }
  .warning-card, .chart-panel, .analysis-panel, .indicator-panel, .empty-state, .limitation-callout { break-inside: avoid; box-shadow: none; }
  .warning-content { padding: 5mm; }
  .chart-grid, .two-column { gap: 4mm; }
  .chart-wrap { padding: 2mm; }
  .table-region { overflow: visible; border-color: var(--line-strong); }
  table, .matrix-table, .provenance-table { min-width: 0 !important; font-size: 7.2pt; }
  th, td { padding: 2mm; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
  details > * { display: block !important; }
  details > summary { display: none !important; }
  a { color: var(--ink); text-decoration: underline; }
  .source-link { max-width: none; word-break: break-all; }
  .report-footer { break-before: auto; border-top: 1px solid var(--line); }
}
"""

_SCRIPT = r"""
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  var printButton = document.getElementById("print-report");
  if (printButton) {
    printButton.addEventListener("click", function () { window.print(); });
  }

  document.querySelectorAll("table[data-sortable]").forEach(function (table) {
    table.querySelectorAll("thead th").forEach(function (heading, columnIndex) {
      if (heading.hasAttribute("data-no-sort")) { return; }
      var label = heading.textContent || "Column";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "sort-button screen-only";
      button.textContent = label;
      button.setAttribute("aria-label", "Sort by " + label);
      heading.textContent = "";
      heading.appendChild(button);
      button.addEventListener("click", function () {
        var body = table.tBodies[0];
        if (!body) { return; }
        var ascending = button.getAttribute("aria-sort") !== "ascending";
        table.querySelectorAll(".sort-button").forEach(function (other) {
          other.removeAttribute("aria-sort");
        });
        button.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var aText = (a.cells[columnIndex] || {}).textContent || "";
          var bText = (b.cells[columnIndex] || {}).textContent || "";
          var aNumber = Number(aText.replace(/[^0-9.+-]/g, ""));
          var bNumber = Number(bText.replace(/[^0-9.+-]/g, ""));
          var comparison = Number.isFinite(aNumber) && Number.isFinite(bNumber)
            ? aNumber - bNumber
            : aText.localeCompare(bText, undefined, {numeric: true});
          return ascending ? comparison : -comparison;
        });
        rows.forEach(function (row) { body.appendChild(row); });
      });
    });
  });
}());
"""


@dataclass(frozen=True)
class _Estimate:
    label: str
    display: str
    ratio: float | None
    is_probability: bool


@dataclass(frozen=True)
class _Severity:
    key: str
    label: str
    symbol: str


def _text(value: object, *, fallback: str = "Not available") -> str:
    if value is None or value == "":
        return fallback
    return escape(str(value), quote=True)


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
    if number < 0 or number > 1:
        return None
    return number


def _first(mapping: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _coalesce(*values: object) -> object | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "validated", "acceptable"}


def _format_percent(value: object, *, signed: bool = False) -> str:
    ratio = _ratio(value)
    if ratio is None:
        return "Not available"
    prefix = "+" if signed and ratio > 0 else ""
    return f"{prefix}{ratio * 100:.1f}%"


def _format_change(value: object) -> str:
    number = _number(value)
    if number is None:
        return "Not available"
    if abs(number) <= 1:
        number *= 100
    return f"{number:+.1f} pp"


def _format_signed_percent(value: object) -> str:
    number = _number(value)
    if number is None:
        return "Not available"
    if abs(number) <= 1:
        number *= 100
    return f"{number:+.1f}%"


def _format_percentile(value: object) -> str:
    number = _number(value)
    if number is None:
        return "Not available"
    if 0 <= number <= 1:
        number *= 100
    return f"{number:.1f} percentile"


def _format_confidence(value: object) -> str:
    number = _number(value)
    if number is not None and 0 <= number <= 1:
        return f"{number * 100:.1f}%"
    return "Not available" if value in (None, "") else str(value)


def _format_ratio(value: object) -> str:
    number = _number(value)
    return "Not available" if number is None else f"{number:.1f}×"


def _format_number(value: object, *, suffix: str = "", decimals: int = 1) -> str:
    number = _number(value)
    if number is None:
        return "Not available"
    return f"{number:,.{decimals}f}{suffix}"


def _normal_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _hazard_key(value: object) -> str:
    token = _normal_token(value)
    aliases = {
        "fx": "currency-bop",
        "bank": "banking",
        "sov": "sovereign",
        "mon": "inflation",
        "pol": "political",
        "coup": "coup",
        "civ": "internal-conflict",
        "war": "interstate-conflict",
    }
    if token in aliases:
        return aliases[token]
    if "currency" in token or "balance-of-payments" in token or token in {"fx", "bop"}:
        return "currency-bop"
    if "bank" in token:
        return "banking"
    if "sovereign" in token or "default" in token or "debt" in token:
        return "sovereign"
    if "inflation" in token or "monetary" in token:
        return "inflation"
    if "coup" in token or "unconstitutional" in token:
        return "coup"
    if "interstate" in token or "international-conflict" in token:
        return "interstate-conflict"
    if "internal" in token and ("conflict" in token or "armed" in token):
        return "internal-conflict"
    if "political" in token or "instability" in token:
        return "political"
    return token or "unspecified-hazard"


def _hazard_label(value: object) -> str:
    key = _hazard_key(value)
    for canonical_key, label in _CANONICAL_HAZARDS:
        if key == canonical_key:
            return label
    raw = str(value or "Unspecified hazard").replace("_", " ").replace("-", " ").strip()
    return raw[:1].upper() + raw[1:]


def _looks_like_hazard(value: object) -> bool:
    token = _normal_token(value)
    key = _hazard_key(token)
    canonical = {item[0] for item in _CANONICAL_HAZARDS}
    words = {"crisis", "conflict", "coup", "banking", "sovereign", "inflation", "political"}
    return key in canonical or any(word in token for word in words)


def _looks_like_horizon(value: object) -> bool:
    token = str(value or "").strip().lower()
    return bool(re.search(r"\b\d+\s*(d|day|days|m|month|months|y|year|years)\b", token))


def _horizon_label(value: object) -> str:
    raw = str(value or "Not available").strip()
    match = re.fullmatch(r"(\d+)\s*d", raw.lower())
    if match:
        return f"{match.group(1)} days"
    match = re.fullmatch(r"(\d+)\s*m", raw.lower())
    if match:
        return f"{match.group(1)} months"
    match = re.fullmatch(r"(\d+)\s*y", raw.lower())
    if match:
        return f"{match.group(1)} years"
    return raw


def _horizon_days(value: object) -> float:
    raw = str(value or "").strip().lower()
    number_match = re.search(r"\d+(?:\.\d+)?", raw)
    if not number_match:
        return float("inf")
    number = float(number_match.group())
    if "year" in raw or re.fullmatch(r"\d+\s*y", raw):
        return number * 365.25
    if "month" in raw or re.fullmatch(r"\d+\s*m", raw):
        return number * 30.4375
    return number


def _records(value: object, *, record_keys: set[str]) -> list[dict[str, object]]:
    """Flatten common list/keyed-map payload variants without mutating the input."""

    output: list[dict[str, object]] = []

    def walk(node: object, path: tuple[str, ...] = ()) -> None:
        if isinstance(node, Mapping):
            keys = {str(key) for key in node}
            if keys & record_keys:
                record = {str(key): item for key, item in node.items()}
                for part in path:
                    if _looks_like_horizon(part) and "horizon" not in record:
                        record["horizon"] = part
                    elif _looks_like_hazard(part) and "hazard" not in record:
                        record["hazard"] = part
                    elif "country" not in record and not _looks_like_horizon(part):
                        record["country"] = part
                output.append(record)
                return
            for key, item in node.items():
                walk(item, path + (str(key),))
            return
        for item in _sequence(node):
            walk(item, path)

    walk(value)
    return output


def _forecast_records(report: Mapping[str, object]) -> list[dict[str, object]]:
    records = _records(
        report.get("forecasts"),
        record_keys={
            "hazard",
            "hazard_type",
            "horizon",
            "forecast_horizon",
            "raw_probability",
            "raw_estimate",
            "calibrated_probability",
            "risk_estimate",
            "risk_index",
        },
    )
    return records


def _alert_records(report: Mapping[str, object]) -> list[dict[str, object]]:
    return _records(
        report.get("alerts"),
        record_keys={"severity", "alert_level", "level", "hazard", "hazard_type", "active"},
    )


def _country_names(report: Mapping[str, object]) -> list[str]:
    countries = report.get("countries")
    names: list[str] = []
    if isinstance(countries, str):
        names.append(countries)
    elif isinstance(countries, Mapping):
        if set(countries) & {"name", "country", "country_name", "iso3", "code"}:
            names.append(str(_first(countries, "name", "country", "country_name", "iso3", "code")))
        else:
            for key, value in countries.items():
                item = _mapping(value)
                names.append(str(_first(item, "name", "country", "country_name", "iso3") or key))
    else:
        for country in _sequence(countries):
            item = _mapping(country)
            names.append(str(_first(item, "name", "country", "country_name", "iso3", "code") or country))
    cleaned = [name for name in names if name and name != "None"]
    return list(dict.fromkeys(cleaned))


def _calibration_allowed(report: Mapping[str, object], forecast: Mapping[str, object]) -> bool:
    analysis = _mapping(report.get("analysis"))
    mode = str(_first(analysis, "report_mode", "mode") or report.get("report_mode") or "").lower()
    if "uncalibrated" in mode:
        return False

    calibration = _mapping(report.get("calibration"))
    validation = _mapping(report.get("validation"))
    calibrated_status = str(
        _first(forecast, "calibration_status", "calibration_state")
        or _first(calibration, "status", "calibration_status")
        or ""
    ).strip().lower()
    calibrated_claim = (
        _truthy(_first(forecast, "calibrated", "is_calibrated"))
        or "calibrated_probability" in forecast
        or calibrated_status in {"calibrated", "validated", "acceptable", "passed"}
    )
    validated_status = str(
        _first(forecast, "validation_status")
        or _first(calibration, "validation_status", "status")
        or _first(validation, "calibration_status", "status")
        or ""
    ).strip().lower()
    validated_claim = (
        _truthy(_first(forecast, "calibration_validated", "validated", "is_validated"))
        or _truthy(_first(calibration, "validated", "calibration_validated"))
        or _truthy(_first(validation, "calibration_validated", "validated"))
        or validated_status in {"validated", "acceptable", "passed"}
    )
    return calibrated_claim and validated_claim


def _domain_status(value: object) -> tuple[str, bool]:
    """Return an auditable domain label and whether it is a confirmed OOD finding."""

    token = _normal_token(value)
    if token in {"model-out-of-domain", "out-of-domain", "ood"}:
        return "Model out of domain", True
    if token in {"in-domain", "indomain", "ok"}:
        return "In domain", False
    if token in {"not-assessed", "unassessed", "unknown", "none", ""}:
        return "Domain not assessed", False
    if token in {"near-boundary", "boundary", "near-domain-boundary"}:
        return "Near model-domain boundary", False
    return str(value), False


def _momentum_change(item: Mapping[str, object], horizon: str = "30d") -> object | None:
    direct_keys = {
        "7d": ("change_7d", "seven_day"),
        "30d": ("change_30d", "probability_change", "momentum_30d", "change"),
        "90d": ("change_90d", "ninety_day"),
        "12m": ("change_12m", "twelve_month"),
    }
    direct = _first(item, *direct_keys.get(horizon, ("change",)))
    if direct not in (None, ""):
        return direct
    momentum = _mapping(_first(item, "momentum", "risk_momentum"))
    aliases = {
        "7d": ("7d", "seven_day", "change_7d"),
        "30d": ("30d", "thirty_day", "change_30d"),
        "90d": ("90d", "ninety_day", "change_90d"),
        "12m": ("12m", "twelve_month", "change_12m"),
    }
    return _first(momentum, *aliases.get(horizon, (horizon,)))


def _evidence_alerts(item: Mapping[str, object]) -> str | None:
    raw = _first(item, "evidence_alerts", "evidence_warning", "data_warning")
    values = [str(value) for value in _sequence(raw) if value not in (None, "")]
    if values:
        return " · ".join(values)
    if raw not in (None, ""):
        return str(raw)
    return None


def _estimate(report: Mapping[str, object], forecast: Mapping[str, object]) -> _Estimate:
    if _calibration_allowed(report, forecast):
        value = _first(forecast, "calibrated_probability", "probability")
        ratio = _ratio(value)
        if ratio is not None:
            return _Estimate(
                label="Validated probability",
                display=_format_percent(value),
                ratio=ratio,
                is_probability=True,
            )
    index = _first(forecast, "risk_index", "score")
    raw = _first(
        forecast,
        "risk_estimate",
        "raw_estimate",
        "raw_probability",
        "probability",
        "calibrated_probability",
    )
    if raw not in (None, ""):
        ratio = _ratio(raw)
        return _Estimate(
            label="Uncalibrated risk estimate",
            display=_format_percent(raw),
            ratio=ratio,
            is_probability=False,
        )
    number = _number(index)
    if number is None:
        return _Estimate("Risk estimate", "Not available", None, False)
    ratio = number / 100 if 1 < number <= 100 else number if 0 <= number <= 1 else None
    display = f"{number:.1f} / 100" if number > 1 else f"{number:.3f} index"
    return _Estimate("Risk index", display, ratio, False)


def _severity(report: Mapping[str, object], item: Mapping[str, object]) -> _Severity:
    _, is_out_of_domain = _domain_status(_first(item, "ood_status", "domain_status"))
    if is_out_of_domain:
        return _Severity("out-of-domain", "Model out of domain", "▧")
    evidence = str(_first(item, "evidence_status", "data_status") or "").strip().lower()
    confidence = str(_first(item, "confidence", "evidence_confidence") or "").strip().lower()
    if "insufficient" in evidence or confidence in {"insufficient", "none", "unusable"}:
        return _Severity("insufficient", "Insufficient evidence", "…")

    raw = str(_first(item, "severity", "alert_level", "level", "status") or "watch")
    key = _normal_token(raw)
    allowed = _calibration_allowed(report, item)
    if key in {"no-alert", "none", "normal"}:
        if not allowed:
            return _Severity(
                "low",
                "No operational alert — uncalibrated",
                "○",
            )
        return _Severity("low", "No alert", "○")
    if "critical" in key:
        key = "critical"
    elif "high" in key:
        key = "high"
    elif "elevated" in key:
        key = "elevated"
    elif "low" in key:
        key = "low"
    elif "insufficient" in key:
        key = "insufficient"
    else:
        key = "watch"

    if not allowed and _SEVERITY_RANK.get(key, 1) > _SEVERITY_RANK["watch"]:
        return _Severity("watch-uncalibrated", "Watch — uncalibrated", "◇")
    labels = {
        "low": ("Low", "○"),
        "watch": ("Watch", "◇"),
        "elevated": ("Elevated", "△"),
        "high": ("High", "▲"),
        "critical": ("Critical", "■"),
        "insufficient": ("Insufficient evidence", "…"),
    }
    label, symbol = labels[key]
    if not allowed and key == "watch":
        return _Severity("watch-uncalibrated", "Watch — uncalibrated", "◇")
    return _Severity(key, label, symbol)


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, set | frozenset):
        return sorted(value, key=str)
    return str(value)


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set | frozenset):
        return [_json_safe(item) for item in sorted(value, key=str)]
    if isinstance(value, (date, datetime, Decimal)):
        return _json_default(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return _json_default(value)


def _embedded_json(report: Mapping[str, object]) -> str:
    payload = json.dumps(
        _json_safe(report),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _section_heading(number: str, title: str, intro: str) -> str:
    return (
        '<header class="section-heading">'
        f'<span class="section-number" aria-hidden="true">{_text(number)}</span>'
        f'<div><h2 class="section-title">{_text(title)}</h2><div class="section-rule"></div></div>'
        f'<p class="section-intro">{_text(intro)}</p>'
        "</header>"
    )


def _empty_state(title: str, body: str) -> str:
    return (
        '<div class="empty-state" role="status">'
        f'<h3>{_text(title)}</h3><p>{_text(body)}</p></div>'
    )


def _table_region(table: str, *, label: str) -> str:
    return (
        f'<div class="table-region" role="region" aria-label="{_text(label)}" tabindex="0">'
        f"{table}</div>"
    )


def _safe_source_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return '<span class="unsafe-url">Not available</span>'
    parsed = urlsplit(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        safe = _text(raw)
        return f'<a class="source-link" href="{safe}" rel="noopener noreferrer">{safe}</a>'
    return (
        f'<span class="unsafe-url" title="Unsupported URL scheme">{_text(raw)} '
        "(link disabled)</span>"
    )


def _report_validated(report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]) -> bool:
    return bool(forecasts) and all(_calibration_allowed(report, forecast) for forecast in forecasts)


def _render_header(report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]) -> str:
    analysis = _mapping(report.get("analysis"))
    countries = _country_names(report)
    country_label = ", ".join(countries) if countries else "Country set not supplied"
    analysis_date = _first(analysis, "analysis_date", "as_of", "date")
    generated_date = _first(analysis, "generated_at", "report_generated_at", "generated_date")
    validated = _report_validated(report, forecasts)
    supplied_mode = _first(analysis, "report_mode", "mode") or report.get("report_mode")
    if validated:
        mode = str(supplied_mode or "RESEARCH / VALIDATED")
    else:
        mode = "RESEARCH / UNCALIBRATED"
    mode_note = (
        "Numerical probabilities are shown only where calibration and validation are explicitly attested."
        if validated
        else "Operational severity is capped at WATCH where calibration is not explicitly validated."
    )
    versions = (
        ("Schema", report.get("schema_version")),
        ("Model", report.get("model_version")),
        ("Method", report.get("methodology_version")),
        ("Calibration", report.get("calibration_version")),
        ("Alert policy", report.get("alert_policy_version")),
    )
    chips = "".join(
        f'<span class="version-chip"><span>{_text(label)}</span><b>{_text(value)}</b></span>'
        for label, value in versions
    )
    return f"""
    <header class="report-header" role="banner">
      <div class="masthead">
        <div>
          <span class="institution-mark">Forecast · evidence · audit</span>
          <h1 class="report-title">FX<span class="dash">—</span>CPM</h1>
          <p class="report-deck">Foreign-exchange-informed, multi-hazard crisis early warning.
          A research instrument for calibrated vigilance, not a declaration that a crisis will occur.</p>
        </div>
        <aside class="mode-block" data-validated="{str(validated).lower()}" aria-label="Report mode">
          <span class="kicker">Report mode</span>
          <p class="mode-value">{_text(mode)}</p>
          <p class="mode-note">{_text(mode_note)}</p>
        </aside>
      </div>
      <div class="header-facts" aria-label="Report scope and dates">
        <div class="header-fact"><span class="kicker">Countries / scope</span><strong>{_text(country_label)}</strong></div>
        <div class="header-fact"><span class="kicker">Analysis date</span><strong>{_text(analysis_date)}</strong></div>
        <div class="header-fact"><span class="kicker">Generated</span><strong>{_text(generated_date)}</strong></div>
        <div class="header-fact"><span class="kicker">Forecast records</span><strong>{len(forecasts)}</strong></div>
      </div>
      <div class="version-strip" aria-label="Report versions">{chips}</div>
    </header>
    """


def _render_navigation() -> str:
    links = (
        ("01", "Overview", "overview"),
        ("02", "Warnings", "warnings"),
        ("03", "Hazard matrix", "hazard-matrix"),
        ("04", "Term structure", "term-structure"),
        ("05", "FX stress", "fx-stress"),
        ("06", "Vulnerability", "vulnerability"),
        ("07", "History", "history"),
        ("08", "Analogues", "analogues"),
        ("09", "Contributors", "contributors"),
        ("10", "Contagion", "contagion"),
        ("11", "Calibration", "calibration"),
        ("12", "Data quality", "data-quality"),
        ("13", "Method", "methodology"),
        ("14", "Sources", "sources"),
        ("15", "Limits", "limitations"),
    )
    items = "".join(
        f'<li><a href="#{anchor}"><span aria-hidden="true">{number} / </span>{label}</a></li>'
        for number, label, anchor in links
    )
    return f"""
    <nav class="report-nav screen-only" aria-label="Report sections">
      <div class="report-nav__inner">
        <ol>{items}</ol>
        <button class="control-button js-only" type="button" id="print-report"
          aria-label="Print or save this report as PDF">Print / PDF</button>
      </div>
    </nav>
    """


def _forecast_sort_value(report: Mapping[str, object], forecast: Mapping[str, object]) -> float:
    estimate = _estimate(report, forecast)
    return estimate.ratio if estimate.ratio is not None else -1


def _limitation_text(report: Mapping[str, object]) -> str:
    analysis = _mapping(report.get("analysis"))
    major = _first(analysis, "major_limitation", "primary_limitation")
    if major not in (None, ""):
        return str(major)
    limitations = report.get("limitations")
    if isinstance(limitations, Mapping):
        first_value = next(iter(limitations.values()), None)
        if isinstance(first_value, Mapping):
            return str(_first(first_value, "text", "description", "limitation") or first_value)
        if first_value not in (None, ""):
            return str(first_value)
    for item in _sequence(limitations):
        mapping = _mapping(item)
        return str(_first(mapping, "text", "description", "limitation") or item)
    if isinstance(limitations, str) and limitations:
        return limitations
    return "No explicit limitations were supplied; the evidence audit is incomplete and should not be treated as assurance."


def _fx_summary(report: Mapping[str, object]) -> str:
    stress = report.get("fx_stress")
    records = _panel_records(
        stress,
        record_keys={"emp", "fx_stress_percentile", "residual_stress", "abnormal_fx_return", "regime"},
    )
    if not records:
        return "FX stress evidence not available"
    item = records[0]
    percentile = _first(item, "fx_stress_percentile", "stress_percentile", "percentile")
    emp = _first(item, "emp", "exchange_market_pressure")
    residual = _first(item, "residual_stress", "abnormal_fx_return", "fx_residual")
    if percentile not in (None, ""):
        number = _number(percentile)
        if number is not None and number <= 1:
            number *= 100
        return f"FX stress {_format_percentile(number)}"
    if emp not in (None, ""):
        return f"EMP {_format_number(emp)}"
    if residual not in (None, ""):
        return f"Residual stress {_format_number(residual)}"
    return "FX stress indicators incomplete"


def _render_overview(report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]) -> str:
    analysis = _mapping(report.get("analysis"))
    ordered = sorted(forecasts, key=lambda item: _forecast_sort_value(report, item), reverse=True)
    top = ordered[0] if ordered else {}
    estimate = _estimate(report, top)
    hazard = _hazard_label(_first(top, "hazard", "hazard_type"))
    horizon = _horizon_label(_first(top, "horizon", "forecast_horizon"))
    country = _first(top, "country", "country_name")
    baseline = _first(top, "base_rate", "baseline_probability", "baseline")
    change = _momentum_change(top)
    supplied_narrative = _first(analysis, "executive_summary", "summary", "narrative")
    if supplied_narrative not in (None, ""):
        lead = str(supplied_narrative)
    elif top:
        scope = f" for {country}" if country not in (None, "") else ""
        lead = (
            f"The most elevated available signal{scope} is {hazard.lower()} over {horizon}: "
            f"{estimate.label.lower()} {estimate.display}."
        )
    else:
        lead = (
            "No assessable numerical forecast was supplied. This absence is an evidence limitation, "
            "not evidence of low economic or geopolitical risk."
        )
    comparison = (
        f"{_format_percent(baseline)} historical baseline"
        if baseline not in (None, "")
        else "Historical baseline not available"
    )
    direction = _format_change(change)
    confidence = _first(top, "confidence", "evidence_confidence")
    calibration = "Validated" if top and _calibration_allowed(report, top) else "Uncalibrated / not validated"
    limitation = _limitation_text(report)
    return f"""
    <section class="report-section" id="overview" aria-labelledby="overview-title">
      {_section_heading("01", "Executive crisis overview", "A disciplined reading order: estimate, historical comparison, direction, evidence quality, then limitations.").replace('<h2 class="section-title">', '<h2 class="section-title" id="overview-title">', 1)}
      <div class="overview-grid">
        <article class="executive-copy">
          <span class="kicker">Structured assessment</span>
          <p class="lead">{_text(lead)}</p>
          <p>Relative to the available benchmark: <strong>{_text(comparison)}</strong>. Recent direction:
          <strong>{_text(direction)}</strong>. Evidence confidence is
          <strong>{_text(_format_confidence(confidence))}</strong>; calibration state is <strong>{_text(calibration)}</strong>.</p>
          <p class="caution-statement"><strong>Caution.</strong> Forecasts are probabilistic early-warning
          signals. They do not declare that a crisis will occur, establish causation, or reveal private intentions.</p>
        </article>
        <dl class="overview-ledger">
          <div><dt>Most elevated available hazard</dt><dd>{_text(hazard if top else None)}</dd></div>
          <div><dt>Primary horizon</dt><dd>{_text(horizon if top else None)}</dd></div>
          <div><dt>Largest disclosed deterioration</dt><dd>{_text(direction)}</dd></div>
          <div><dt>Strongest available FX signal</dt><dd>{_text(_fx_summary(report))}</dd></div>
        </dl>
        <aside class="limitation-callout" aria-label="Most important limitation">
          <strong>Most important limitation</strong><p>{_text(limitation)}</p>
        </aside>
      </div>
    </section>
    """


def _forecast_key(record: Mapping[str, object]) -> tuple[str, str, str]:
    country = _normal_token(_first(record, "country", "country_name"))
    hazard = _hazard_key(_first(record, "hazard", "hazard_type"))
    horizon = _normal_token(_horizon_label(_first(record, "horizon", "forecast_horizon")))
    return country, hazard, horizon


def _warning_records(
    report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    index = {_forecast_key(record): dict(record) for record in forecasts}
    alerts = [item for item in _alert_records(report) if item.get("active") is not False]
    merged: list[dict[str, object]] = []
    for alert in alerts:
        base = index.get(_forecast_key(alert), {})
        base.update(alert)
        merged.append(base)
    if not merged:
        merged = [
            dict(item)
            for item in sorted(
                forecasts,
                key=lambda record: _forecast_sort_value(report, record),
                reverse=True,
            )[:4]
        ]
    return merged


def _contributor_label(item: Mapping[str, object]) -> str:
    return str(_first(item, "name", "feature", "label", "indicator") or "Not available")


def _warning_card(report: Mapping[str, object], item: Mapping[str, object], index: int) -> str:
    hazard_raw = _first(item, "hazard", "hazard_type")
    hazard = _hazard_label(hazard_raw)
    country = _first(item, "country", "country_name")
    horizon = _horizon_label(_first(item, "horizon", "forecast_horizon"))
    estimate = _estimate(report, item)
    severity = _severity(report, item)
    baseline = _first(item, "base_rate", "baseline_probability", "baseline")
    relative = _first(item, "relative_risk", "relative")
    change = _momentum_change(item)
    confidence = _first(item, "confidence", "evidence_confidence")
    percentile = _first(item, "historical_percentile", "percentile")
    model_tier = _first(item, "model_tier", "tier")
    domain_label, _ = _domain_status(_first(item, "ood_status", "domain_status"))
    calibration_state = (
        "Validated calibration"
        if _calibration_allowed(report, item)
        else "Uncalibrated or validation not attested"
    )
    raw_contributors = _sequence(_first(item, "contributors", "predictive_contributors"))
    first_contributor = _mapping(raw_contributors[0]) if raw_contributors else {}
    reason = _first(item, "key_reason", "reason", "key_contributor") or (
        _contributor_label(first_contributor) if first_contributor else None
    )
    caveat = _first(item, "caveat", "evidence_caveat", "warning") or _limitation_text(report)
    scope = " · ".join(str(value) for value in (country, horizon) if value not in (None, ""))
    operational_note = ""
    requested = str(_first(item, "severity", "alert_level", "level") or "").upper()
    if severity.key == "watch-uncalibrated" and requested not in {"", "WATCH"}:
        operational_note = f"Requested {requested}; display capped by uncalibrated-output policy."
    evidence_warning = _evidence_alerts(item) or operational_note
    spine = (
        (estimate.label, estimate.display),
        ("Historical base rate", _format_percent(baseline)),
        ("Evidence confidence", _format_confidence(confidence)),
        ("Data coverage", _format_percent(_first(item, "coverage", "data_coverage"))),
        ("Calibration", calibration_state),
        ("Model tier", str(model_tier or "Not available")),
        ("Domain status", domain_label),
        ("Evidence warning", str(evidence_warning or "No specific warning supplied")),
    )
    spine_items = "".join(
        f'<li><span class="spine-key">{_text(label)}</span><span class="spine-value">{_text(value)}</span></li>'
        for label, value in spine
    )
    return f"""
    <article class="warning-card" data-risk="{severity.key}" aria-labelledby="warning-{index}-title">
      <header class="warning-header">
        <div class="hazard-label">
          {hazard_icon_svg(hazard_raw)}
          <div><h3 id="warning-{index}-title">{_text(hazard)}</h3><p>{_text(scope)}</p></div>
        </div>
        <span class="severity-badge" data-risk="{severity.key}"
          data-operational-level="{'WATCH_UNCALIBRATED' if severity.key == 'watch-uncalibrated' else severity.key.upper()}">
          <span class="severity-symbol" aria-hidden="true">{severity.symbol}</span>{_text(severity.label)}
          {'<span class="sr-only"> (WATCH_UNCALIBRATED)</span>' if severity.key == 'watch-uncalibrated' else ''}
        </span>
      </header>
      <div class="warning-layout">
        <div class="warning-content">
          <div class="estimate-row">
            <div class="estimate-block"><span class="estimate-value">{_text(estimate.display)}</span>
              <span class="estimate-label">{_text(estimate.label)}</span></div>
            <dl class="metric-grid">
              <div><dt>Historical base rate</dt><dd>{_text(_format_percent(baseline))}</dd></div>
              <div><dt>Relative risk</dt><dd>{_text(_format_ratio(relative))}</dd></div>
              <div><dt>30-day momentum</dt><dd>{_text(_format_change(change))}</dd></div>
              <div><dt>Historical percentile</dt><dd>{_text(_format_percentile(percentile))}</dd></div>
            </dl>
          </div>
          <div class="warning-reading">
            <div class="reading-note"><h4>Key predictive contributor</h4><p>{_text(reason)}</p></div>
            <div class="reading-note"><h4>Caveat / contrary evidence</h4><p>{_text(caveat)}</p></div>
          </div>
        </div>
        <aside class="evidence-spine" aria-label="Evidence spine for {_text(hazard)}">
          <h4>Evidence spine</h4><ol>{spine_items}</ol>
        </aside>
      </div>
    </article>
    """


def _render_warnings(report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]) -> str:
    warnings = _warning_records(report, forecasts)
    body = (
        '<div class="warning-stack">'
        + "".join(_warning_card(report, item, index) for index, item in enumerate(warnings, 1))
        + "</div>"
        if warnings
        else _empty_state(
            "No assessable warning records",
            "No active alerts or forecast estimates were supplied. This is insufficient evidence, not a low-risk assessment.",
        )
    )
    heading = _section_heading(
        "02",
        "Active warning center",
        "Risk magnitude and evidence quality stay connected through the vertical evidence spine. Text, symbol, and border pattern repeat every severity state.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="warnings-title">', 1)
    return f'<section class="report-section" id="warnings" aria-labelledby="warnings-title">{heading}{body}</section>'


def _hazard_definitions(report: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    hazards = report.get("hazards")
    if isinstance(hazards, Mapping):
        if set(hazards) & {"hazard", "hazard_type", "name", "supported_horizons"}:
            key = _hazard_key(_first(hazards, "hazard", "hazard_type", "name"))
            result[key] = hazards
        else:
            for key, value in hazards.items():
                result[_hazard_key(key)] = _mapping(value)
    else:
        for value in _sequence(hazards):
            item = _mapping(value)
            result[_hazard_key(_first(item, "hazard", "hazard_type", "name") or value)] = item
    return result


def _matrix_hazards(forecasts: Sequence[Mapping[str, object]]) -> list[tuple[str, str]]:
    hazards = list(_CANONICAL_HAZARDS)
    known = {key for key, _ in hazards}
    for forecast in forecasts:
        raw = _first(forecast, "hazard", "hazard_type")
        key = _hazard_key(raw)
        if key not in known:
            hazards.append((key, _hazard_label(raw)))
            known.add(key)
    return hazards


def _matrix_horizons(
    forecasts: Sequence[Mapping[str, object]], definitions: Mapping[str, Mapping[str, object]]
) -> list[str]:
    values: list[str] = []
    for forecast in forecasts:
        horizon = _first(forecast, "horizon", "forecast_horizon")
        if horizon not in (None, ""):
            values.append(_horizon_label(horizon))
    for definition in definitions.values():
        for horizon in _sequence(_first(definition, "supported_horizons", "horizons")):
            values.append(_horizon_label(horizon))
    if not values:
        values.extend(_DEFAULT_HORIZONS)
    return sorted(dict.fromkeys(values), key=_horizon_days)


def _render_matrix(report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]) -> str:
    definitions = _hazard_definitions(report)
    horizons = _matrix_horizons(forecasts, definitions)
    index = {
        (_hazard_key(_first(item, "hazard", "hazard_type")), _normal_token(_horizon_label(_first(item, "horizon", "forecast_horizon")))): item
        for item in forecasts
    }
    header = "".join(f'<th scope="col">{_text(horizon)}</th>' for horizon in horizons)
    rows: list[str] = []
    for key, label in _matrix_hazards(forecasts):
        definition = definitions.get(key, {})
        supported_raw = _sequence(_first(definition, "supported_horizons", "horizons"))
        supported = {_normal_token(_horizon_label(value)) for value in supported_raw}
        cells: list[str] = []
        for horizon in horizons:
            forecast = index.get((key, _normal_token(horizon)))
            if forecast:
                estimate = _estimate(report, forecast)
                severity = _severity(report, forecast)
                change = _momentum_change(forecast)
                confidence = _first(forecast, "confidence", "evidence_confidence")
                cells.append(
                    f'<td class="matrix-cell" data-risk="{severity.key}">'
                    f'<span class="cell-estimate">{_text(estimate.display)}</span>'
                    f'<span class="cell-status">{_text(estimate.label)} · {_text(_format_confidence(confidence))}</span>'
                    f'<span class="cell-change">{_text(_format_change(change))} · {_text(severity.label)}</span></td>'
                )
            elif supported and _normal_token(horizon) not in supported:
                cells.append(
                    '<td class="matrix-cell unsupported"><span class="cell-estimate">—</span>'
                    '<span class="cell-status">Not supported for this hazard</span></td>'
                )
            else:
                cells.append(
                    '<td class="matrix-cell"><span class="cell-estimate">Not available</span>'
                    '<span class="cell-status">Evidence not supplied</span></td>'
                )
        rows.append(
            f'<tr><th scope="row">{hazard_icon_svg(label, size=20)} {_text(label)}</th>{"".join(cells)}</tr>'
        )
    table = (
        '<table class="matrix-table" data-sortable><caption>Eight hazard families across supported forecast horizons. '
        "Cumulative long-horizon estimates are not directly comparable with short-horizon estimates.</caption>"
        f'<thead><tr><th scope="col">Hazard family</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )
    heading = _section_heading(
        "03",
        "Multi-hazard horizon matrix",
        "Every missing cell remains visibly missing; unsupported horizons are distinguished from absent observations.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="matrix-title">', 1)
    return (
        '<section class="report-section" id="hazard-matrix" aria-labelledby="matrix-title">'
        f'{heading}{_table_region(table, label="Scrollable multi-hazard forecast matrix")}</section>'
    )


def _render_term_structure(
    report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]
) -> str:
    groups: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    labels: dict[str, str] = {}
    for forecast in forecasts:
        raw = _first(forecast, "hazard", "hazard_type")
        key = _hazard_key(raw)
        groups[key].append(forecast)
        labels[key] = _hazard_label(raw)
    panels: list[str] = []
    for index, (key, items) in enumerate(groups.items(), 1):
        ordered = sorted(items, key=lambda item: _horizon_days(_first(item, "horizon", "forecast_horizon")))
        normalized: list[dict[str, object]] = []
        for item in ordered:
            estimate = _estimate(report, item)
            if estimate.ratio is None:
                continue
            normalized.append(
                {
                    "horizon": _horizon_label(_first(item, "horizon", "forecast_horizon")),
                    "estimate": estimate.ratio,
                    "lower": _first(
                        item,
                        "lower",
                        "lower_bound",
                        "uncertainty_low",
                        "ci_low",
                        "p05",
                    ),
                    "upper": _first(
                        item,
                        "upper",
                        "upper_bound",
                        "uncertainty_high",
                        "ci_high",
                        "p95",
                    ),
                }
            )
        all_probability = bool(ordered) and all(_calibration_allowed(report, item) for item in ordered)
        value_label = "Validated probability" if all_probability else "Uncalibrated risk estimate"
        chart = term_structure_svg(
            normalized,
            title=f"{labels[key]} term structure",
            chart_id=f"term-{index}-{key}",
            value_keys=("estimate",),
            value_label=value_label,
        )
        table_rows: list[str] = []
        for item in ordered:
            estimate = _estimate(report, item)
            lower = _first(
                item,
                "lower",
                "lower_bound",
                "uncertainty_low",
                "ci_low",
                "p05",
            )
            upper = _first(
                item,
                "upper",
                "upper_bound",
                "uncertainty_high",
                "ci_high",
                "p95",
            )
            interval = (
                f"{_format_percent(lower)}–{_format_percent(upper)}"
                if lower not in (None, "") and upper not in (None, "")
                else "Not available"
            )
            table_rows.append(
                "<tr>"
                f'<th scope="row">{_text(_horizon_label(_first(item, "horizon", "forecast_horizon")))}</th>'
                f'<td>{_text(estimate.display)}</td><td>{_text(interval)}</td>'
                f'<td>{_text(_format_percent(_first(item, "base_rate", "baseline")))}</td>'
                f'<td>{_text(_format_confidence(_first(item, "confidence", "evidence_confidence")))}</td>'
                f'<td>{_text("Validated" if _calibration_allowed(report, item) else "Uncalibrated")}</td>'
                "</tr>"
            )
        data_table = (
            f'<table><caption>Text alternative for { _text(labels[key]) } term structure</caption>'
            "<thead><tr><th scope=\"col\">Horizon</th><th scope=\"col\">Estimate</th>"
            "<th scope=\"col\">Uncertainty interval</th><th scope=\"col\">Base rate</th>"
            "<th scope=\"col\">Confidence</th><th scope=\"col\">Calibration</th></tr></thead>"
            f'<tbody>{"".join(table_rows)}</tbody></table>'
        )
        panels.append(
            '<article class="chart-panel">'
            f'<header class="chart-panel__header"><h3>{_text(labels[key])}</h3>'
            f'<p>{_text(value_label)} across {len(ordered)} disclosed horizon(s)</p></header>'
            f'<div class="chart-wrap">{chart}</div>'
            f'<details class="chart-data" open><summary>Chart data and uncertainty</summary>'
            f'{_table_region(data_table, label=f"{labels[key]} term structure data")}</details>'
            '<p class="chart-note">Long-horizon cumulative estimates reflect longer exposure and should be '
            "compared with horizon-matched base rates.</p></article>"
        )
    body = (
        f'<div class="chart-grid">{"".join(panels)}</div>'
        if panels
        else _empty_state(
            "Term structure unavailable",
            "No horizon-specific forecast estimates were supplied. The report will not interpolate missing horizons.",
        )
    )
    heading = _section_heading(
        "04",
        "Probability / estimate term structure",
        "Axes, units, uncertainty and calibration labels are rendered into the document; scripting is not required.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="term-title">', 1)
    return f'<section class="report-section" id="term-structure" aria-labelledby="term-title">{heading}{body}</section>'


def _panel_records(value: object, *, record_keys: set[str]) -> list[dict[str, object]]:
    records = _records(value, record_keys=record_keys)
    if records:
        return records
    if isinstance(value, Mapping) and value:
        return [{str(key): item for key, item in value.items()}]
    return []


def _indicator(
    label: str,
    value: object,
    *,
    formatter: str = "text",
    note: str = "",
) -> str:
    if formatter == "percent":
        display = _format_percent(value)
    elif formatter == "signed_percent":
        display = _format_signed_percent(value)
    elif formatter == "change":
        display = _format_change(value)
    elif formatter == "number":
        display = _format_number(value)
    elif formatter == "percentile":
        display = _format_percentile(value)
    elif formatter == "quality":
        number = _number(value)
        display = _format_percent(number) if number is not None else (
            "Not available" if value in (None, "") else str(value)
        )
    else:
        display = "Not available" if value in (None, "") else str(value)
    missing = display == "Not available"
    return (
        f'<div class="indicator{" is-missing" if missing else ""}">'
        f'<span class="kicker">{_text(label)}</span><span class="indicator-value">{_text(display)}</span>'
        f'<span class="indicator-note">{_text(note or ("Explicitly missing" if missing else "Observed / supplied"))}</span></div>'
    )


def _named_measure(
    item: Mapping[str, object],
    *name_fragments: str,
) -> tuple[object | None, str]:
    for raw_measure in _sequence(_first(item, "measures", "indicators")):
        measure = _mapping(raw_measure)
        name = str(_first(measure, "name", "label", "indicator") or "")
        token = _normal_token(name)
        if any(_normal_token(fragment) in token for fragment in name_fragments):
            status = _first(measure, "status", "evidence_status")
            unit = _first(measure, "unit", "units")
            note = " · ".join(str(value) for value in (status, unit) if value not in (None, ""))
            return _first(measure, "value", "estimate", "score"), note
    return None, "Explicitly missing"


def _render_fx_stress(report: Mapping[str, object]) -> str:
    records = _panel_records(
        report.get("fx_stress"),
        record_keys={
            "country",
            "spot_return",
            "raw_fx_return",
            "abnormal_fx_return",
            "residual_stress",
            "realized_volatility",
            "emp",
            "reserve_pressure",
            "parallel_market_premium",
            "fx_stress_percentile",
            "regime",
        },
    )
    panels: list[str] = []
    for item in records:
        country = _first(item, "country", "country_name") or "Country not supplied"
        as_of = _first(item, "as_of", "date", "analysis_date") or _first(
            _mapping(report.get("analysis")),
            "analysis_date",
            "as_of",
        )
        status = _first(item, "status", "evidence_status") or "Evidence status not supplied"
        spot_nested, spot_note = _named_measure(item, "spot depreciation", "spot behavior")
        residual_nested, residual_note = _named_measure(
            item,
            "residual fx",
            "abnormal fx",
        )
        volatility_nested, volatility_note = _named_measure(
            item,
            "realized volatility",
            "fx volatility",
        )
        emp_nested, emp_note = _named_measure(item, "exchange market pressure")
        reserve_nested, reserve_note = _named_measure(item, "reserve pressure")
        parallel_nested, parallel_note = _named_measure(item, "parallel market premium")
        option_nested, option_note = _named_measure(item, "option", "forward")
        values = (
            (
                "Spot behavior",
                _coalesce(
                    _first(item, "spot_return", "raw_fx_return", "spot_change"),
                    spot_nested,
                ),
                "signed_percent",
                spot_note or "Raw market move",
            ),
            (
                "Residual FX stress",
                _coalesce(
                    _first(item, "residual_stress", "abnormal_fx_return", "fx_residual"),
                    residual_nested,
                ),
                "number",
                residual_note or "Global-factor adjusted",
            ),
            (
                "Realized volatility",
                _coalesce(
                    _first(item, "realized_volatility", "fx_volatility"),
                    volatility_nested,
                ),
                "signed_percent",
                volatility_note,
            ),
            (
                "Exchange-market pressure",
                _coalesce(_first(item, "emp", "exchange_market_pressure"), emp_nested),
                "number",
                emp_note or "EMP composite",
            ),
            (
                "Reserve pressure",
                _coalesce(_first(item, "reserve_pressure", "reserve_change"), reserve_nested),
                "number",
                reserve_note or "Reserve-side pressure",
            ),
            (
                "Parallel-market premium",
                _coalesce(
                    _first(item, "parallel_market_premium", "parallel_premium"),
                    parallel_nested,
                ),
                "percent",
                parallel_note or "Official / parallel-rate gap",
            ),
            ("Option / forward indicator", option_nested, "number", option_note),
            ("FX stress percentile", _first(item, "fx_stress_percentile", "stress_percentile", "percentile"), "percentile", "Historical distribution"),
            ("Currency regime", _first(item, "regime", "currency_regime", "regime_type"), "text", "Interpretation context"),
        )
        indicators = "".join(
            _indicator(label, value, formatter=formatter, note=note)
            for label, value, formatter, note in values
        )
        panels.append(
            '<article class="indicator-panel"><header class="indicator-head"><div>'
            f'<h3>{_text(country)}</h3><p>FX market stress · as of {_text(as_of)}</p></div>'
            f'<span class="status-label">{_text(status)}</span></header><div class="indicator-grid">'
            f"{indicators}</div></article>"
        )
    body = (
        "".join(panels)
        if panels
        else _empty_state(
            "FX stress observations unavailable",
            "Raw and residual FX stress, EMP, reserve pressure, parallel-market premium and regime were not supplied. Missing indicators are not treated as zero.",
        )
    )
    heading = _section_heading(
        "05",
        "FX market stress",
        "Observed spot pressure stays distinct from global-factor-adjusted residual stress and slow-moving reserve constraints.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="fx-title">', 1)
    return f'<section class="report-section" id="fx-stress" aria-labelledby="fx-title">{heading}{body}</section>'


def _render_vulnerability(report: Mapping[str, object]) -> str:
    records = _panel_records(
        report.get("macro_vulnerability"),
        record_keys={
            "country",
            "vulnerability_score",
            "credit",
            "credit_to_gdp",
            "sovereign",
            "reserves",
            "inflation",
            "external_balance",
            "leverage",
            "political_structure",
            "momentum",
        },
    )
    momentum_root = report.get("risk_momentum")
    momentum_records = _panel_records(
        momentum_root,
        record_keys={"country", "change_7d", "change_30d", "change_90d", "change_12m"},
    )
    panels: list[str] = []
    for item in records:
        countries = _country_names(report)
        country = _first(item, "country", "country_name") or (
            countries[0] if len(countries) == 1 else "Country set"
        )
        dimensions = [_mapping(value) for value in _sequence(item.get("dimensions"))]
        if dimensions:
            indicators = "".join(
                _indicator(
                    str(_first(dimension, "name", "label") or "Structural dimension"),
                    _first(dimension, "score", "value"),
                    formatter="percent",
                    note=str(_first(dimension, "direction", "status") or "Direction not supplied"),
                )
                for dimension in dimensions
            )
        else:
            metrics = (
                ("Composite vulnerability", _first(item, "vulnerability_score", "score"), "number"),
                ("Credit", _first(item, "credit", "credit_to_gdp", "credit_gap"), "number"),
                ("Sovereign", _first(item, "sovereign", "sovereign_stress", "debt_service"), "number"),
                ("Reserve adequacy", _first(item, "reserves", "reserve_adequacy", "reserve_cover"), "number"),
                ("Inflation", _first(item, "inflation", "cpi_inflation"), "percent"),
                (
                    "External balance",
                    _first(item, "external_balance", "current_account"),
                    "signed_percent",
                ),
                ("Leverage", _first(item, "leverage", "private_leverage"), "number"),
                ("Political structure", _first(item, "political_structure", "political_vulnerability"), "text"),
            )
            indicators = "".join(
                _indicator(
                    label,
                    value,
                    formatter=formatter,
                    note="Slow-moving structural indicator",
                )
                for label, value, formatter in metrics
            )
        panels.append(
            '<article class="indicator-panel"><header class="indicator-head"><div>'
            f'<h3>{_text(country)}</h3><p>Structural vulnerability · not an event forecast</p></div>'
            '<span class="status-label">Structural layer</span></header>'
            f'<div class="indicator-grid">{indicators}</div></article>'
        )
    vulnerability_body = (
        "".join(panels)
        if panels
        else _empty_state(
            "Structural vulnerability unavailable",
            "No slow-moving macro-financial vulnerability indicators were supplied.",
        )
    )
    momentum_items = momentum_records
    if not momentum_items:
        for record in records:
            embedded = _mapping(_first(record, "momentum", "risk_momentum"))
            if embedded:
                merged = dict(embedded)
                merged.setdefault("country", _first(record, "country", "country_name"))
                momentum_items.append(merged)
    if not momentum_items:
        by_hazard: dict[str, Mapping[str, object]] = {}
        for forecast in _forecast_records(report):
            if not _mapping(_first(forecast, "momentum", "risk_momentum")):
                continue
            key = _hazard_key(_first(forecast, "hazard", "hazard_type"))
            previous = by_hazard.get(key)
            if previous is None or _forecast_sort_value(report, forecast) > _forecast_sort_value(
                report,
                previous,
            ):
                by_hazard[key] = forecast
        for forecast in by_hazard.values():
            record = dict(forecast)
            record["country"] = (
                f'{_first(forecast, "country", "country_name") or "Country"} · '
                f'{_hazard_label(_first(forecast, "hazard", "hazard_type"))} · '
                f'{_horizon_label(_first(forecast, "horizon", "forecast_horizon"))}'
            )
            momentum_items.append(record)
    momentum_rows: list[str] = []
    for item in momentum_items:
        momentum_rows.append(
            "<tr>"
            f'<th scope="row">{_text(_first(item, "country", "country_name"))}</th>'
            f'<td>{_text(_format_change(_momentum_change(item, "7d")))}</td>'
            f'<td>{_text(_format_change(_momentum_change(item, "30d")))}</td>'
            f'<td>{_text(_format_change(_momentum_change(item, "90d")))}</td>'
            f'<td>{_text(_format_change(_momentum_change(item, "12m")))}</td></tr>'
        )
    if momentum_rows:
        table = (
            '<table data-sortable><caption>Change in risk estimate, percentage points</caption>'
            '<thead><tr><th scope="col">Country / series</th><th scope="col">7 days</th>'
            '<th scope="col">30 days</th><th scope="col">90 days</th><th scope="col">12 months</th>'
            f'</tr></thead><tbody>{"".join(momentum_rows)}</tbody></table>'
        )
        momentum_body = _table_region(table, label="Risk momentum by observation window")
    else:
        momentum_body = _empty_state(
            "Risk momentum unavailable",
            "No comparable 7-day, 30-day, 90-day or 12-month changes were supplied.",
        )
    heading = _section_heading(
        "06",
        "Structural vulnerability & risk momentum",
        "Slow-moving balance-sheet exposure and changes in model output are shown as different analytical objects.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="vulnerability-title">', 1)
    return (
        '<section class="report-section" id="vulnerability" aria-labelledby="vulnerability-title">'
        f'{heading}<div class="two-column"><div>{vulnerability_body}</div><div>{momentum_body}</div></div></section>'
    )


def _timeline_data(report: Mapping[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    analysis = _mapping(report.get("analysis"))
    payload = report.get("historical_timeline") or _first(analysis, "historical_timeline", "history")
    container = _mapping(payload)
    series = _first(container, "series", "points", "estimates") if container else payload
    points = _panel_records(
        series,
        record_keys={
            "date",
            "period",
            "probability",
            "risk_estimate",
            "estimate",
            "value",
            "vintage_state",
            "vintage_status",
        },
    )
    events_raw = (
        _first(container, "events", "crisis_onsets")
        or report.get("crisis_events")
        or report.get("events")
    )
    events = _panel_records(
        events_raw,
        record_keys={"event_id", "hazard", "hazard_type", "onset", "onset_canonical", "date"},
    )
    for point in points:
        if not _truthy(_first(point, "event_onset", "is_event_onset", "crisis_onset")):
            continue
        event = dict(point)
        event.setdefault("onset_canonical", _first(point, "date", "period", "analysis_date"))
        event.setdefault("hazard_type", _first(point, "hazard", "hazard_type", "type"))
        event.setdefault("notes", "Event onset embedded in the historical timeline")
        events.append(event)
    return points, events


def _render_history(report: Mapping[str, object]) -> str:
    points, events = _timeline_data(report)
    chart = timeline_svg(points, events, title="Historical risk timeline", chart_id="historical-risk")
    reconstructed = any(
        "reconstruct"
        in str(
            _first(
                point,
                "vintage_state",
                "vintage_status",
                "estimate_type",
                "vintage",
            )
            or ""
        ).lower()
        for point in points
    )
    state = "RECONSTRUCTED ESTIMATES" if reconstructed else "TRUE-VINTAGE / AS-OF STATE"
    rows = "".join(
        "<tr>"
        f'<th scope="row">{_text(_first(point, "date", "period", "analysis_date"))}</th>'
        f'<td>{_text(_format_percent(_first(point, "calibrated_probability", "risk_estimate", "estimate", "probability", "value")))}</td>'
        f'<td>{_text(_first(point, "hazard", "hazard_type"))}</td>'
        f'<td>{_text(_first(point, "vintage_state", "vintage_status", "estimate_type", "vintage"))}</td></tr>'
        for point in points
    )
    data_table = (
        '<table><caption>Historical estimate text alternative</caption><thead><tr>'
        '<th scope="col">Date</th><th scope="col">Estimate</th><th scope="col">Hazard</th>'
        f'<th scope="col">Vintage state</th></tr></thead><tbody>{rows}</tbody></table>'
    )
    events_rows = "".join(
        "<tr>"
        f'<th scope="row">{_text(_first(event, "onset_canonical", "onset", "date"))}</th>'
        f'<td>{_text(_hazard_label(_first(event, "hazard", "hazard_type")))}</td>'
        f'<td>{_text(_first(event, "label_confidence", "confidence"))}</td>'
        f'<td>{_text(_first(event, "notes", "source_agreement"))}</td></tr>'
        for event in events
    )
    events_table = (
        '<table><caption>Documented crisis onset markers</caption><thead><tr>'
        '<th scope="col">Onset</th><th scope="col">Hazard</th><th scope="col">Label confidence</th>'
        f'<th scope="col">Notes / agreement</th></tr></thead><tbody>{events_rows}</tbody></table>'
    )
    body = (
        '<article class="chart-panel full-span"><header class="chart-panel__header">'
        f'<h3>Historical signal and documented onsets</h3><p>{_text(state)} · '
        f'{len(events)} onset marker(s)</p></header><div class="chart-wrap">{chart}</div>'
        f'<details class="chart-data" open><summary>Timeline data</summary>{_table_region(data_table, label="Historical timeline data")}</details>'
        f'<details class="chart-data" open><summary>Crisis onset markers</summary>{_table_region(events_table, label="Documented crisis onset data")}</details></article>'
        if points
        else _empty_state(
            "Historical timeline unavailable",
            "No true-vintage or explicitly reconstructed model history was supplied. The renderer will not backfill a historical probability series.",
        )
    )
    heading = _section_heading(
        "07",
        "Historical timeline",
        "Historical estimates disclose whether they are reconstructed or could have been observed with the deployed model at the time.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="history-title">', 1)
    return f'<section class="report-section" id="history" aria-labelledby="history-title">{heading}{body}</section>'


def _analogue_context(item: Mapping[str, object]) -> str:
    regime = _first(item, "regime", "currency_regime")
    time_to_event = _first(item, "time_to_event_days", "lead_time_days")
    parts = []
    if regime not in (None, ""):
        parts.append(f"Regime: {regime}")
    if time_to_event not in (None, ""):
        parts.append(f"Time to event: {time_to_event} days")
    return " · ".join(parts) or "No additional analogue caveat supplied"


def _render_analogues(report: Mapping[str, object]) -> str:
    analogues = _panel_records(
        report.get("historical_analogues"),
        record_keys={"country", "period", "similarity", "outcome", "hazard", "distance"},
    )
    rows = "".join(
        "<tr>"
        f'<th scope="row">{_text(_first(item, "country", "country_name"))}</th>'
        f'<td>{_text(_first(item, "period", "date", "window"))}</td>'
        f'<td>{_text(_hazard_label(_first(item, "hazard", "hazard_type", "event_type")))}</td>'
        f'<td>{_text(_format_number(_first(item, "similarity", "score")))}</td>'
        f'<td>{_text(_first(item, "outcome", "subsequent_outcome"))}</td>'
        f'<td>{_text(_first(item, "evidence_quality", "confidence") or _format_percent(_first(item, "coverage")))}</td>'
        f'<td>{_text(_first(item, "notes", "caveat", "distance_method") or _analogue_context(item))}</td></tr>'
        for item in analogues
    )
    if rows:
        table = (
            '<table data-sortable><caption>Nearest disclosed historical states. Similarity does not imply identical outcomes.</caption>'
            '<thead><tr><th scope="col">Country</th><th scope="col">Period</th><th scope="col">Hazard</th>'
            '<th scope="col">Similarity</th><th scope="col">Observed outcome</th>'
            '<th scope="col">Evidence quality</th><th scope="col">Caveat</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )
        body = _table_region(table, label="Historical analogue comparison")
    else:
        body = _empty_state(
            "Historical analogues unavailable",
            "No analogue search results were supplied. The report does not invent historical comparators.",
        )
    heading = _section_heading(
        "08",
        "Historical analogues",
        "Comparable states offer context rather than a deterministic precedent; outcomes and evidence quality remain visible.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="analogues-title">', 1)
    return f'<section class="report-section" id="analogues" aria-labelledby="analogues-title">{heading}{body}</section>'


def _contributor_records(
    report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    raw = report.get("contributors") or report.get("predictive_contributors")
    selected_forecast: Mapping[str, object] | None = None
    if raw is None:
        ordered = sorted(forecasts, key=lambda item: _forecast_sort_value(report, item), reverse=True)
        selected_forecast = ordered[0] if ordered else None
        raw = (
            _first(selected_forecast, "contributors", "predictive_contributors")
            if selected_forecast
            else None
        )
    if isinstance(raw, Mapping):
        output: list[dict[str, object]] = []
        for key, sign in (("positive", 1), ("negative", -1), ("contrary_evidence", -1)):
            for item in _sequence(raw.get(key)):
                record = dict(_mapping(item))
                value = _number(_first(record, "contribution", "value", "effect", "score"))
                if value is not None:
                    record["contribution"] = abs(value) * sign
                output.append(record)
        if output:
            return output
    output = _panel_records(
        raw,
        record_keys={"name", "feature", "label", "indicator", "contribution", "effect", "value"},
    )
    if selected_forecast:
        for item in _sequence(selected_forecast.get("contrary_evidence")):
            record = dict(_mapping(item))
            value = _number(_first(record, "contribution", "value", "effect", "score"))
            if value is not None:
                record["contribution"] = -abs(value)
            output.append(record)
    return output


def _render_contributors(
    report: Mapping[str, object], forecasts: Sequence[Mapping[str, object]]
) -> str:
    contributors = _contributor_records(report, forecasts)
    chart = diverging_bars_svg(
        contributors,
        title="Predictive contributors",
        chart_id="predictive-contributors",
    )
    rows = "".join(
        "<tr>"
        f'<th scope="row">{_text(_contributor_label(item))}</th>'
        f'<td>{_text(_format_number(_first(item, "contribution", "value", "effect", "score"), decimals=3))}</td>'
        f'<td>{_text("Raises estimate" if (_number(_first(item, "contribution", "value", "effect", "score")) or 0) >= 0 else "Contrary evidence")}</td>'
        f'<td>{_text(_first(item, "availability", "available", "status", "notes"))}</td></tr>'
        for item in contributors
    )
    table = (
        '<table><caption>Signed predictive contributions; values are model contributions, not causal effects.</caption>'
        '<thead><tr><th scope="col">Feature</th><th scope="col">Contribution</th>'
        '<th scope="col">Direction</th><th scope="col">Evidence status</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )
    body = (
        '<article class="chart-panel full-span"><header class="chart-panel__header">'
        '<h3>Predictive Contributors</h3><p>Signed associations in the deployed model · not causes of crisis</p></header>'
        f'<div class="chart-wrap">{chart}</div><details class="chart-data" open>'
        f'<summary>Contributor data and contrary evidence</summary>{_table_region(table, label="Predictive contributor data")}</details>'
        '<p class="chart-note">Positive bars raise the reported estimate; dashed negative bars are contrary evidence. '
        "Neither direction establishes causation.</p></article>"
        if contributors
        else _empty_state(
            "Predictive contributors unavailable",
            "No feature-contribution output was supplied. Explanatory evidence is therefore incomplete.",
        )
    )
    heading = _section_heading(
        "09",
        "Predictive Contributors",
        "Model associations are separated into estimate-raising signals and contrary evidence, with an explicit non-causal interpretation.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="contributors-title">', 1)
    return f'<section class="report-section" id="contributors" aria-labelledby="contributors-title">{heading}{body}</section>'


def _contagion_records(report: Mapping[str, object]) -> list[dict[str, object]]:
    contagion = report.get("contagion")
    container = _mapping(contagion)
    peers = _first(container, "peers", "countries", "regional_context", "records")
    source = peers if peers is not None else contagion
    return _panel_records(
        source,
        record_keys={
            "country",
            "peer",
            "region",
            "hazard",
            "risk_estimate",
            "risk_index",
            "probability",
            "common_factor_stress",
            "contagion_indicator",
            "channel",
        },
    )


def _render_contagion(report: Mapping[str, object]) -> str:
    container = _mapping(report.get("contagion"))
    records = _contagion_records(report)
    summary_values = (
        ("Regional state", _first(container, "regional_state", "status", "region"), "text"),
        (
            "Common-factor stress",
            _first(
                container,
                "common_factor_stress",
                "common_factor_pressure",
                "global_factor",
            ),
            "percent",
        ),
        (
            "Network / contagion pressure",
            _first(container, "contagion_index", "network_stress", "network_pressure"),
            "percent",
        ),
        (
            "Own-country pressure",
            _first(container, "own_country_pressure", "domestic_pressure"),
            "percent",
        ),
    )
    summary = "".join(
        _indicator(label, value, formatter=formatter, note="Regional / network context")
        for label, value, formatter in summary_values
    )
    rows = "".join(
        "<tr>"
        f'<th scope="row">{_text(_first(item, "country", "peer", "country_name"))}</th>'
        f'<td>{_text(_first(item, "region", "peer_group") or "Peer set")}</td>'
        f'<td>{_text(_hazard_label(_first(item, "hazard", "hazard_type")) if _first(item, "hazard", "hazard_type") else "Regional context")}</td>'
        f'<td>{_text(_format_percent(_first(item, "risk_estimate", "risk_index", "probability", "score")))}</td>'
        f'<td>{_text(_format_percent(_first(item, "common_factor_stress", "common_factor") or _first(container, "common_factor_pressure", "common_factor_stress")))}</td>'
        f'<td>{_text(_first(item, "channel", "contagion_channel", "indicator"))}</td>'
        f'<td>{_text(_first(item, "confidence", "evidence_status") or _first(container, "status"))}</td></tr>'
        for item in records
    )
    if rows:
        table = (
            '<table data-sortable><caption>Accessible regional and contagion comparison; estimates retain their disclosed calibration state.</caption>'
            '<thead><tr><th scope="col">Country / peer</th><th scope="col">Region</th>'
            '<th scope="col">Hazard</th><th scope="col">Risk estimate</th>'
            '<th scope="col">Common-factor stress</th><th scope="col">Channel</th>'
            f'<th scope="col">Evidence</th></tr></thead><tbody>{rows}</tbody></table>'
        )
        table_body = _table_region(table, label="Regional and contagion context table")
    else:
        table_body = _empty_state(
            "Regional peer data unavailable",
            "No peer-country or network observations were supplied. Missing regional context does not lower country risk.",
        )
    body = (
        '<article class="indicator-panel"><header class="indicator-head"><div><h3>Regional signal ledger</h3>'
        '<p>Common shocks, peer conditions and transmission channels</p></div>'
        '<span class="status-label">Context, not attribution</span></header>'
        f'<div class="indicator-grid">{summary}</div></article><div style="height:1rem"></div>{table_body}'
    )
    heading = _section_heading(
        "10",
        "Regional / contagion context",
        "Common-factor stress and transmission channels contextualize country estimates; an accessible table is always primary evidence.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="contagion-title">', 1)
    return f'<section class="report-section" id="contagion" aria-labelledby="contagion-title">{heading}{body}</section>'


def _calibration_bins(calibration: Mapping[str, object]) -> list[dict[str, object]]:
    bins = _first(calibration, "reliability_bins", "bins", "reliability")
    if isinstance(bins, Mapping):
        bins = _first(bins, "bins", "points") or bins
    return _panel_records(
        bins,
        record_keys={"predicted", "mean_predicted", "observed", "event_rate", "count"},
    )


def _validation_windows(validation: Mapping[str, object]) -> list[dict[str, object]]:
    windows = _first(validation, "backtests", "windows", "historical_windows", "folds")
    return _panel_records(
        windows,
        record_keys={
            "window",
            "period",
            "crises_detected",
            "missed_events",
            "false_alerts",
            "warning_lead_time",
        },
    )


def _render_calibration(report: Mapping[str, object]) -> str:
    calibration = _mapping(report.get("calibration"))
    validation = _mapping(report.get("validation"))
    validation_metrics = _mapping(_first(validation, "metrics", "scores"))
    bins = _calibration_bins(calibration)
    chart = reliability_svg(bins, title="Calibration reliability", chart_id="calibration-reliability")
    status = _first(calibration, "status", "validation_status") or _first(
        validation, "calibration_status", "status"
    )
    metrics = (
        ("Calibration status", status, "text"),
        (
            "Brier score",
            _first(calibration, "brier_score", "brier")
            or _first(validation_metrics, "brier_score", "brier"),
            "number",
        ),
        (
            "Log loss",
            _first(calibration, "log_loss", "logloss")
            or _first(validation_metrics, "log_loss", "logloss"),
            "number",
        ),
        (
            "PR-AUC",
            _first(calibration, "pr_auc", "average_precision")
            or _first(validation_metrics, "pr_auc", "average_precision"),
            "number",
        ),
        ("Historical base rate", _first(calibration, "base_rate", "event_rate"), "percent"),
        (
            "Historical event count",
            _first(calibration, "event_count", "n_events", "crises")
            or _first(validation, "event_count", "n_events"),
            "number",
        ),
        (
            "Test period",
            _first(calibration, "test_period", "test_window", "calibration_period")
            or _first(validation, "test_window", "test_period"),
            "text",
        ),
        ("Calibration method", _first(calibration, "method", "calibration_method"), "text"),
    )
    metric_html = "".join(
        _indicator(label, value, formatter=formatter, note="Validation disclosure")
        for label, value, formatter in metrics
    )
    reliability_panel = (
        '<article class="chart-panel"><header class="chart-panel__header"><h3>Reliability</h3>'
        '<p>Mean forecast against observed event rate</p></header>'
        f'<div class="chart-wrap">{chart}</div><p class="chart-note">The diagonal is perfect calibration; '
        "distance from it is calibration error. Empty bins are not inferred.</p></article>"
    )
    metric_panel = (
        '<article class="analysis-panel"><header class="panel-header"><h3>Calibration audit</h3>'
        '<p>Performance is meaningful only for the disclosed hazard, horizon and out-of-sample window.</p></header>'
        f'<div class="indicator-grid">{metric_html}</div></article>'
    )

    windows = _validation_windows(validation)
    window_rows = "".join(
        "<tr>"
        f'<th scope="row">{_text(_first(item, "window", "period", "test_period"))}</th>'
        f'<td>{_text(_first(item, "crises_detected", "events_detected", "true_positives"))}</td>'
        f'<td>{_text(_first(item, "missed_events", "false_negatives"))}</td>'
        f'<td>{_text(_first(item, "false_alerts", "false_positives"))}</td>'
        f'<td>{_text(_first(item, "warning_lead_time", "median_lead_time"))}</td>'
        f'<td>{_text(_first(item, "method", "notes"))}</td></tr>'
        for item in windows
    )
    if window_rows:
        backtest_table = (
            '<table data-sortable><caption>Historical backtest windows</caption><thead><tr>'
            '<th scope="col">Window</th><th scope="col">Crises detected</th><th scope="col">Missed</th>'
            '<th scope="col">False alerts</th><th scope="col">Warning lead time</th>'
            f'<th scope="col">Method / notes</th></tr></thead><tbody>{window_rows}</tbody></table>'
        )
        backtest_body = _table_region(backtest_table, label="Historical backtest windows")
    else:
        backtest_body = _empty_state(
            "Backtest windows unavailable",
            "Crises detected, missed events, false alerts and warning lead times were not supplied.",
        )
    ablation = _mapping(_first(validation, "fx_ablation", "ablation"))
    with_fx = _first(ablation, "with_fx", "full_model") or _first(validation, "performance_with_fx")
    without_fx = _first(ablation, "without_fx", "no_fx") or _first(
        validation, "performance_without_fx"
    )
    if set(ablation) & {"delta_average_precision", "delta_brier", "delta_log_loss"}:
        ablation_indicators = (
            _indicator(
                "Δ average precision",
                _first(ablation, "delta_average_precision"),
                formatter="number",
                note="With FX minus without FX",
            )
            + _indicator(
                "Δ Brier score",
                _first(ablation, "delta_brier"),
                formatter="number",
                note="With FX minus without FX",
            )
            + _indicator(
                "Δ log loss",
                _first(ablation, "delta_log_loss"),
                formatter="number",
                note="With FX minus without FX",
            )
            + _indicator(
                "Test period",
                _first(validation, "test_window", "test_period"),
                note="Out-of-sample window",
            )
        )
    else:
        ablation_indicators = (
            _indicator("With FX", with_fx, formatter="number", note="Selected validation metric")
            + _indicator(
                "Without FX",
                without_fx,
                formatter="number",
                note="Same validation metric",
            )
            + _indicator(
                "Metric",
                _first(ablation, "metric", "score_name"),
                note="Must be comparable",
            )
            + _indicator(
                "Test period",
                _first(ablation, "test_period", "window"),
                note="Out-of-sample window",
            )
        )
    ablation_html = (
        '<article class="analysis-panel"><header class="panel-header"><h3>FX ablation</h3>'
        '<p>Performance with and without the FX feature family</p></header><div class="indicator-grid">'
        f"{ablation_indicators}"
        "</div></article>"
    )
    heading = _section_heading(
        "11",
        "Calibration & backtest",
        "Reliability, proper scoring rules, historical event counts and FX ablation make probability claims auditable.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="calibration-title">', 1)
    return (
        '<section class="report-section" id="calibration" aria-labelledby="calibration-title">'
        f'{heading}<div class="chart-grid">{reliability_panel}{metric_panel}'
        f'<div class="full-span">{backtest_body}</div><div class="full-span">{ablation_html}</div></div></section>'
    )


def _quality_score(value: object) -> tuple[float, str]:
    number = _number(value)
    if number is None:
        return 0.0, "Not available"
    normalized = number * 100 if 0 <= number <= 1 else number
    normalized = max(0.0, min(100.0, normalized))
    return normalized, f"{normalized:.0f} / 100"


def _data_quality_records(report: Mapping[str, object]) -> list[dict[str, object]]:
    quality = report.get("data_quality")
    container = _mapping(quality)
    records = _first(container, "countries", "records", "series") if container else None
    if records is None:
        records = quality
    return _panel_records(
        records,
        record_keys={
            "country",
            "coverage",
            "freshness",
            "source_authority",
            "source_disagreement",
            "historical_depth",
            "vintage_quality",
            "score",
            "data_quality_score",
        },
    )


def _render_data_quality(report: Mapping[str, object]) -> str:
    records = _data_quality_records(report)
    panels: list[str] = []
    for index, item in enumerate(records, 1):
        country = _first(item, "country", "country_name") or (
            "Overall evidence quality" if len(records) == 1 else f"Evidence unit {index}"
        )
        score_value = _first(item, "data_quality_score", "score", "quality_score", "overall")
        score, score_label = _quality_score(score_value)
        warnings = [str(value) for value in _sequence(item.get("warnings"))]
        warning = _first(item, "warning", "limitations", "status") or (
            " · ".join(warnings) if warnings else None
        )
        metrics = (
            ("Coverage", _first(item, "coverage", "coverage_score"), "quality"),
            ("Freshness", _first(item, "freshness", "freshness_status"), "quality"),
            ("Source authority", _first(item, "source_authority", "authority"), "quality"),
            ("Source disagreement", _first(item, "source_disagreement", "disagreement"), "quality"),
            ("Historical depth", _first(item, "historical_depth", "history_years"), "quality"),
            ("Vintage quality", _first(item, "vintage_quality", "point_in_time_quality"), "quality"),
            ("Release lag", _first(item, "release_lag", "publication_lag"), "text"),
            ("Missing required fields", _first(item, "missing_required", "missing_count"), "text"),
        )
        metric_html = "".join(
            _indicator(label, value, formatter=formatter, note="Evidence dimension")
            for label, value, formatter in metrics
        )
        panels.append(
            '<article class="indicator-panel"><header class="indicator-head"><div>'
            f'<h3>{_text(country)}</h3><p>{_text(warning or "Data quality is separate from economic risk")}</p></div>'
            f'<span class="status-label">{_text(score_label)}</span></header>'
            f'<label class="kicker" for="quality-{index}">Composite data-quality score</label>'
            f'<meter class="quality-meter" id="quality-{index}" min="0" max="100" value="{score:.1f}">'
            f'{score:.0f} out of 100</meter><div style="height:1rem"></div>'
            f'<div class="indicator-grid">{metric_html}</div></article>'
        )
    quality_body = (
        "".join(panels)
        if panels
        else _empty_state(
            "Data-quality audit unavailable",
            "Coverage, freshness, authority, disagreement, historical depth and vintage quality were not supplied. This absence must not be interpreted as low crisis risk.",
        )
    )
    source_health = _mapping(report.get("source_health"))
    source_values = (
        ("Healthy sources", _first(source_health, "healthy", "available", "healthy_count"), "number"),
        ("Stale sources", _first(source_health, "stale", "stale_count"), "number"),
        ("Failed sources", _first(source_health, "failed", "failed_count"), "number"),
        ("Source-health state", _first(source_health, "status", "last_audit", "checked_at"), "text"),
    )
    source_metrics = "".join(
        _indicator(label, value, formatter=formatter, note="Source-health telemetry")
        for label, value, formatter in source_values
    )
    source_panel = (
        '<article class="indicator-panel"><header class="indicator-head"><div><h3>Source health</h3>'
        '<p>Collection availability is an evidence property, not an economic outcome.</p></div>'
        '<span class="status-label">Audit layer</span></header>'
        f'<div class="indicator-grid">{source_metrics}</div></article>'
    )
    heading = _section_heading(
        "12",
        "Data quality",
        "Evidence coverage, freshness and provenance are isolated from economic risk so sparse data can never look reassuring.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="quality-title">', 1)
    return (
        '<section class="report-section" id="data-quality" aria-labelledby="quality-title">'
        f'{heading}<div class="two-column"><div>{quality_body}</div><div>{source_panel}</div></div></section>'
    )


def _render_methodology(report: Mapping[str, object]) -> str:
    method = _mapping(report.get("methodology"))
    analysis = _mapping(report.get("analysis"))
    definitions = (
        ("Event target", _first(method, "event_target", "target", "event_definition")),
        ("Forecast model", _first(method, "model", "model_summary", "estimator")),
        ("Forecast horizons", _first(method, "horizons", "forecast_horizons")),
        ("Calibration", _first(method, "calibration", "calibration_method")),
        ("Regime adjustment", _first(method, "regime_adjustment", "regime_model")),
        ("Alert threshold", _first(method, "alert_threshold", "alert_policy")),
        ("Uncertainty", _first(method, "uncertainty", "uncertainty_method")),
        ("Point-in-time policy", _first(method, "point_in_time", "vintage_policy")),
    )
    entries = "".join(
        f'<div><dt>{_text(label)}</dt><dd>{_text(value)}</dd></div>' for label, value in definitions
    )
    summary = _first(method, "summary", "description") or _first(
        analysis, "methodology_summary"
    )
    body = (
        '<div class="two-column"><article class="analysis-panel"><header class="panel-header">'
        '<h3>Method at a glance</h3><p>Definitions are reported as supplied; the renderer does not infer scientific choices.</p>'
        f'</header><div class="panel-body"><p>{_text(summary)}</p></div></article>'
        '<article class="analysis-panel"><header class="panel-header"><h3>Reproducibility ledger</h3>'
        '<p>Minimum interpretive details for an independent review</p></header>'
        f'<div class="panel-body"><dl class="definition-list">{entries}</dl></div></article></div>'
    )
    heading = _section_heading(
        "13",
        "Methodology summary",
        "Target, horizon, calibration, regime handling, thresholds and uncertainty are part of the forecast claim.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="methodology-title">', 1)
    return f'<section class="report-section" id="methodology" aria-labelledby="methodology-title">{heading}{body}</section>'


def _provenance_records(report: Mapping[str, object]) -> list[dict[str, object]]:
    provenance = report.get("provenance")
    container = _mapping(provenance)
    sources = _first(container, "sources", "records", "observations") if container else None
    if sources is None:
        sources = provenance
    return _panel_records(
        sources,
        record_keys={
            "source_name",
            "source",
            "series",
            "series_id",
            "period",
            "period_start",
            "release_date",
            "retrieval_date",
            "vintage",
            "status",
            "source_url",
            "url",
            "license",
        },
    )


def _render_sources(report: Mapping[str, object]) -> str:
    records = _provenance_records(report)
    rows = "".join(
        "<tr>"
        f'<th scope="row">{_text(_first(item, "source_name", "source", "provider"))}</th>'
        f'<td>{_text(_first(item, "series", "series_id", "feature_id", "indicator"))}</td>'
        f'<td>{_text(_first(item, "period", "period_end", "observation_date"))}</td>'
        f'<td>{_text(_first(item, "release_date", "published_at"))}</td>'
        f'<td>{_text(_first(item, "retrieval_date", "retrieved_at"))}</td>'
        f'<td>{_text(_first(item, "vintage", "revision_status"))}</td>'
        f'<td>{_text(_first(item, "status", "quality_status"))}</td>'
        f'<td>{_safe_source_url(_first(item, "source_url", "url"))}</td>'
        f'<td>{_text(_first(item, "license", "licence"))}</td></tr>'
        for item in records
    )
    if rows:
        table = (
            '<table class="provenance-table" data-sortable><caption>Source and vintage provenance appendix</caption>'
            '<thead><tr><th scope="col">Source</th><th scope="col">Series</th><th scope="col">Period</th>'
            '<th scope="col">Release date</th><th scope="col">Retrieval date</th><th scope="col">Vintage</th>'
            '<th scope="col">Status</th><th scope="col" data-no-sort>URL</th><th scope="col">License</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>'
        )
        body = _table_region(table, label="Scrollable source and provenance appendix")
    else:
        body = _empty_state(
            "Provenance appendix incomplete",
            "No auditable source records were supplied. The report should not be used as a source-complete research artifact.",
        )
    heading = _section_heading(
        "14",
        "Source / provenance appendix",
        "Series, release date, retrieval date, vintage, status, URL and license remain attached to the evidence trail.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="sources-title">', 1)
    return f'<section class="report-section" id="sources" aria-labelledby="sources-title">{heading}{body}</section>'


def _limitation_records(report: Mapping[str, object]) -> list[str]:
    raw = report.get("limitations")
    values: list[str] = []
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            item = _mapping(value)
            text = _first(item, "text", "description", "limitation") if item else value
            values.append(f"{key}: {text}" if item else str(text))
    elif isinstance(raw, str):
        values.append(raw)
    else:
        for value in _sequence(raw):
            item = _mapping(value)
            values.append(str(_first(item, "text", "description", "limitation") or value))
    if not values:
        values.append(
            "No limitations were supplied in the canonical payload; this is itself a material evidence limitation."
        )
    return values


def _render_limitations(report: Mapping[str, object]) -> str:
    items = "".join(f"<li>{_text(value)}</li>" for value in _limitation_records(report))
    heading = _section_heading(
        "15",
        "Limitations",
        "Known blind spots, point-in-time constraints and model-domain caveats are part of the result, not footnotes to it.",
    ).replace('<h2 class="section-title">', '<h2 class="section-title" id="limitations-title">', 1)
    return (
        '<section class="report-section" id="limitations" aria-labelledby="limitations-title">'
        f'{heading}<ol class="limitations-list">{items}</ol></section>'
    )


def _render_footer(report: Mapping[str, object]) -> str:
    analysis = _mapping(report.get("analysis"))
    generated = _first(analysis, "generated_at", "report_generated_at", "generated_date")
    schema = report.get("schema_version")
    return f"""
    <footer class="report-footer">
      <p><strong>FX-CPM research report.</strong> Probabilistic early-warning signals are not declarations,
      causal findings, trading advice, or substitutes for expert country analysis.</p>
      <p>Schema {_text(schema)} · generated {_text(generated)}</p>
    </footer>
    """


def render_html_report(report: Mapping[str, object]) -> str:
    """Render ``report`` as one deterministic, self-contained HTML document.

    Report-provided strings and URLs are escaped.  Missing optional sections are
    represented by explicit evidence states, never by numeric zero.  The function
    performs no I/O and never mutates the supplied mapping.

    Args:
        report: Canonical FX-CPM report payload as a plain mapping.

    Returns:
        A complete UTF-8 HTML document with inline CSS, static SVG, progressive
        JavaScript enhancements, and an escaped JSON copy of ``report``.

    Raises:
        TypeError: If ``report`` is not a mapping.
    """

    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")

    forecasts = _forecast_records(report)
    countries = _country_names(report)
    title_scope = ", ".join(countries) if countries else "Research report"
    title = f"FX-CPM — {title_scope}"
    sections = (
        _render_overview(report, forecasts),
        _render_warnings(report, forecasts),
        _render_matrix(report, forecasts),
        _render_term_structure(report, forecasts),
        _render_fx_stress(report),
        _render_vulnerability(report),
        _render_history(report),
        _render_analogues(report),
        _render_contributors(report, forecasts),
        _render_contagion(report),
        _render_calibration(report),
        _render_data_quality(report),
        _render_methodology(report),
        _render_sources(report),
        _render_limitations(report),
    )
    payload = _embedded_json(report)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="dark">\n'
        f"<title>{_text(title)}</title>\n"
        f"<style>{_STYLE}</style>\n"
        "</head>\n<body>\n"
        '<a class="skip-link" href="#main-content">Skip to report content</a>\n'
        f"{_render_header(report, forecasts)}\n{_render_navigation()}\n"
        f'<main id="main-content" tabindex="-1">{"".join(sections)}</main>\n'
        f"{_render_footer(report)}\n"
        f'<script type="application/json" id="fx-cpm-report-data">{payload}</script>\n'
        f"<script>{_SCRIPT}</script>\n"
        "</body>\n</html>\n"
    )


__all__ = ["render_html_report"]
