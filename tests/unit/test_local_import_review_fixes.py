"""Slice 6 review fixes: US-13, ADR-005 re-upload window, ADR-007 diagnostics. Synthetic files in tmp_path."""

from datetime import datetime

from import_fakes import BROKEN, HEADER, T_IMPORT, write_checklist, write_file
from joiner_fakes import D1, T1, joiner, rec, run
from store_sync_fakes import FakeDiagnostics

from riro.services.diagnostics import Diagnostics
from riro.services.joiners import JoinerService, local_id
from riro.services.local_import import import_paths
from riro.store.repo import Repo

A = "Synthetic Joiner A.xlsx"
NOW = datetime(2026, 10, 30, 9, 0, 0)


def by_id(repo, joiner_id):
    return next(j for j in repo.joiners() if j.id == joiner_id)


def test_adr005_import_does_not_move_a_hidden_joiners_reupload_count(tmp_path):
    repo = Repo.in_memory()
    repo.apply(
        [rec("id-b", owner="Test Person B", present=False)],
        T1,
        run(),
        joiners=[joiner("id-b", name="Test Person B", hidden=True, missing_syncs=1)],
    )
    import_paths([write_checklist(tmp_path, A)], repo, FakeDiagnostics(), T_IMPORT)
    hidden = by_id(repo, "id-b")
    assert (hidden.hidden, hidden.missing_syncs) == (True, 1)


def test_adr005_hidden_dated_joiner_in_the_window_comes_back_on_its_import(tmp_path):
    repo = Repo.in_memory()
    repo.apply(
        [rec("id-a", owner="Test Person A", present=False)],
        T1,
        run(),
        joiners=[joiner("id-a", hidden=True, missing_syncs=1)],
    )
    JoinerService(repo).set_roll_on("id-a", D1.isoformat())
    path = write_checklist(tmp_path, A, owner="Test Person A")
    import_paths([path], repo, FakeDiagnostics(), T_IMPORT)
    back = by_id(repo, "id-a")
    assert (back.hidden, back.file_id, back.roll_on) == (
        False,
        local_id("test person a"),
        D1,
    )
    assert [j.id for j in repo.joiners() if not j.hidden] == ["id-a"]


def test_adr007_import_event_counts_each_skip_reason(tmp_path):
    repo = Repo.in_memory()
    repo.apply([rec("id-sp", owner="Test Person S")], T1, run())
    paths = [
        write_file(tmp_path, "Synthetic notes.txt", b"synthetic"),
        write_file(tmp_path, "Synthetic big.xlsx", b"x" * 200_000),
        write_file(tmp_path, "Synthetic broken.xlsx", BROKEN),
        write_checklist(tmp_path / "h", "Synthetic no headers.xlsx", header=HEADER[1:]),
        write_checklist(tmp_path / "s", "Synthetic S.xlsx", owner="Test Person S"),
    ]
    diagnostics = FakeDiagnostics()
    import_paths(paths, repo, diagnostics, T_IMPORT, max_bytes=100_000)
    [event] = diagnostics.of("local_import")
    assert {k: event[k] for k in event if k.endswith("_count")} == {
        "files_count": 5,
        "added_count": 0,
        "updated_count": 0,
        "skipped_count": 5,
        "not_xlsx_count": 1,
        "too_large_count": 1,
        "unreadable_count": 1,
        "not_checklist_count": 1,
        "in_sharepoint_count": 1,
    }


def test_adr007_the_real_report_names_the_local_import_step(tmp_path):
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    paths = [
        write_checklist(tmp_path, A),
        write_file(tmp_path, "Synthetic notes.txt", b"synthetic"),
    ]
    import_paths(paths, Repo.in_memory(), diagnostics, T_IMPORT)
    lines = [
        line for line in diagnostics.report().splitlines() if "local_import" in line
    ]
    assert len(lines) == 1
    for part in ("result=ok", "files_count=2", "added_count=1", "not_xlsx_count=1"):
        assert part in lines[0]
    assert "synthetic" not in diagnostics.report().lower()
