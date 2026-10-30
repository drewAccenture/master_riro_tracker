"""Write a synthetic tracker.json for the slice 5 visual check (docs/plans/plan-slice5-ui-port.md, section 6).

Usage: .venv\\Scripts\\python.exe tools\\make_demo_data.py <empty folder>
Then start the app with RIRO_DATA_DIR=<that folder>. Invented names and tasks only, never real checklist data.
The folder gets no edge_profile, so the app opens without a sign-in and without Edge.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from riro.core.models import (
    Checklist,
    FileRecord,
    Joiner,
    SkippedRow,
    SyncRun,
    Task,
)
from riro.store.datafile import DataFile
from riro.store.repo import Repo, check_layout

# (deadline, status, days after roll-on it was completed, role, assigned id, description, guidelines, remarks)
ALPHA = [
    (
        "10 days Before Roll On",
        "Completed",
        -12,
        "PMO",
        "demo.pmo.one",
        "Invented setup task\nMore detail here.",
        "Invented guideline",
        "",
    ),
    (
        "1 days Before Roll On",
        "Completed",
        1,
        "Supervisor",
        "demo.lead.one",
        "Invented welcome call",
        "",
        "Done after the start",
    ),
    (
        "On Roll On",
        "Not Started",
        None,
        "Team Member",
        "",
        "Invented first-day form",
        "Fill in the form.",
        "",
    ),
    (
        "1 days After Roll On",
        "In Progress",
        None,
        "Team Member",
        "",
        "Invented laptop check",
        "",
        "",
    ),
    (
        "3 days After Roll On",
        "Not Started",
        None,
        "PMO",
        "demo.pmo.one",
        "Invented access request",
        "",
        "",
    ),
    (
        "5 days After Roll On",
        "Not Applicable",
        None,
        "Training Representative",
        "demo.trainer.one",
        "Invented optional course",
        "",
        "",
    ),
    (
        "10 days After Roll On",
        "Not Started",
        None,
        "Team Member",
        "",
        "Invented training plan",
        "",
        "",
    ),
    (
        "whenever it suits",
        "Not Started",
        None,
        "Team Member",
        "",
        "Invented task with an unclear deadline",
        "",
        "",
    ),
]
BETA = [
    (
        "10 days Before Roll On",
        "Completed",
        -11,
        "PMO",
        "demo.pmo.two",
        "Invented seat booking",
        "",
        "",
    ),
    (
        "On Roll On",
        "Not Started",
        None,
        "Team Member",
        "",
        "Invented badge photo",
        "",
        "",
    ),
    (
        "1 days After Roll On",
        "Not Started",
        None,
        "Supervisor",
        "demo.lead.two",
        "Invented team intro",
        "",
        "",
    ),
    (
        "5 days After Roll On",
        "Not Started",
        None,
        "Team Member",
        "",
        "Invented safety course",
        "",
        "",
    ),
    (
        "30 days After Roll On",
        "Not Started",
        None,
        "Project Manager",
        "demo.pm.two",
        "Invented 30-day review",
        "",
        "",
    ),
]


def _checklist(
    owner: str, rows: list[tuple], roll_on: date | None, skipped: bool
) -> Checklist:
    tasks = []
    for number, (
        deadline,
        status,
        done_after,
        role,
        who,
        text,
        guide,
        remarks,
    ) in enumerate(rows, 1):
        done_on = None
        if done_after is not None and roll_on is not None:
            done_on = roll_on + timedelta(days=done_after)
        tasks.append(
            Task(
                row_number=number + 1,
                number=str(number),
                role=role,
                description=text,
                deadline=deadline,
                status=status,
                completion_date=done_on,
                assigned_id=who,
                remarks=remarks,
                guidelines=guide,
            )
        )
    gaps = (
        (SkippedRow(len(rows) + 2, "no task number or description"),) if skipped else ()
    )
    return Checklist("Roll-In Checklist", owner, tuple(tasks), gaps, (), 0)


def main(folder: Path) -> int:
    path = folder / "data" / "tracker.json"
    if path.exists():
        print(f"{path} already exists. Use an empty folder.", file=sys.stderr)
        return 1
    today = date.today()
    now = datetime.now().replace(microsecond=0)
    alpha_on, beta_on = today - timedelta(days=3), today + timedelta(days=1)
    people = [
        ("demo-a", "Demo Joiner Alpha", ALPHA, alpha_on, True),
        ("demo-b", "Demo Joiner Beta", BETA, beta_on, False),
        ("demo-c", "Demo Joiner Gamma", BETA, None, False),
    ]
    records, joiners = [], []
    for file_id, name, rows, roll_on, skipped in people:
        checklist = _checklist(name, rows, roll_on or today, skipped)
        records.append(
            FileRecord(
                file_id,
                f"{name}.xlsx",
                f"e-{file_id}",
                now.isoformat(),
                True,
                checklist,
                now,
                None,
            )
        )
        joiners.append(Joiner(file_id, file_id, name, name.lower(), None, False, 0))
    repo = Repo(DataFile(path, validate=check_layout))
    repo.apply(records, now, SyncRun(now, "ok", 3, 3, 0, ()), joiners=joiners)
    for file_id, _, _, roll_on, _ in people:
        if roll_on is not None:
            repo.set_roll_on(file_id, roll_on)
    print(f"Synthetic demo data written to {path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
