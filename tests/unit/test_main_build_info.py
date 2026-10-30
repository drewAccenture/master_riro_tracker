"""Slice 7b, US-16: the report names the app version and the build, so she can tell which build she runs.

read_build() only accepts "<git short commit> <yyyy-mm-dd>"; anything else is "unknown", no file is "source".
Files are written under tmp_path only. main() runs with a fake webview in demo mode, so no window and no Edge.
"""

from pathlib import Path

import pytest

import riro.__main__ as app
from riro.services.diagnostics import Diagnostics

ROOT = Path(__file__).resolve().parents[2]


def write(tmp_path, text):
    path = tmp_path / "build.txt"
    path.write_text(text, encoding="utf-8")
    return path


# --- read_build ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("abc1234 2026-10-30", "abc1234 2026-10-30"),
        ("abc1234 2026-10-30\n", "abc1234 2026-10-30"),
        ("  abc1234 2026-10-30  \r\n", "abc1234 2026-10-30"),
        ("0123456789ab 2026-01-02\n", "0123456789ab 2026-01-02"),
        ("abc1234 2026-10-30\nsecond line\n", "abc1234 2026-10-30"),
    ],
    ids=["plain", "newline", "spaces", "twelve-hex", "first-line-only"],
)
def test_us16_read_build_returns_a_good_line(tmp_path, text, expected):
    assert app.read_build(write(tmp_path, text)) == expected


def test_us16_read_build_without_a_file_is_source(tmp_path):
    assert app.read_build(tmp_path / "build.txt") == "source"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n",
        "junk",
        "Test Person A",
        "Test Person A 2026-10-30",
        "ABC1234 2026-10-30",
        "abc123 2026-10-30",
        "0123456789abc 2026-10-30",
        "abc1234 2026-10-30 extra",
        "abc1234  2026-10-30",
        "abc1234 2026-10-3",
        "abc1234 30-10-2026",
        "abc1234",
        "ghijklm 2026-10-30",
    ],
    ids=[
        "empty",
        "blank-line",
        "junk",
        "a-name",
        "a-name-and-date",
        "uppercase-hex",
        "six-hex",
        "thirteen-hex",
        "extra-words",
        "two-spaces",
        "short-date",
        "day-first-date",
        "no-date",
        "not-hex",
    ],
)
def test_us16_read_build_anything_else_is_unknown(tmp_path, text):
    assert app.read_build(write(tmp_path, text)) == "unknown"


def test_adr007_read_build_never_echoes_what_is_in_a_bad_file(tmp_path):
    result = app.read_build(write(tmp_path, "Test Person A\nabc1234 2026-10-30\n"))
    assert result == "unknown"


# --- version and build file ------------------------------------------------------------------------------------


def test_us16_app_version_matches_the_slice():
    assert app.APP_VERSION == "0.7.0"


def test_us16_build_file_sits_next_to_main_in_the_riro_package():
    assert isinstance(app.BUILD_FILE, Path)
    assert app.BUILD_FILE.name == "build.txt"
    assert app.BUILD_FILE.resolve().parent == Path(app.__file__).resolve().parent


def test_us16_build_script_writes_build_txt_from_the_git_commit():
    script = (ROOT / "tools" / "build_package.ps1").read_text(encoding="utf-8")
    assert "build.txt" in script
    assert "rev-parse" in script


def test_us16_build_txt_is_never_committed():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert any("build.txt" in line for line in ignored)


# --- the report shows build: under app: ------------------------------------------------------------------------


class FakeEvents:
    def __init__(self):
        self.loaded = self

    def __iadd__(self, handler):
        return self


class FakeWindow:
    def __init__(self):
        self.events = FakeEvents()


class FakeWebview:
    """Stands in for pywebview: no window opens, start() returns at once (as when the window is closed)."""

    class FileDialog:
        OPEN = "open"

    def create_window(self, *args, **kwargs):
        return FakeWindow()

    def start(self, func=None, *args, **kwargs):
        return None


def test_us16_report_shows_app_version_and_build_line(tmp_path, monkeypatch):
    made = []

    def recording_diagnostics(*args, **kwargs):
        made.append(Diagnostics(*args, **kwargs))
        return made[-1]

    monkeypatch.setenv(
        "RIRO_DATA_DIR", str(tmp_path)
    )  # demo mode: SharePoint switched off
    monkeypatch.setattr(app, "webview", FakeWebview())
    monkeypatch.setattr(app, "Diagnostics", recording_diagnostics)
    app.main()
    [diag] = made
    lines = diag.report().splitlines()
    assert "app: 0.7.0" in lines
    build = [line for line in lines if line.startswith("build: ")]
    assert len(build) == 1
    assert lines.index(build[0]) > lines.index("app: 0.7.0")
    assert build[0] == "build: " + app.read_build(app.BUILD_FILE)
