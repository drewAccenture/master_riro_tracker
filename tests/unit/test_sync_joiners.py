"""US-02, US-07, ADR-005: a sync turns files into joiners, says "N joiners" in the summary, passes duplicate warnings
and gives diagnostics counts without names. Fake folder, in-memory Repo, no Edge."""

from datetime import datetime

import pytest
from store_sync_fakes import Clock, FakeDiagnostics, Folder, Wall

from riro.connectors.sharepoint import errors
from riro.services.joiners import JoinerService, duplicate_warning
from riro.services.sync import SyncService
from riro.store.repo import Repo

T1 = datetime(2026, 10, 29, 9, 0, 0)
A, B, C = (
    "Synthetic Joiner A.xlsx",
    "Synthetic Joiner B.xlsx",
    "Synthetic Joiner C.xlsx",
)
BROKEN = b"PK\x03\x04 broken synthetic bytes"


@pytest.fixture
def owner_file(make_checklist, make_row):
    def _make(owner):
        return make_checklist(
            [
                make_row(1, "Invented task one", owner=owner),
                make_row(2, "Invented task two", status="Completed", owner=owner),
            ]
        )

    return _make


def make(folder):
    diagnostics, repo = FakeDiagnostics(), Repo.in_memory()
    service = SyncService(folder, diagnostics, repo=repo, clock=Clock(), now=Wall(T1))
    return service, repo, diagnostics


def test_us07_sync_result_counts_joiners_and_updated_joiners(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    folder.put("id-b", B, owner_file("Test Person B"))
    service, repo, _ = make(folder)
    first = service.sync()
    assert first.message == "Sync OK: 2 joiners (2 updated, 0 unchanged)."
    assert (first.joiners, first.joiners_updated, first.warnings) == (2, 2, ())
    assert [j.id for j in repo.joiners()] == ["id-a", "id-b"]
    second = service.sync()
    assert second.message == "Sync OK: 2 joiners (0 updated, 2 unchanged)."
    assert (second.joiners, second.joiners_updated) == (2, 0)


def test_us07_one_joiner_is_singular(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    result = make(folder)[0].sync()
    assert result.message == "Sync OK: 1 joiner (1 updated, 0 unchanged)."


def test_us07_partly_worked_counts_joiners_and_skipped_files(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    folder.put("id-b", B, BROKEN)
    folder.put("id-c", C, owner_file("Test Person C"))
    result = make(folder)[0].sync()
    assert result.state == "ok"
    assert (
        result.message
        == "Sync partly worked: 2 joiners (2 updated). 1 file was skipped."
    )
    assert (result.joiners, result.joiners_updated) == (2, 2)


def test_us07_hidden_joiners_are_not_counted(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    folder.put("id-b", B, owner_file("Test Person B"))
    service, repo, _ = make(folder)
    service.sync()
    folder.remove("id-b")
    result = service.sync()
    assert result.message == "Sync OK: 1 joiner (0 updated, 1 unchanged)."
    assert [(j.id, j.hidden) for j in repo.joiners()] == [
        ("id-a", False),
        ("id-b", True),
    ]


def test_us02_duplicate_owner_warns_without_making_the_sync_partly(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"), modified="2026-10-21T08:00:00Z")
    folder.put(
        "id-b", B, owner_file(" test  person A"), modified="2026-10-22T08:00:00Z"
    )
    service, repo, diagnostics = make(folder)
    result = service.sync()
    assert result.state == "ok"
    assert result.message == "Sync OK: 1 joiner (1 updated, 0 unchanged)."
    assert result.warnings == (duplicate_warning(A, B),)
    assert repo.runs()[-1].result == "ok"
    assert [(j.file_id, j.hidden) for j in repo.joiners()] == [("id-b", False)]
    assert diagnostics.of("sync")[-1]["duplicate_count"] == 1


def test_adr005_sync_event_has_joiner_counts_and_no_names(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    folder.put("id-b", B, owner_file("Test Person B"))
    service, repo, diagnostics = make(folder)
    service.sync()
    JoinerService(repo).set_roll_on("id-a", "2026-11-02")
    folder.remove("id-a")
    folder.put("id-new", "Synthetic Joiner A again.xlsx", owner_file("Test Person A"))
    service.sync()
    event = diagnostics.of("sync")[-1]
    assert (
        event["joiners_count"],
        event["waiting_count"],
        event["moved_count"],
        event["duplicate_count"],
    ) == (2, 1, 1, 0)
    text = repr(diagnostics.events)
    assert "Test Person" not in text
    assert "Synthetic Joiner" not in text


def test_adr005_first_sync_event_counts_waiting_joiners(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    service, _, diagnostics = make(folder)
    service.sync()
    event = diagnostics.of("sync")[-1]
    assert (event["joiners_count"], event["waiting_count"], event["moved_count"]) == (
        1,
        1,
        0,
    )


def test_us07_failed_sync_leaves_the_joiners_alone(owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    service, repo, _ = make(folder)
    service.sync()
    JoinerService(repo).set_roll_on("id-a", "2026-11-02")
    before = repo.joiners()
    folder.fail["list_files"] = errors.Unreachable()
    result = service.sync()
    assert result.state == "failed"
    assert result.warnings == ()
    assert repo.joiners() == before


def test_us02_never_read_file_gives_no_joiner_after_a_sync(owner_file):
    folder = Folder()
    folder.put("id-a", A, BROKEN)
    service, repo, _ = make(folder)
    result = service.sync()
    assert (
        result.message
        == "Sync partly worked: 0 joiners (0 updated). 1 file was skipped."
    )
    assert repo.joiners() == ()
