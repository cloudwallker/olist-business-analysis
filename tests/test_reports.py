"""Report publishing gates and weighted sensitivity summaries."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_reports.py"


def test_report_cli_can_execute_help():
    assert SCRIPT.is_file(), "Report generator is not implemented"
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("result_status, blocks, failed_marker, quality_status", [
    ("failed", 0, False, "passed"),
    ("passed", 1, False, "failed"),
    ("passed", 0, True, "passed"),
    ("passed", 0, False, "failed"),
])
def test_invalid_run_does_not_touch_existing_reports(tmp_path, result_status, blocks, failed_marker, quality_status):
    assert SCRIPT.is_file(), "Report generator is not implemented"
    run = tmp_path / "run"
    run.mkdir()
    quality = {"status": quality_status, "blocking_failures": blocks, "checks": []}
    (run / "quality.json").write_text(json.dumps(quality), encoding="utf-8")
    (run / "results.json").write_text(json.dumps({"status": result_status, "quality": quality}), encoding="utf-8")
    if failed_marker:
        (run / "failed.json").write_text('{"status":"failed"}', encoding="utf-8")
    output = tmp_path / "reports"
    output.mkdir()
    existing = output / "analysis-summary.md"
    existing.write_text("previous valid report", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "--run-dir", str(run), "--output-dir", str(output)],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "拒绝生成报告" in result.stderr
    assert existing.read_text(encoding="utf-8") == "previous valid report"
    assert sorted(path.name for path in output.iterdir()) == ["analysis-summary.md"]


def test_sensitivity_sums_numerators_and_denominators_and_rechecks_strata():
    assert SCRIPT.is_file(), "Report generator is not implemented"
    spec = importlib.util.spec_from_file_location("build_reports", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [
        {"purchase_month":"2017-02-01", "customer_state":"SP", "sample":"ALL_JOINT", "on_time_orders":100, "late_orders":50, "on_time_low_score_orders":10, "late_low_score_orders":30, "joint_eligible_orders":150, "early_answer_orders":20, "answer_timestamp_orders":120},
        {"purchase_month":"2017-02-01", "customer_state":"RJ", "sample":"ALL_JOINT", "on_time_orders":50, "late_orders":100, "on_time_low_score_orders":20, "late_low_score_orders":10, "joint_eligible_orders":150, "early_answer_orders":30, "answer_timestamp_orders":150},
        {"purchase_month":"2017-02-01", "customer_state":"SP", "sample":"EXCLUDE_EARLY_ANSWERS", "on_time_orders":100, "late_orders":30, "on_time_low_score_orders":10, "late_low_score_orders":10, "joint_eligible_orders":130, "early_answer_orders":0, "answer_timestamp_orders":100},
        {"purchase_month":"2017-02-01", "customer_state":"RJ", "sample":"EXCLUDE_EARLY_ANSWERS", "on_time_orders":20, "late_orders":100, "on_time_low_score_orders":0, "late_low_score_orders":10, "joint_eligible_orders":120, "early_answer_orders":0, "answer_timestamp_orders":120},
    ]
    summaries = module.aggregate_sensitivity(rows, min_group_orders=30)
    all_sample = summaries["ALL_JOINT"]
    sensitivity = summaries["EXCLUDE_EARLY_ANSWERS"]
    assert all_sample["on_time"]["low_score_share"] == pytest.approx(30 / 150)
    assert all_sample["late"]["low_score_share"] == pytest.approx(40 / 150)
    assert all_sample["answer_timestamp_coverage"] == pytest.approx(270 / 300)
    assert all_sample["qualified_strata"] == 2
    assert (all_sample["positive_gap_strata"], all_sample["negative_gap_strata"]) == (1, 1)
    assert sensitivity["on_time"]["low_score_share"] == pytest.approx(10 / 120)
    assert sensitivity["late"]["low_score_share"] == pytest.approx(20 / 130)
    assert sensitivity["qualified_strata"] == 1
    assert sensitivity["qualified_joint_coverage"] == pytest.approx(130 / 250)
    assert sensitivity["answer_timestamp_coverage"] == pytest.approx(220 / 250)
