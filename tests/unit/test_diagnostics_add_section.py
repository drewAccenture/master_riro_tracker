"""US-16: Diagnostics.add_section(title, lines_fn) adds report sections from other services (slice 7a)."""

from datetime import datetime

from riro.services.diagnostics import Diagnostics

NOW = datetime(2026, 10, 30, 10, 0, 0)
VERSIONS = {"app": "0.1.0-test"}
SUMMARY = "Sign-in summary (last 7 days):"


def make():
    return Diagnostics(None, versions=VERSIONS, now=lambda: NOW)


def test_us16_section_sits_between_summary_and_recent_steps():
    diag = make()
    diag.add_section("Zz Section One:", lambda: ["line a", "line b"])
    text = diag.report()
    assert text.endswith("\n")
    assert text.splitlines() == [
        "RIRO Tracker diagnostic report",
        "",
        "app: 0.1.0-test",
        "",
        SUMMARY,
        "(none)",
        "",
        "Zz Section One:",
        "line a",
        "line b",
        "",
        "Recent steps:",
        "(none)",
        "",
        "Last file checked:",
        "(none)",
    ]


def test_us16_sections_appear_in_the_order_added():
    diag = make()
    diag.add_section("Second Added:", lambda: ["b"])
    diag.add_section("Third Added:", lambda: ["c"])
    lines = diag.report().splitlines()
    assert (
        lines.index(SUMMARY)
        < lines.index("Second Added:")
        < lines.index("Third Added:")
        < lines.index("Recent steps:")
    )
    assert lines[lines.index("Second Added:") + 1 : lines.index("Third Added:")] == [
        "b",
        "",
    ]


def test_us16_empty_section_shows_none():
    diag = make()
    diag.add_section("Empty Section:", list)
    lines = diag.report().splitlines()
    i = lines.index("Empty Section:")
    assert lines[i + 1 : i + 3] == ["(none)", ""]


def test_us16_lines_fn_is_called_each_time_report_runs():
    calls = []

    def lines():
        calls.append(1)
        return [f"call {len(calls)}"]

    diag = make()
    diag.add_section("Counting:", lines)
    assert calls == []  # not called when added
    assert "call 1" in diag.report().splitlines()
    assert "call 2" in diag.report().splitlines()
    assert len(calls) == 2


def test_us16_section_that_raises_shows_not_available_and_rest_still_appears():
    def broken():
        raise RuntimeError("Zz Secret Joiner exploded")

    diag = make()
    diag.event("sync", result="ok", duration_s=1.0)
    diag.add_section("Before:", lambda: ["fine before"])
    diag.add_section("Broken:", broken)
    diag.add_section("After:", lambda: ["fine after"])
    text = diag.report()
    lines = text.splitlines()
    i = lines.index("Broken:")
    assert lines[i + 1 : i + 3] == ["(not available)", ""]
    assert "fine before" in lines
    assert "fine after" in lines
    assert "app: 0.1.0-test" in lines
    assert SUMMARY in lines
    assert "Recent steps:" in lines
    assert any(" sync " in f" {line} " for line in lines)
    assert "Last file checked:" in lines
    assert "Zz Secret" not in text
    assert "RuntimeError" not in text
