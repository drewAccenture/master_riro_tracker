"""US-16, measures US-08: the sign-in summary reads the rotating log files when there is a log folder (slice 7a).

Synthetic log lines only, written under tmp_path in the same format Diagnostics.event() writes.
"""

from datetime import datetime

import pytest

from riro.core.models import HeaderReport
from riro.services.diagnostics import Diagnostics

NOW = datetime(2026, 10, 30, 10, 0, 0)
VERSIONS = {"app": "0.1.0-test"}
TITLE = "Sign-in summary (last 7 days):"


class DayClock:
    def __init__(self, at=NOW):
        self.at = at

    def __call__(self):
        return self.at


@pytest.fixture
def opened():
    made = []
    yield made
    for diag in made:
        diag.close()


def make(opened, clock, log_dir):
    diag = Diagnostics(log_dir, versions=VERSIONS, now=clock)
    opened.append(diag)
    return diag


def section(text, title=TITLE):
    lines = text.splitlines()
    assert title in lines, f"{title!r} missing from report"
    start = lines.index(title) + 1
    end = lines.index("", start)
    return lines[start:end]


def write_log(path, *lines):
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def test_us08_new_diagnostics_on_same_folder_sees_earlier_days(opened, tmp_path):
    clock = DayClock(datetime(2026, 10, 28, 8, 30, 0))
    first = make(opened, clock, tmp_path)
    first.event("sign_in", result="ok", duration_s=25.0)
    first.event("renewal", result="ok", duration_s=5.0)
    first.close()
    clock.at = NOW
    second = make(opened, clock, tmp_path)
    second.event("renewal", result="failed", error_kind="TimedOut")
    assert section(second.report()) == [
        "2026-10-30: visible sign-ins 0 (failed 0), silent renewals 1 (failed 1)",
        "2026-10-28: visible sign-ins 1 (failed 0), silent renewals 1 (failed 0), longest renewal 5 s",
    ]


def test_us08_with_a_log_folder_events_are_not_counted_twice(opened, tmp_path):
    diag = make(opened, DayClock(), tmp_path)
    diag.event("sign_in", result="ok")
    diag.event("renewal", result="ok", duration_s=2.0)
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 1 (failed 0), silent renewals 1 (failed 0), longest renewal 2 s",
    ]


def test_us08_backup_log_files_are_read_too(opened, tmp_path):
    write_log(
        tmp_path / "riro.log.1",
        "2026-10-27 08:00:00 sign_in result=ok",
        "2026-10-27 08:05:00 renewal duration_s=7.5 result=ok",
    )
    write_log(
        tmp_path / "riro.log.3",
        "2026-10-25 09:00:00 renewal duration_s=45 error_kind=TimedOut result=failed",
    )
    diag = make(opened, DayClock(), tmp_path)
    diag.event("sign_in", result="failed", error_kind="NeedsSignIn")
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 1 (failed 1), silent renewals 0 (failed 0)",
        "2026-10-27: visible sign-ins 1 (failed 0), silent renewals 1 (failed 0), longest renewal 7.5 s",
        "2026-10-25: visible sign-ins 0 (failed 0), silent renewals 1 (failed 1), longest renewal 45 s",
    ]


def test_us08_old_days_in_log_files_are_left_out(opened, tmp_path):
    write_log(
        tmp_path / "riro.log.2",
        "2026-10-20 08:00:00 sign_in result=ok",
        "2026-10-23 08:00:00 sign_in result=ok",
        "2026-10-24 08:00:00 sign_in result=ok",
    )
    diag = make(opened, DayClock(), tmp_path)
    assert section(diag.report()) == [
        "2026-10-24: visible sign-ins 1 (failed 0), silent renewals 0 (failed 0)",
    ]


def test_us08_lines_not_in_our_format_are_ignored(opened, tmp_path):
    write_log(
        tmp_path / "riro.log",
        "sign_in result=ok",
        "2026-10-30 sign_in result=ok",
        "09:00:00 renewal result=ok duration_s=9",
        "zz junk line renewal sign_in",
        "file 1 of 2: rows 3, sheet first sheet",
        "  headers found: sign_in, renewal",
        "  Completion Status: sign_in = 4",
        "",
        "2026-10-30 08:00:00 renewal duration_s=1.5 result=ok",
    )
    diag = make(opened, DayClock(), tmp_path)
    diag.file_report(
        1,
        2,
        HeaderReport(
            sheet_name="Synthetic Sheet",
            sheet_matched=False,
            headers_found=("sign_in", "renewal"),
            headers_missing=(),
            row_count=3,
            status_counts={"sign_in": 4},
        ),
    )
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 0 (failed 0), silent renewals 1 (failed 0), longest renewal 1.5 s",
    ]


def test_us16_line_with_an_impossible_date_is_ignored_and_report_still_copies(
    opened, tmp_path
):
    write_log(
        tmp_path / "riro.log",
        "2026-13-45 09:00:00 sign_in result=ok",
        "2026-10-30 08:00:00 sign_in result=ok",
    )
    diag = make(opened, DayClock(), tmp_path)
    text = diag.report()
    assert "Recent steps:" in text
    assert section(text) == [
        "2026-10-30: visible sign-ins 1 (failed 0), silent renewals 0 (failed 0)",
    ]


def test_us08_empty_log_folder_shows_none(opened, tmp_path):
    diag = make(opened, DayClock(), tmp_path)
    diag.event("sync", result="ok")
    assert section(diag.report()) == ["(none)"]
