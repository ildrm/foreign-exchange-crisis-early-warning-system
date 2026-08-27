from __future__ import annotations

import json

from fx_cpm.demo import build_demo_report
from fx_cpm.presentation.pdf import export_pdf as packaged_export_pdf
from scripts.build_historical_panel import main as build_panel
from scripts.export_pdf import export_pdf as script_export_pdf
from scripts.source_audit import audit_records

CSV_HEADER = (
    "observation_id,feature_id,country_id,currency_id,value,unit,frequency,"
    "period_start,period_end,release_date,retrieval_date,vintage,source_name,"
    "source_url,source_type,license,base_quality,revision_status,provenance_type,"
    "status,provider,source_authority,source_quality\n"
)


def test_panel_builder_respects_retrieval_cutoff(tmp_path) -> None:
    source = tmp_path / "observations.csv"
    source.write_text(
        CSV_HEADER
        + "first,reserves,XX,XXC,10,USD,monthly,2019-01-01,2019-01-31,"
        "2019-02-15,2019-02-15,2019-02-15,Official source,https://example.org/data,"
        "official_statistics,CC-BY-4.0,0.9,first_release,true_vintage,available,"
        "Example,primary,0.9\n"
        + "revision,reserves,XX,XXC,12,USD,monthly,2019-01-01,2019-01-31,"
        "2019-04-15,2020-01-15,2019-04-15,Official source,https://example.org/data,"
        "official_statistics,CC-BY-4.0,0.9,revised,true_vintage,available,"
        "Example,primary,0.9\n",
        encoding="utf-8",
    )
    output = tmp_path / "panel.json"
    assert (
        build_panel(
            [
                str(source),
                "--as-of",
                "2019-06-30",
                "--vintage-mode",
                "TRUE_VINTAGE",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["genuine_real_time"] is True
    assert payload["selected_records"] == 1
    assert payload["observations"][0]["value"] == 10.0


def test_source_audit_accepts_explicit_synthetic_missingness() -> None:
    findings = audit_records(build_demo_report()["provenance"])
    assert [item for item in findings if item.level == "ERROR"] == []


def test_source_audit_rejects_incomplete_provenance() -> None:
    record = dict(build_demo_report()["provenance"][0])
    record.pop("license")
    record.pop("transformation_lineage")

    codes = {item.code for item in audit_records([record]) if item.level == "ERROR"}

    assert "MISSING_REQUIRED" in codes
    assert "MISSING_REQUIRED_KEY" in codes


def test_script_pdf_export_is_the_packaged_implementation() -> None:
    assert script_export_pdf is packaged_export_pdf
