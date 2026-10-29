"""Slice 5a review fixes (US-11, US-10, US-03): the Remarks column, the hidden flag for a joiner the last sync hid,
and "waiting" meaning "no roll-on date".
"""

from joiner_fakes import T1, joiner, rec, run
from screens_fakes import AS_OF, make_service, t

from riro.core.checklist import read
from riro.services.joiners import JoinerService
from riro.services.screens import Screens
from riro.store.repo import Repo


def test_us11_task_rows_carry_the_remarks_text():
    task = t(1, "On Roll On", "Not Started", remarks="Invented remark")
    repo = Repo.in_memory()
    repo.apply(
        [rec("f-x", owner="Remark Example", tasks=(task,))],
        T1,
        run(),
        joiners=[joiner("f-x", name="Remark Example")],
    )
    service = JoinerService(repo)
    rows = Screens(service).joiner_extra(service.joiner("f-x", AS_OF), AS_OF)[
        "task_rows"
    ]
    assert rows[0]["remarks"] == "Invented remark"


def test_us10_joiner_extra_says_when_the_joiner_is_hidden():
    service = make_service()
    screens = Screens(service)
    assert screens.joiner_extra(service.joiner("f-h", AS_OF), AS_OF)["hidden"] is True
    assert screens.joiner_extra(service.joiner("f-a", AS_OF), AS_OF)["hidden"] is False


def test_us03_dated_joiner_without_a_read_file_is_not_listed_as_waiting():
    repo = Repo.in_memory()
    repo.apply(
        [rec("f-a", owner="Alpha Example")],
        T1,
        run(),
        joiners=[
            joiner("f-gone", file_id="f-missing", name="Dated Example", roll_on=AS_OF)
        ],
    )
    sidebar = Screens(JoinerService(repo)).overview(AS_OF)["sidebar"]
    assert sidebar["waiting"] == []


def test_us11_missing_guidelines_column_in_the_file_gives_empty_text(make_xlsx):
    header = [
        "Checklist Owner",
        "Role",
        "Task Number",
        "Description",
        "Completion Status",
        "Completion Date",
        "Deadline",
    ]
    row = [
        "Test Person A",
        "PMO",
        1,
        "Invented task 1",
        "Not Started",
        None,
        "On Roll On",
    ]
    checklist = read(make_xlsx([("Roll-In Checklist", [header, row])]))
    assert checklist.headers_missing == ()
    assert checklist.tasks[0].guidelines == ""
