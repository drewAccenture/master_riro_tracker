"""Builders for the slice 5 screen tests (US-03, US-05, US-11). Synthetic data only, invented names.

A real JoinerService over an in-memory Repo. "Status as of" is 2026-11-05 unless a test says otherwise.
"""

from datetime import date

from joiner_fakes import SIX_TASKS, SKIPPED, T1, joiner, rec, run

from riro.core.models import Task
from riro.services.joiners import JoinerService
from riro.store.repo import Repo

AS_OF = date(2026, 11, 5)
ALPHA_ROLL_ON = date(2026, 11, 2)
BETA_ROLL_ON = date(2026, 11, 9)


def t(
    number,
    deadline,
    status,
    done_on=None,
    role="PMO",
    assigned_id="",
    description=None,
    **extra,
):
    """A Task. extra may hold guidelines (slice 5), so tests without it run before the field exists."""
    return Task(
        row_number=int(number) + 1,
        number=str(number),
        role=role,
        description=description or f"Invented task {number}",
        deadline=deadline,
        status=status,
        completion_date=done_on,
        assigned_id=assigned_id,
        **extra,
    )


# Beta, roll-on 2026-11-09, as of 2026-11-05. index: track, days, bucket.
BETA_TASKS = (
    t(1, "On Roll On", "Not Started"),  # 0: On Track 4, week
    t(2, "10 days Before Roll On", "Not Started", role="Team Member"),  # 1: Delayed -6
    t(
        3,
        "7 days Before Roll On",
        "In Progress",
        role="Hiring Manager",
        assigned_id="invented.manager",
        description="Invented first line\nInvented second line",
    ),  # 2: Delayed -3
    t(4, "6 days Before Roll On", "Completed", date(2026, 11, 1)),  # 3: Completed
    t(5, "3 days Before Roll On", "Not Started"),  # 4: On Track 1, soon
    t(6, "4 days Before Roll On", "Not Started"),  # 5: On Track 0, today
    t(7, "5 days After Roll On", "Not Started", role=""),  # 6: On Track 9, later
)

# Something late on every track, so leaving it out of the totals shows.
HIDDEN_TASKS = (
    t(1, "10 days Before Roll On", "Not Started"),
    t(2, "On Roll On", "Not Started"),
)


def make_service(extra=True, problem=None):
    """Alpha (dated, SIX_TASKS) and Beta (dated, BETA_TASKS); extra adds a waiting and a hidden joiner."""
    records = [
        rec(
            "f-a",
            owner="Alpha Example",
            tasks=SIX_TASKS,
            skipped=SKIPPED,
            problem=problem,
        ),
        rec("f-b", owner="Beta Example", tasks=BETA_TASKS),
    ]
    joiners = [
        joiner("f-a", name="Alpha Example", roll_on=ALPHA_ROLL_ON),
        joiner("f-b", name="Beta Example", roll_on=BETA_ROLL_ON),
    ]
    if extra:
        records += [
            rec("f-w", owner="Waiting Example", tasks=SIX_TASKS),
            rec("f-h", owner="Hidden Example", present=False, tasks=HIDDEN_TASKS),
        ]
        joiners += [
            joiner("f-w", name="Waiting Example"),
            joiner(
                "f-h",
                name="Hidden Example",
                roll_on=ALPHA_ROLL_ON,
                hidden=True,
                missing_syncs=1,
            ),
        ]
    repo = Repo.in_memory()
    repo.apply(records, T1, run(), joiners=joiners)
    return JoinerService(repo)
