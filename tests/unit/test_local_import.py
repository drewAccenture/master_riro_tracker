"""US-13, ADR-005: a picked .xlsx becomes a local FileRecord and a waiting joiner, keyed by the normalized owner.

services.local_import.import_paths over an in-memory Repo. Files are synthetic, written to tmp_path.
"""

import hashlib

from import_fakes import T_IMPORT, row, write_checklist
from joiner_fakes import D1, T1, joiner, rec, run
from store_sync_fakes import FakeDiagnostics

from riro.services.joiners import JoinerService, duplicate_warning
from riro.services.local_import import (
    IN_SHAREPOINT,
    LOCAL_PREFIX,
    ImportResult,
    import_paths,
    import_summary,
    is_local,
    local_id,
)
from riro.store.repo import Repo

A = "Synthetic Joiner A.xlsx"


def do_import(paths, repo=None, diagnostics=None, now=T_IMPORT, **kwargs):
    repo = repo if repo is not None else Repo.in_memory()
    diagnostics = diagnostics if diagnostics is not None else FakeDiagnostics()
    return import_paths(paths, repo, diagnostics, now, **kwargs), repo


def visible(repo):
    return [j for j in repo.joiners() if not j.hidden]


def test_us13_local_id_is_the_prefix_and_12_hex_of_the_owner_sha256():
    expected = "local-" + hashlib.sha256(b"test person a").hexdigest()[:12]
    assert LOCAL_PREFIX == "local-"
    assert local_id("test person a") == expected
    assert local_id("test person a") != local_id("test person b")


def test_us13_is_local_tells_imports_from_sharepoint_ids():
    assert is_local(local_id("test person a")) is True
    assert is_local("local-abc") is True
    assert is_local("id-a") is False
    assert is_local("01ABCDEF-sharepoint-unique-id") is False


def test_us13_good_file_becomes_one_record_with_the_import_fields(tmp_path):
    path = write_checklist(tmp_path / "picked", A, owner="Test Person A")
    result, repo = do_import([path])
    key = "test person a"
    [record] = repo.files()
    assert record.id == local_id(key)
    assert record.name == A  # base name, never the path
    assert (record.etag, record.modified) == ("", T_IMPORT.isoformat())
    assert (record.present, record.read_at, record.problem) == (True, T_IMPORT, None)
    assert record.checklist.owner == "Test Person A"
    assert result == ImportResult("ok", import_summary(1, 0, 0), added=1, updated=0)


def test_us13_good_file_becomes_a_waiting_joiner_named_from_the_owner(tmp_path):
    path = write_checklist(tmp_path, A, owner="  Test Person A ")
    _, repo = do_import([path])
    [j] = visible(repo)
    assert j.file_id == local_id("test person a")
    assert j.name == "Test Person A"  # US-02: name from the Checklist Owner, trimmed
    assert j.owner_key == "test person a"
    assert (j.roll_on, j.hidden) == (None, False)
    assert [w.id for w in JoinerService(repo).waiting()] == [j.id]


def test_us13_same_reading_rules_as_us02_skipped_rows_are_kept(tmp_path):
    path = write_checklist(tmp_path, A)
    _, repo = do_import([path])
    checklist = repo.files()[0].checklist
    assert [t.number for t in checklist.tasks] == ["1", "2"]
    assert [t.status for t in checklist.tasks] == ["Not Started", "Completed"]
    assert len(checklist.skipped_rows) == 1
    assert checklist.skipped_rows[0].row_number == 4


def test_us13_empty_owner_is_keyed_and_named_by_the_file_name(tmp_path):
    rows = [
        row(1, "Invented task one", owner=""),
        row(2, "Invented task two", owner=""),
    ]
    path = write_checklist(tmp_path, "Synthetic  Joiner X.XLSX", rows=rows)
    result, repo = do_import([path])
    assert result.added == 1
    assert repo.files()[0].id == local_id("synthetic joiner x")
    assert visible(repo)[0].name == "Synthetic  Joiner X"


def test_us13_upper_case_extension_is_accepted(tmp_path):
    path = write_checklist(tmp_path, "Synthetic Joiner A.XLSX")
    result, repo = do_import([path])
    assert (result.added, result.skipped) == (1, ())
    assert len(repo.files()) == 1


def test_us13_several_files_become_several_joiners(tmp_path):
    paths = [
        write_checklist(tmp_path, A, owner="Test Person A"),
        write_checklist(tmp_path, "Synthetic Joiner B.xlsx", owner="Test Person B"),
    ]
    result, repo = do_import(paths)
    assert (result.state, result.added, result.updated) == ("ok", 2, 0)
    assert result.message == import_summary(2, 0, 0)
    assert sorted(j.name for j in visible(repo)) == ["Test Person A", "Test Person B"]


def test_us13_reimport_of_the_same_owner_updates_the_record_and_keeps_joiner_and_date(
    tmp_path,
):
    first = write_checklist(tmp_path / "one", A, owner="Test Person A")
    _, repo = do_import([first])
    [before] = visible(repo)
    assert JoinerService(repo).set_roll_on(before.id, D1.isoformat()) == (True, "")
    rows = [row(n, f"Invented task {n}", owner=" test  PERSON a") for n in (1, 2, 3)]
    second = write_checklist(tmp_path / "two", "Synthetic Joiner A v2.xlsx", rows=rows)
    later = T_IMPORT.replace(hour=11)
    result, _ = do_import([second], repo=repo, now=later)
    assert (result.added, result.updated) == (0, 1)
    assert result.message == import_summary(0, 1, 0)
    [record] = repo.files()
    assert record.id == local_id("test person a")
    assert record.name == "Synthetic Joiner A v2.xlsx"
    assert (record.modified, record.read_at) == (later.isoformat(), later)
    assert len(record.checklist.tasks) == 3
    [after] = visible(repo)
    assert (after.id, after.roll_on) == (before.id, D1)


def test_us13_two_picked_files_with_one_owner_last_wins_with_a_warning(tmp_path):
    first = write_checklist(
        tmp_path, "Synthetic Joiner A old.xlsx", owner="Test Person A"
    )
    rows = [row(n, f"Invented task {n}", owner="test person a") for n in (1, 2, 3)]
    last = write_checklist(tmp_path, "Synthetic Joiner A new.xlsx", rows=rows)
    result, repo = do_import([first, last])
    assert (result.added, result.updated) == (1, 0)  # counted once
    assert result.message == import_summary(1, 0, 0)
    assert result.warnings == (
        duplicate_warning("Synthetic Joiner A old.xlsx", "Synthetic Joiner A new.xlsx"),
    )
    [record] = repo.files()
    assert record.name == "Synthetic Joiner A new.xlsx"
    assert len(record.checklist.tasks) == 3
    assert len(visible(repo)) == 1


def test_us13_owner_already_in_sharepoint_is_skipped_sharepoint_wins(tmp_path):
    repo = Repo.in_memory()
    repo.apply(
        [rec("id-sp", owner="Test Person A")], T1, run(), joiners=[joiner("id-sp")]
    )
    before_files, before_joiners = repo.files(), repo.joiners()
    path = write_checklist(tmp_path / "picked", A, owner=" test person A")
    result, _ = do_import([path], repo=repo)
    assert result.state == "ok"
    assert result.skipped == ((A, IN_SHAREPOINT),)
    assert (result.added, result.updated) == (0, 0)
    assert result.message == import_summary(0, 0, 1)
    assert repo.files() == before_files
    assert repo.joiners() == before_joiners


def test_us13_sharepoint_file_that_left_the_folder_does_not_block_an_import(tmp_path):
    repo = Repo.in_memory()
    repo.apply(
        [rec("id-sp", owner="Test Person A", present=False)],
        T1,
        run(),
        joiners=[joiner("id-sp", hidden=True, missing_syncs=3)],
    )
    path = write_checklist(tmp_path, A, owner="Test Person A")
    result, _ = do_import([path], repo=repo)
    assert (result.added, result.skipped) == (1, ())
    assert repo.file(local_id("test person a")).present is True


def test_us13_never_read_sharepoint_file_does_not_block_an_import(tmp_path):
    repo = Repo.in_memory()
    repo.apply(
        [rec("id-sp", owner="Test Person A", read=False, problem="x")], T1, run()
    )
    path = write_checklist(tmp_path, A, owner="Test Person A")
    result, _ = do_import([path], repo=repo)
    assert (result.added, result.skipped) == (1, ())


def test_us13_import_keeps_existing_sharepoint_joiners_and_their_dates(tmp_path):
    repo = Repo.in_memory()
    repo.apply(
        [rec("id-b", owner="Test Person B")],
        T1,
        run(),
        joiners=[joiner("id-b", name="Test Person B")],
    )
    JoinerService(repo).set_roll_on("id-b", D1.isoformat())
    path = write_checklist(tmp_path, A, owner="Test Person A")
    do_import([path], repo=repo)
    shown = {j.name: j for j in visible(repo)}
    assert set(shown) == {"Test Person A", "Test Person B"}
    assert (shown["Test Person B"].id, shown["Test Person B"].roll_on) == ("id-b", D1)
    assert shown["Test Person A"].roll_on is None
    assert repo.file("id-b") == rec("id-b", owner="Test Person B")
