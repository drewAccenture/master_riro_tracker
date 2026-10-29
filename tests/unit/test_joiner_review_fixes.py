"""Slice 4 review fixes (ADR-005, US-03, ADR-004): no joiner id collision when an owner correction splits a
duplicate pair, a failed date save is reported in plain words, and the visible dated joiner keeps winning.
"""

import pytest
from joiner_fakes import D1, D2, joiner, rec

from riro.services.joiners import DATE_NOT_SAVED, JoinerService, match_joiners
from riro.store.datafile import SaveFailed
from riro.store.repo import Repo


@pytest.mark.parametrize("order", [("f1", "f2"), ("f2", "f1")])
def test_adr005_owner_correction_that_splits_a_duplicate_pair_gives_two_joiners(order):
    # J f1 (dated) moved to the newer duplicate f2. Now f2's owner is corrected to another person.
    by_id = {
        "f1": rec("f1", owner="Test Person A", modified="2026-10-20T08:00:00Z"),
        "f2": rec("f2", owner="Test Person B", modified="2026-10-25T08:00:00Z"),
    }
    records = [by_id[file_id] for file_id in order]
    stored = [joiner("f1", file_id="f2", name="Test Person A", roll_on=D1)]

    match = match_joiners(records, stored)

    visible = {j.file_id: j for j in match.joiners if not j.hidden}
    assert set(visible) == {"f1", "f2"}
    assert visible["f2"].id == "f1"  # the dated joiner stays on the file it was reading
    assert visible["f2"].roll_on == D1
    # Person A's file gets its own, new, waiting joiner.
    assert visible["f1"].roll_on is None
    assert visible["f1"].id != "f1"
    assert len({j.id for j in match.joiners}) == len(match.joiners)


def test_adr005_visible_dated_joiner_keeps_its_date_when_its_newer_file_leaves():
    # J1 (D1) won the tie on the newer f1; J2 (D2) lost it and is hidden but still on the older f2.
    records = [
        rec("f1", modified="2026-10-25T08:00:00Z", present=False),
        rec("f2", modified="2026-10-20T08:00:00Z"),
    ]
    stored = [
        joiner("j1", file_id="f1", roll_on=D1),
        joiner("j2", file_id="f2", roll_on=D2, hidden=True, missing_syncs=3),
    ]
    by_id = {j.id: j for j in match_joiners(records, stored).joiners}
    assert by_id["j1"].hidden is False
    assert by_id["j1"].file_id == "f2"
    assert by_id["j1"].roll_on == D1
    assert by_id["j2"].hidden is True


class RefusingRepo(Repo):
    def set_roll_on(self, joiner_id, roll_on):
        raise SaveFailed("synthetic: data file held by another program")


def test_adr004_roll_on_that_cannot_be_saved_is_reported_in_plain_words():
    repo = RefusingRepo.in_memory()
    service = JoinerService(repo)
    assert service.set_roll_on("f-a", "2026-11-02") == (False, DATE_NOT_SAVED)


def test_adr004_date_not_saved_message_is_plain_words():
    assert DATE_NOT_SAVED == (
        "The roll-on date could not be saved. Close other programs that may use "
        "the tracker's data and click Confirm again."
    )
