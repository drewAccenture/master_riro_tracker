"""US-16, measures US-08: the "Sign-in summary (last 7 days):" section of the diagnostic report (slice 7a).

Real Diagnostics with a settable clock, so events land on chosen days. Log files are synthetic, under tmp_path.
"""

from datetime import datetime, timedelta

import pytest

from riro.services.diagnostics import Diagnostics

NOW = datetime(2026, 10, 30, 10, 0, 0)
VERSIONS = {"app": "0.1.0-test", "python": "3.13.9"}
TITLE = "Sign-in summary (last 7 days):"


class DayClock:
    """now() returns .at; tests move .at between events."""

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


def make(opened, clock, log_dir=None):
    diag = Diagnostics(log_dir, versions=VERSIONS, now=clock)
    opened.append(diag)
    return diag


def section(text, title=TITLE):
    lines = text.splitlines()
    assert title in lines, f"{title!r} missing from report"
    start = lines.index(title) + 1
    end = lines.index("", start)
    return lines[start:end]


def at(clock, day, hour=9, minute=0):
    clock.at = datetime(2026, 10, day, hour, minute, 0)


# --- layout ------------------------------------------------------------------------------------------------------


def test_us16_report_layout_with_summary_and_no_events(opened):
    text = make(opened, DayClock()).report()
    assert text.endswith("\n")
    assert text.splitlines() == [
        "RIRO Tracker diagnostic report",
        "",
        "app: 0.1.0-test",
        "python: 3.13.9",
        "",
        TITLE,
        "(none)",
        "",
        "Recent steps:",
        "(none)",
        "",
        "Last file checked:",
        "(none)",
    ]


def test_us16_summary_comes_before_recent_steps(opened):
    clock = DayClock()
    diag = make(opened, clock)
    diag.event("sign_in", result="ok")
    lines = diag.report().splitlines()
    assert lines.index(TITLE) < lines.index("Recent steps:")
    assert lines.index("python: 3.13.9") < lines.index(TITLE)


# --- counts per day (in memory, no log folder) -------------------------------------------------------------------


def test_us08_counts_sign_ins_and_renewals_ok_and_failed_per_day(opened):
    clock = DayClock()
    diag = make(opened, clock)
    at(clock, 29)
    diag.event("sign_in", result="ok", duration_s=20.0)
    diag.event("renewal", result="ok", duration_s=12.4)
    diag.event("renewal", result="failed", error_kind="TimedOut", duration_s=45.0)
    at(clock, 30)
    diag.event("sign_in", result="ok", duration_s=8.0)
    diag.event("sign_in", result="failed", error_kind="NeedsSignIn")
    diag.event("renewal", result="ok", duration_s=3.0)
    diag.event("renewal", result="ok", duration_s=2.25)
    diag.event("renewal", result="failed", error_kind="TimedOut")
    clock.at = NOW
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 2 (failed 1), silent renewals 3 (failed 1), longest renewal 3 s",
        "2026-10-29: visible sign-ins 1 (failed 0), silent renewals 2 (failed 1), longest renewal 45 s",
    ]


def test_us08_newest_day_first_whatever_the_event_order(opened):
    clock = DayClock()
    diag = make(opened, clock)
    at(clock, 28)
    diag.event("sign_in", result="ok")
    at(clock, 30)
    diag.event("sign_in", result="ok")
    at(clock, 26)
    diag.event("sign_in", result="failed")
    clock.at = NOW
    days = [line.split(":")[0] for line in section(diag.report())]
    assert days == ["2026-10-30", "2026-10-28", "2026-10-26"]


def test_us08_no_longest_renewal_when_no_renewal_has_a_duration(opened):
    clock = DayClock()
    diag = make(opened, clock)
    diag.event("sign_in", result="ok", duration_s=30.0)
    diag.event("renewal", result="ok")
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 1 (failed 0), silent renewals 1 (failed 0)",
    ]


def test_us08_day_with_only_sign_ins_shows_zero_renewals(opened):
    clock = DayClock()
    diag = make(opened, clock)
    diag.event("sign_in", result="ok")
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 1 (failed 0), silent renewals 0 (failed 0)",
    ]


@pytest.mark.parametrize(
    ("duration", "shown"),
    [(12.4, "12.4"), (3, "3"), (3.0, "3"), (0, "0"), (7.5, "7.5"), (0.25, "0.25")],
)
def test_us08_longest_renewal_is_formatted_like_the_report(opened, duration, shown):
    diag = make(opened, DayClock())
    diag.event("renewal", result="ok", duration_s=duration)
    assert section(diag.report()) == [
        f"2026-10-30: visible sign-ins 0 (failed 0), silent renewals 1 (failed 0), longest renewal {shown} s",
    ]


def test_us08_other_steps_are_not_counted(opened):
    clock = DayClock()
    diag = make(opened, clock)
    diag.event("sign_in", result="ok")
    for step in ("edge_start", "health_ping", "list", "download", "sync", "other"):
        diag.event(step, result="failed", duration_s=99.0)
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 1 (failed 0), silent renewals 0 (failed 0)",
    ]


def test_us08_day_without_sign_in_or_renewal_gets_no_line(opened):
    clock = DayClock()
    diag = make(opened, clock)
    at(clock, 29)
    diag.event("sync", result="ok", duration_s=4.0)
    diag.event("list", result="failed", error_kind="NoAccess")
    at(clock, 30)
    diag.event("health_ping", result="ok")
    assert section(diag.report()) == ["(none)"]


# --- the 7-day window --------------------------------------------------------------------------------------------


def test_us08_window_is_today_and_the_six_days_before(opened):
    clock = DayClock()
    diag = make(opened, clock)
    clock.at = NOW - timedelta(days=7)  # 2026-10-23: too old
    diag.event("sign_in", result="ok")
    clock.at = NOW - timedelta(days=6)  # 2026-10-24: oldest day kept
    diag.event("renewal", result="ok", duration_s=1.5)
    clock.at = NOW + timedelta(days=1)  # 2026-10-31: future, left out
    diag.event("sign_in", result="failed")
    clock.at = NOW.replace(hour=23, minute=59)
    diag.event("sign_in", result="ok")
    clock.at = NOW
    assert section(diag.report()) == [
        "2026-10-30: visible sign-ins 1 (failed 0), silent renewals 0 (failed 0)",
        "2026-10-24: visible sign-ins 0 (failed 0), silent renewals 1 (failed 0), longest renewal 1.5 s",
    ]
