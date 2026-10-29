"""ADR-005, US-03: a dated joiner whose newer duplicate file left the folder comes back on the older file.

Gap found while writing the slice 4 tests: the older file's own undated joiner must not win and hide the date.
"""

from joiner_fakes import D1, joiner, rec

from riro.services.joiners import match_joiners


def test_us03_dated_joiner_moves_back_to_the_older_file_when_the_newer_one_leaves():
    records = [
        rec("f-old", modified="2026-10-20T08:00:00Z"),
        rec("f-new", modified="2026-10-25T08:00:00Z", present=False),
    ]
    # j-dated was reading the newer duplicate; f-old is the older file's own joiner, which lost the tie.
    stored = [
        joiner("j-dated", file_id="f-new", roll_on=D1),
        joiner("f-old", hidden=True, missing_syncs=1),
    ]
    match = match_joiners(records, stored)
    by_id = {j.id: j for j in match.joiners}
    assert by_id["j-dated"].file_id == "f-old"
    assert by_id["j-dated"].roll_on == D1
    assert by_id["j-dated"].hidden is False
    assert by_id["f-old"].hidden is True
    assert match.moved == 1


def test_us03_undated_hidden_joiner_does_not_take_over_a_file_that_has_a_joiner():
    records = [rec("f-a")]
    stored = [
        joiner("f-a"),
        joiner("j-gone", file_id="f-gone", hidden=True, missing_syncs=0),
    ]
    match = match_joiners(records, stored)
    by_id = {j.id: j for j in match.joiners}
    assert by_id["f-a"].hidden is False
    assert by_id["j-gone"].hidden is True
    assert match.moved == 0
