"""US-13, US-09, ADR-004, ADR-007: files the import skips (exact reasons), one save, SaveFailed, diagnostics.

services.local_import.import_paths. Files are synthetic, written to tmp_path. Never a huge file: a small max_bytes.
"""

import os

import pytest
from import_fakes import (
    BROKEN,
    HEADER,
    T_IMPORT,
    SwitchDataFile,
    checklist_bytes,
    write_checklist,
    write_file,
)
from joiner_fakes import T1, joiner, rec, run
from store_sync_fakes import FakeDiagnostics

from riro.services.local_import import (
    MAX_BYTES,
    NOT_XLSX,
    TOO_LARGE,
    import_paths,
    import_summary,
)
from riro.services.sync_files import UNREADABLE, not_a_checklist
from riro.services.sync_messages import SAVE_FAILED
from riro.store.repo import Repo

A = "Synthetic Joiner A.xlsx"


def make_repo():
    datafile = SwitchDataFile()
    return Repo(datafile), datafile


def test_us13_limits_and_texts_are_as_agreed():
    assert MAX_BYTES == 20 * 1024 * 1024
    assert NOT_XLSX == "is not an .xlsx file"
    assert TOO_LARGE == "is too large (over 20 MB)"


@pytest.mark.parametrize(
    "name", ["notes.txt", "Synthetic Joiner A.xls", "Synthetic Joiner A.csv", "xlsx"]
)
def test_us13_not_an_xlsx_name_is_skipped_and_nothing_is_saved(tmp_path, name):
    path = write_file(tmp_path / "picked", name, checklist_bytes())
    repo, datafile = make_repo()
    result = import_paths([path], repo, FakeDiagnostics(), T_IMPORT)
    assert result.state == "ok"
    assert result.skipped == ((name, NOT_XLSX),)  # base name only, never the folder
    assert (result.added, result.updated) == (0, 0)
    assert result.message == import_summary(0, 0, 1)
    assert (repo.files(), repo.joiners(), datafile.saves) == ((), (), 0)


def test_us13_name_rule_comes_before_the_size_rule(tmp_path):
    path = write_file(tmp_path, "big.txt", b"x" * 50)
    repo, _ = make_repo()
    result = import_paths([path], repo, FakeDiagnostics(), T_IMPORT, max_bytes=1)
    assert result.skipped == (("big.txt", NOT_XLSX),)


def test_us13_file_over_max_bytes_is_skipped_as_too_large(tmp_path):
    path = write_checklist(tmp_path, A)
    size = os.path.getsize(path)
    repo, datafile = make_repo()
    result = import_paths([path], repo, FakeDiagnostics(), T_IMPORT, max_bytes=size - 1)
    assert result.skipped == ((A, TOO_LARGE),)
    assert (repo.files(), datafile.saves) == ((), 0)


def test_us13_file_of_exactly_max_bytes_is_imported(tmp_path):
    path = write_checklist(tmp_path, A)
    repo, _ = make_repo()
    result = import_paths(
        [path], repo, FakeDiagnostics(), T_IMPORT, max_bytes=os.path.getsize(path)
    )
    assert (result.added, result.skipped) == (1, ())


def test_us13_broken_bytes_are_skipped_as_unreadable(tmp_path):
    path = write_file(tmp_path, A, BROKEN)
    repo, datafile = make_repo()
    result = import_paths([path], repo, FakeDiagnostics(), T_IMPORT)
    assert result.skipped == ((A, UNREADABLE),)
    assert (repo.files(), datafile.saves) == ((), 0)


def test_us13_file_that_cannot_be_opened_is_skipped_as_unreadable(tmp_path):
    path = str(tmp_path / "gone" / A)  # never written
    repo, _ = make_repo()
    result = import_paths([path], repo, FakeDiagnostics(), T_IMPORT)
    assert result.state == "ok"
    assert result.skipped == ((A, UNREADABLE),)
    assert repo.files() == ()


def test_us13_missing_headers_are_skipped_as_not_a_checklist(tmp_path):
    header = [h for h in HEADER if h not in ("Role", "Deadline")]
    rows = [["Test Person A", 1, "Invented task one", "Not Started", None, "", ""]]
    path = write_checklist(tmp_path, A, rows=rows, header=header)
    repo, datafile = make_repo()
    result = import_paths([path], repo, FakeDiagnostics(), T_IMPORT)
    assert result.skipped == ((A, not_a_checklist(("Role", "Deadline"))),)
    assert (repo.files(), datafile.saves) == ((), 0)


def test_us13_good_and_bad_files_skips_keep_the_picked_order(tmp_path):
    paths = [
        write_file(tmp_path, "notes.txt", b"synthetic"),
        write_checklist(tmp_path, A, owner="Test Person A"),
        write_file(tmp_path, "Synthetic Joiner B.xlsx", BROKEN),
    ]
    repo, _ = make_repo()
    result = import_paths(paths, repo, FakeDiagnostics(), T_IMPORT)
    assert result.state == "ok"
    assert result.skipped == (
        ("notes.txt", NOT_XLSX),
        ("Synthetic Joiner B.xlsx", UNREADABLE),
    )
    assert result.added == 1
    assert result.message == import_summary(1, 0, 2)
    assert [r.name for r in repo.files()] == [A]


def test_adr004_one_import_of_several_files_is_one_save(tmp_path):
    paths = [
        write_checklist(tmp_path, A, owner="Test Person A"),
        write_checklist(tmp_path, "Synthetic Joiner B.xlsx", owner="Test Person B"),
        write_checklist(tmp_path, "Synthetic Joiner C.xlsx", owner="Test Person C"),
    ]
    repo, datafile = make_repo()
    import_paths(paths, repo, FakeDiagnostics(), T_IMPORT)
    assert datafile.saves == 1
    assert len(repo.files()) == 3


def test_adr004_save_failed_gives_the_save_message_and_changes_nothing(tmp_path):
    repo, datafile = make_repo()
    repo.apply(
        [rec("id-b", owner="Test Person B")],
        T1,
        run(),
        joiners=[joiner("id-b", name="Test Person B")],
    )
    before = (repo.files(), repo.joiners(), repo.last_success(), repo.runs())
    datafile.fail = True
    diagnostics = FakeDiagnostics()
    path = write_checklist(tmp_path, A, owner="Test Person A")
    result = import_paths([path], repo, diagnostics, T_IMPORT)
    assert (result.state, result.message) == ("failed", SAVE_FAILED)
    assert (repo.files(), repo.joiners(), repo.last_success(), repo.runs()) == before
    [event] = diagnostics.of("local_import")
    assert (event["result"], event["error_kind"]) == ("failed", "SaveFailed")


def test_adr007_local_import_event_has_counts_only(tmp_path):
    repo, _ = make_repo()
    first = write_checklist(tmp_path / "one", A, owner="Test Person A")
    import_paths([first], repo, FakeDiagnostics(), T_IMPORT)
    paths = [
        write_checklist(tmp_path / "two", A, owner="Test Person A"),  # updated
        write_checklist(
            tmp_path / "two", "Synthetic Joiner B.xlsx", owner="Test Person B"
        ),  # added
        write_file(tmp_path / "two", "Synthetic notes.txt", b"synthetic"),  # skipped
    ]
    diagnostics = FakeDiagnostics()
    import_paths(paths, repo, diagnostics, T_IMPORT)
    [event] = diagnostics.of("local_import")
    assert {
        k: event[k] for k in ("result", "files_count", "added_count", "updated_count")
    } == {
        "result": "ok",
        "files_count": 3,
        "added_count": 1,
        "updated_count": 1,
    }
    assert (event["skipped_count"], event["error_kind"]) == (1, None)


def test_adr007_diagnostics_never_hold_names_paths_or_owner_text(tmp_path):
    repo, datafile = make_repo()
    paths = [
        write_checklist(tmp_path, A, owner="Test Person A"),
        write_checklist(tmp_path, "Synthetic Joiner A dup.xlsx", owner="test person a"),
        write_file(tmp_path, "Synthetic Joiner B.xlsx", BROKEN),
        write_file(tmp_path, "Synthetic notes.txt", b"synthetic"),
    ]
    diagnostics = FakeDiagnostics()
    import_paths(paths, repo, diagnostics, T_IMPORT)
    datafile.fail = True
    import_paths(
        [write_checklist(tmp_path, "Synthetic Joiner C.xlsx", owner="Test Person C")],
        repo,
        diagnostics,
        T_IMPORT,
    )
    assert len(diagnostics.of("local_import")) == 2
    text = repr(diagnostics.events) + repr(diagnostics.file_reports)
    lowered = text.lower()
    assert "test person" not in lowered
    assert "synthetic" not in lowered
    assert ".xlsx" not in lowered and ".txt" not in lowered
    assert str(tmp_path).lower() not in lowered
    assert tmp_path.name.lower() not in lowered
