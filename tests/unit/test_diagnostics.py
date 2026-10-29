"""US-16, ADR-007: diagnostics report content and the allowed-field filter in services/diagnostics.py."""

from datetime import datetime
from pathlib import Path

import pytest

from riro.core.models import HeaderReport
from riro.services.diagnostics import Diagnostics

NOW = datetime(2026, 10, 27, 9, 15, 30)
VERSIONS = {
    "app": "0.1.0-test",
    "python": "3.13.9",
    "pywebview": "9.8.7",
    "edge": "999.0.1",
}


def make(log_dir=None):
    return Diagnostics(log_dir, versions=VERSIONS, now=lambda: NOW)


def sample_report(sheet_name="Roll-In Checklist"):
    return HeaderReport(
        sheet_name=sheet_name,
        sheet_matched=True,
        headers_found=(
            "Checklist Owner",
            "Role",
            "Task Number",
            "Description",
            "Completion Status",
        ),
        headers_missing=("Completion Date", "Deadline"),
        row_count=42,
        deadline_counts={"10 days Before Roll On": 7, "On Roll On": 11},
        status_counts={"Completed": 13, "Not Started": 17},
    )


def log_text(log_dir: Path) -> str:
    return "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in log_dir.rglob("*")
        if p.is_file()
    )


def has_line_with(text, *parts):
    return any(all(p in line for p in parts) for line in text.splitlines())


# --- content (US-16) ---------------------------------------------------------------------------------------------


def test_us16_report_holds_every_version():
    text = make().report()
    for key, value in VERSIONS.items():
        assert key in text
        assert value in text


def test_us16_report_holds_steps_with_timestamp_and_duration():
    diag = make()
    diag.event("edge_start", result="ok", duration_s=2.5, attempt=1)
    diag.event("list", result="ok", duration_s=0.75, files_count=3)
    text = diag.report()
    assert has_line_with(text, "edge_start", "2.5")
    assert has_line_with(text, "list", "0.75")
    assert "2026-10-27" in text
    assert "09:15:30" in text


@pytest.mark.parametrize(
    "step",
    [
        "edge_start",
        "sign_in",
        "renewal",
        "health_ping",
        "list",
        "download",
        "header_check",
        "sync",
    ],
)
def test_us16_known_steps_are_kept(step):
    diag = make()
    diag.event(step, result="ok", duration_s=1.5)
    assert step in diag.report()


def test_us16_unknown_step_is_recorded_as_other():
    diag = make()
    diag.event("made_up_step_zz", result="ok")
    text = diag.report()
    assert "other" in text
    assert "made_up_step_zz" not in text


def test_us16_file_report_shows_position_headers_rows_and_value_counts():
    diag = make()
    diag.file_report(1, 3, sample_report())
    text = diag.report()
    assert "file 1 of 3" in text
    for header in sample_report().headers_found + sample_report().headers_missing:
        assert header in text
    assert "42" in text
    assert has_line_with(text, "10 days Before Roll On", "7")
    assert has_line_with(text, "On Roll On", "11")
    assert has_line_with(text, "Completed", "13")
    assert has_line_with(text, "Not Started", "17")


def test_us16_file_report_never_shows_sheet_name():
    diag = make()
    diag.file_report(1, 1, sample_report(sheet_name="Zz Hidden Sheet Name"))
    assert "Zz Hidden Sheet Name" not in diag.report()


def test_us16_allowed_fields_are_kept():
    diag = make()
    diag.event(
        "download",
        result="failed",
        error_kind="TimedOut",
        http_status=403,
        attempt=2,
        rows_count=987,
    )
    text = diag.report()
    assert "failed" in text
    assert "TimedOut" in text
    assert "403" in text
    assert "987" in text


# --- allowed-field filter (ADR-007) -------------------------------------------------------------------------------


def test_adr007_unknown_fields_are_dropped_silently():
    diag = make()
    diag.event(
        "list", result="ok", nickname="zzq-unknown-value", note="zzq-other-value"
    )
    text = diag.report()
    assert "zzq-unknown-value" not in text
    assert "zzq-other-value" not in text
    assert "nickname" not in text


@pytest.mark.parametrize(
    "fields",
    [
        {"duration_s": "zzq-in-duration"},
        {"http_status": "zzq-in-status"},
        {"attempt": "zzq-in-attempt"},
        {"files_count": "zzq-in-count"},
        {"result": "zzq-not-ok-or-failed"},
        {"error_kind": "zzq-not-a-kind"},
    ],
)
def test_adr007_wrong_value_types_are_dropped_silently(fields):
    diag = make()
    diag.event("list", **fields)
    text = diag.report()
    assert "zzq" not in text
    assert "list" in text


def test_adr007_url_keeps_scheme_host_and_site_only():
    diag = make()
    url = "https://ts.accenture.com/sites/WFR-USTEAM/Shared%20Documents/Repo/ZzFolder/x.xlsx?zzq=1&b=2"
    diag.event("download", url=url)
    text = diag.report()
    assert "https://ts.accenture.com/sites/WFR-USTEAM/" in text
    assert "ZzFolder" not in text
    assert "Shared%20Documents" not in text
    assert "zzq" not in text


# --- log file (ADR-007) ------------------------------------------------------------------------------------------


def test_adr007_events_are_written_to_a_log_under_log_dir(tmp_path):
    diag = make(tmp_path)
    diag.event("health_ping", result="ok", duration_s=0.25)
    diag.event("list", result="failed", error_kind="NoAccess", http_status=403)
    text = log_text(tmp_path)
    assert "health_ping" in text
    assert "NoAccess" in text
    assert "403" in text


def test_adr007_no_log_dir_still_records_in_memory():
    diag = make(None)
    diag.event("sync", result="ok", duration_s=3.5)
    assert "sync" in diag.report()
