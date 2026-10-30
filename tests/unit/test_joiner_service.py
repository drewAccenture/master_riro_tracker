"""US-03, US-04, US-10: JoinerService lists joiners, the waiting list, one joiner's status, and sets the roll-on date.

A real Repo (in memory or on tmp_path), seeded through Repo.apply(..., joiners=...). Dates are passed in.
"""

from datetime import date

import pytest
from joiner_fakes import D1, D2, SIX_TASKS, SKIPPED, T1, joiner, rec, run

from riro.core.models import JoinerView
from riro.core.status import compute
from riro.services.joiners import BAD_DATE, UNKNOWN_JOINER, JoinerService
from riro.store.datafile import DataFile, MemoryDataFile
from riro.store.repo import Repo

AS_OF = date(2026, 11, 5)


def seeded(datafile=None):
    repo = Repo(datafile if datafile is not None else MemoryDataFile())
    records = [
        rec("f-z", owner="Zeta Person", tasks=SIX_TASKS),
        rec("f-a", owner="alpha Person", tasks=SIX_TASKS, skipped=SKIPPED),
        rec("f-b", owner="Beta Person", problem="synthetic reason"),
        rec("f-h", owner="Hidden Person", present=False),
    ]
    joiners = [
        joiner("f-z", name="Zeta Person"),
        joiner("f-a", name="alpha Person"),
        joiner("f-b", name="Beta Person"),
        joiner("f-h", name="Hidden Person", hidden=True, missing_syncs=1),
    ]
    repo.apply(records, T1, run(), joiners=joiners)
    return repo


def test_us03_new_constants_text():
    assert BAD_DATE == "Type the roll-on date as a date, for example 2026-11-02."
    assert UNKNOWN_JOINER == "This joiner is no longer in the list."


def test_us10_views_lists_visible_joiners_sorted_by_name_ignoring_case():
    views = JoinerService(seeded()).views(AS_OF)
    assert isinstance(views, tuple)
    assert all(isinstance(v, JoinerView) for v in views)
    assert [v.joiner.name for v in views] == [
        "alpha Person",
        "Beta Person",
        "Zeta Person",
    ]


def test_us03_waiting_lists_visible_joiners_without_a_date_sorted_by_name():
    repo = seeded()
    service = JoinerService(repo)
    assert [j.id for j in service.waiting()] == ["f-a", "f-b", "f-z"]
    assert service.set_roll_on("f-b", "2026-11-02") == (True, "")
    assert [j.id for j in service.waiting()] == ["f-a", "f-z"]
    assert isinstance(service.waiting(), tuple)


def test_us03_waiting_joiner_has_no_status_yet():
    view = JoinerService(seeded()).joiner("f-a", AS_OF)
    assert view.status is None
    assert view.joiner.roll_on is None
    assert view.checklist is not None
    assert len(view.checklist.tasks) == 6


def test_us04_status_comes_from_core_status_with_the_roll_on_and_as_of():
    repo = seeded()
    service = JoinerService(repo)
    service.set_roll_on("f-a", "2026-11-02")
    view = service.joiner("f-a", AS_OF)
    assert view.status == compute(SIX_TASKS, D1, AS_OF)
    assert view.status.counts == {
        "Delayed": 1,
        "On Track": 1,
        "Completed": 1,
        "Completed Late": 1,
        "N/A": 1,
        "Deadline unclear": 1,
    }
    assert (view.status.percent, view.status.delayed_count) == (40, 1)
    assert view.joiner.roll_on == D1


def test_us09_view_has_problem_and_read_at_from_the_file_record():
    service = JoinerService(seeded())
    view = service.joiner("f-b", AS_OF)
    assert (view.problem, view.read_at) == ("synthetic reason", T1)
    assert service.joiner("f-a", AS_OF).problem is None


def test_us03_unknown_joiner_is_none():
    assert JoinerService(seeded()).joiner("no-such-id", AS_OF) is None


def test_us03_set_roll_on_saves_at_once_and_the_next_view_uses_it():
    repo = seeded()
    service = JoinerService(repo)
    assert service.set_roll_on("f-a", "2026-11-02") == (True, "")
    assert [j.roll_on for j in repo.joiners() if j.id == "f-a"] == [D1]
    assert service.views(AS_OF)[0].status.delayed_count == 1


def test_us03_changed_date_updates_deadlines_and_statuses_right_away():
    service = JoinerService(seeded())
    service.set_roll_on("f-a", "2026-11-02")
    before = service.joiner("f-a", AS_OF).status
    assert service.set_roll_on("f-a", "2026-11-09") == (True, "")
    after = service.joiner("f-a", AS_OF).status
    assert after == compute(SIX_TASKS, D2, AS_OF)
    assert after != before
    assert after.counts["Delayed"] == 0
    assert after.counts["On Track"] == 2
    assert service.joiner("f-a", AS_OF).joiner.roll_on == D2


def test_us03_set_roll_on_accepts_surrounding_spaces():
    service = JoinerService(seeded())
    assert service.set_roll_on("f-z", "  2026-11-02 ") == (True, "")
    assert service.joiner("f-z", AS_OF).joiner.roll_on == D1


@pytest.mark.parametrize(
    "text", ["", "   ", "02/11/2026", "2026-13-01", "2 Nov 2026", "next monday"]
)
def test_us03_set_roll_on_rejects_anything_but_a_date(text):
    repo = seeded()
    service = JoinerService(repo)
    service.set_roll_on("f-a", "2026-11-02")
    assert service.set_roll_on("f-a", text) == (False, BAD_DATE)
    assert service.joiner("f-a", AS_OF).joiner.roll_on == D1


def test_us03_set_roll_on_for_an_unknown_joiner():
    repo = seeded()
    before = repo.joiners()
    assert JoinerService(repo).set_roll_on("no-such-id", "2026-11-02") == (
        False,
        UNKNOWN_JOINER,
    )
    assert repo.joiners() == before


class CountingDataFile:
    def __init__(self):
        self.inner = MemoryDataFile()
        self.saves = 0

    def load(self):
        return self.inner.load()

    def save(self, data):
        self.saves += 1
        self.inner.save(data)


def test_us03_set_roll_on_is_one_save_and_a_bad_date_saves_nothing():
    datafile = CountingDataFile()
    service = JoinerService(seeded(datafile))
    saves = datafile.saves
    service.set_roll_on("f-a", "2026-11-02")
    assert datafile.saves == saves + 1
    service.set_roll_on("f-a", "not a date")
    service.set_roll_on("no-such-id", "2026-11-02")
    assert datafile.saves == saves + 1


def test_us03_roll_on_survives_an_app_restart(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    JoinerService(seeded(DataFile(path))).set_roll_on("f-a", "2026-11-02")
    restarted = JoinerService(Repo(DataFile(path)))
    assert restarted.joiner("f-a", AS_OF).joiner.roll_on == D1
    assert [j.id for j in restarted.waiting()] == ["f-b", "f-z"]
