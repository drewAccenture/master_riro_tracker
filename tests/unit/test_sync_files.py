"""US-06, US-09, US-10: services/sync_files.py decides per file: unchanged, updated or skipped with a reason."""

import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from riro.connectors.sharepoint import errors
from riro.core.checklist import OPTIONAL_HEADERS, REQUIRED_HEADERS, read
from riro.core.models import FileRecord
from riro.services.sync_files import (
    NO_ACCESS,
    NOT_FOUND,
    UNREADABLE,
    FileOutcome,
    FolderResult,
    not_a_checklist,
    sync_folder,
)

T1 = datetime(2026, 10, 29, 9, 0, 0)
T2 = datetime(2026, 10, 29, 9, 5, 0)
BROKEN = b"PK\x03\x04 broken synthetic bytes"
REPO_ROOT = Path(__file__).resolve().parents[2]


def item(file_id, name=None, etag=None, modified="2026-10-20"):
    return {
        "id": file_id,
        "name": name or f"Synthetic Joiner {file_id}.xlsx",
        "etag": etag or f"e-{file_id}-1",
        "modified": modified,
        "size": 10,
    }


def stored(file_id, checklist, **changes):
    base = FileRecord(
        id=file_id,
        name=f"Synthetic Joiner {file_id}.xlsx",
        etag=f"e-{file_id}-1",
        modified="2026-10-20",
        present=True,
        checklist=checklist,
        read_at=T1,
        problem=None,
    )
    return replace(base, **changes)


class Downloads:
    def __init__(self, data):
        self.data = data  # id -> bytes or exception
        self.calls = []

    def __call__(self, file_id):
        self.calls.append(file_id)
        value = self.data[file_id]
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def good(make_checklist, make_row):
    return make_checklist(
        [make_row(1, "Invented task one"), make_row(2, "Invented task two")]
    )


@pytest.fixture
def other(make_checklist, make_row):
    return make_checklist([make_row(1, "Invented other task", owner="Test Person B")])


def by_id(result):
    return {r.id: r for r in result.records}


def test_us06_reason_texts():
    assert (
        UNREADABLE == "could not be read. It may be open, broken or not an .xlsx file"
    )
    assert NOT_FOUND == "could not be downloaded: the file was not found"
    assert NO_ACCESS == "could not be downloaded: you do not have access to the file"
    assert (
        not_a_checklist(["Role", "Deadline"])
        == "not a checklist: missing headers Role, Deadline"
    )


def test_us06_only_xlsx_files_count_in_any_case(good):
    listing = [
        item("1", "notes.txt"),
        item("2", "Synthetic B.XLSX"),
        item("3", "synthetic c.xlsx"),
    ]
    download = Downloads({"2": good, "3": good})
    result = sync_folder(listing, {}, download, T1)
    assert isinstance(result, FolderResult)
    assert result.total == 2
    assert download.calls == ["2", "3"]
    assert [(o.index, o.file_id, o.kind) for o in result.outcomes] == [
        (1, "2", "updated"),
        (2, "3", "updated"),
    ]
    assert set(by_id(result)) == {"2", "3"}


def test_us06_new_file_is_downloaded_read_and_updated(good):
    result = sync_folder(
        [item("a", modified="2026-10-22")], {}, Downloads({"a": good}), T2
    )
    assert result.records == (
        FileRecord(
            id="a",
            name="Synthetic Joiner a.xlsx",
            etag="e-a-1",
            modified="2026-10-22",
            present=True,
            checklist=read(good),
            read_at=T2,
            problem=None,
        ),
    )
    assert result.outcomes == (
        FileOutcome(1, "a", "Synthetic Joiner a.xlsx", "updated", "", read(good)),
    )
    assert (result.updated, result.unchanged, result.skipped) == (1, 0, ())


def test_us06_same_etag_with_stored_data_is_not_downloaded(good):
    old = stored("a", read(good))
    listing = [item("a", name="Synthetic Renamed a.xlsx", modified="2026-10-23")]
    download = Downloads({})
    result = sync_folder(listing, {"a": old}, download, T2)
    assert download.calls == []
    assert result.outcomes[0].kind == "unchanged"
    assert by_id(result)["a"] == stored(
        "a", read(good), name="Synthetic Renamed a.xlsx", modified="2026-10-23"
    )
    assert (result.updated, result.unchanged) == (0, 1)


def test_us09_same_etag_without_stored_data_is_tried_again(good):
    never_read = stored("a", None, etag="e-a-1", read_at=None, problem=UNREADABLE)
    download = Downloads({"a": good})
    result = sync_folder([item("a")], {"a": never_read}, download, T2)
    assert download.calls == ["a"]
    assert by_id(result)["a"].checklist == read(good)
    assert by_id(result)["a"].problem is None


def test_us06_changed_etag_is_downloaded_again(good, other):
    old = stored("a", read(good))
    result = sync_folder(
        [item("a", etag="e-a-2")], {"a": old}, Downloads({"a": other}), T2
    )
    record = by_id(result)["a"]
    assert (record.checklist, record.etag, record.read_at) == (read(other), "e-a-2", T2)


def test_us09_unreadable_file_keeps_old_data_etag_and_read_time(good, other):
    old = stored("a", read(good))
    listing = [item("a", etag="e-a-2", modified="2026-10-24"), item("b")]
    result = sync_folder(listing, {"a": old}, Downloads({"a": BROKEN, "b": other}), T2)
    assert by_id(result)["a"] == stored(
        "a", read(good), modified="2026-10-24", problem=UNREADABLE
    )
    assert result.outcomes[0] == FileOutcome(
        1, "a", "Synthetic Joiner a.xlsx", "unreadable", UNREADABLE
    )
    assert by_id(result)["b"].checklist == read(other)  # US-09: other files go on
    assert result.skipped == (("Synthetic Joiner a.xlsx", UNREADABLE),)
    assert (result.updated, result.unchanged) == (1, 0)


def test_us09_unreadable_file_never_read_has_no_data():
    result = sync_folder([item("a")], {}, Downloads({"a": BROKEN}), T2)
    assert by_id(result)["a"] == FileRecord(
        id="a",
        name="Synthetic Joiner a.xlsx",
        etag="",
        modified="2026-10-20",
        present=True,
        checklist=None,
        read_at=None,
        problem=UNREADABLE,
    )


def test_us09_missing_headers_is_not_a_checklist_and_keeps_old_data(
    good, make_checklist, make_row
):
    header = [
        h for h in REQUIRED_HEADERS + OPTIONAL_HEADERS if h not in ("Role", "Deadline")
    ]
    template = make_checklist([make_row(1, "Invented task one")], header=header)
    old = stored("a", read(good))
    result = sync_folder(
        [item("a", etag="e-a-2")], {"a": old}, Downloads({"a": template}), T2
    )
    reason = not_a_checklist(("Role", "Deadline"))
    assert result.outcomes[0].kind == "not_checklist"
    assert result.outcomes[0].reason == reason
    assert by_id(result)["a"] == stored("a", read(good), problem=reason)
    assert result.skipped == (("Synthetic Joiner a.xlsx", reason),)


@pytest.mark.parametrize(
    ("kind", "reason"), [("NotFound", NOT_FOUND), ("NoAccess", NO_ACCESS)]
)
def test_us09_per_file_download_error_skips_only_that_file(good, other, kind, reason):
    old = stored("a", read(good))
    listing = [item("a", etag="e-a-2"), item("b")]
    download = Downloads({"a": getattr(errors, kind)("synthetic"), "b": other})
    result = sync_folder(listing, {"a": old}, download, T2)
    assert result.outcomes[0].kind == "download_failed"
    assert result.outcomes[0].reason == reason
    assert by_id(result)["a"] == stored("a", read(good), problem=reason)
    assert by_id(result)["b"].checklist == read(other)
    assert result.skipped == (("Synthetic Joiner a.xlsx", reason),)


@pytest.mark.parametrize(
    "kind", ["NeedsSignIn", "Unreachable", "TimedOut", "EdgeMissing"]
)
def test_us07_whole_sync_connector_errors_propagate(good, kind):
    download = Downloads({"a": good, "b": getattr(errors, kind)("synthetic")})
    with pytest.raises(getattr(errors, kind)):
        sync_folder([item("a"), item("b")], {}, download, T2)


def test_adr003_check_runs_after_each_download_and_can_stop_the_sync(good):
    events = []

    def download(file_id):
        events.append(("download", file_id))
        return good

    sync_folder(
        [item("a"), item("b")], {}, download, T2, check=lambda: events.append("check")
    )
    assert events == [("download", "a"), "check", ("download", "b"), "check"]

    class Stop(Exception):
        pass

    def stop():
        raise Stop()

    with pytest.raises(Stop):
        sync_folder([item("a")], {}, Downloads({"a": good}), T2, check=stop)


def test_us10_file_gone_from_listing_is_hidden_with_its_data(good):
    stored_files = {"a": stored("a", read(good)), "gone": stored("gone", read(good))}
    result = sync_folder([item("a")], stored_files, Downloads({}), T2)
    assert by_id(result)["gone"] == stored("gone", read(good), present=False)
    assert result.total == 1
    assert len(result.records) == 2


def test_us10_hidden_file_listed_again_is_shown(good):
    hidden = stored("a", read(good), present=False)
    result = sync_folder([item("a")], {"a": hidden}, Downloads({}), T2)
    assert by_id(result)["a"].present is True
    assert by_id(result)["a"].checklist == read(good)


def test_us07_counts_and_skipped_in_listing_order(good, other):
    stored_files = {"u": stored("u", read(good))}
    listing = [item("x", etag="e-x-1"), item("u"), item("n"), item("y")]
    download = Downloads({"x": BROKEN, "n": other, "y": errors.NotFound("synthetic")})
    result = sync_folder(listing, stored_files, download, T2)
    assert [o.kind for o in result.outcomes] == [
        "unreadable",
        "unchanged",
        "updated",
        "download_failed",
    ]
    assert [o.index for o in result.outcomes] == [1, 2, 3, 4]
    assert (result.total, result.updated, result.unchanged) == (4, 1, 1)
    assert result.skipped == (
        ("Synthetic Joiner x.xlsx", UNREADABLE),
        ("Synthetic Joiner y.xlsx", NOT_FOUND),
    )


def test_adr007_openpyxl_data_validation_warning_is_filtered_at_import():
    script = (
        "import warnings\n"
        "import riro.services.sync_files\n"
        "with warnings.catch_warnings(record=True) as log:\n"
        "    for text in ('Data Validation extension is not supported and will be removed',\n"
        "                 'zz other synthetic warning'):\n"
        "        warnings.warn_explicit(text, UserWarning, 'reader.py', 1,\n"
        "                               module='openpyxl.worksheet._reader')\n"
        "print([str(w.message) for w in log])\n"
    )
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"))
    done = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['zz other synthetic warning']"
