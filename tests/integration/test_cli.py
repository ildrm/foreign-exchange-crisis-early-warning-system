from __future__ import annotations

import json

from fx_cpm.presentation.cli import main


def test_default_cli_is_explicitly_uncalibrated(capsys) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "RESEARCH_UNCALIBRATED" in output
    assert "uncalibrated estimate" in output
    assert "not a declaration" in output


def test_cli_writes_filtered_canonical_json(tmp_path) -> None:
    output = tmp_path / "report.json"
    assert (
        main(
            [
                "--countries",
                "tr,br",
                "--hazards",
                "fx,banking",
                "--as-of",
                "2024-01-31",
                "--output",
                str(output),
                "--validate",
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert {item["country_id"] for item in payload["countries"]} == {"TR", "BR"}
    assert {item["hazard_type"] for item in payload["hazards"]} == {"FX", "BANK"}
    assert payload["analysis"]["analysis_date"] == "2024-01-31"


def test_no_seed_requires_external_input(capsys) -> None:
    assert main(["--no-seed"]) == 2
    assert "requires --input-json" in capsys.readouterr().err


def test_synthetic_backtest_is_never_presented_as_empirical(capsys) -> None:
    assert main(["--backtest", "fx"]) == 0
    output = capsys.readouterr().out
    assert "RESEARCH_UNCALIBRATED" in output

