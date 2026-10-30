"""US-16, ADR-007: names, ids and tokens fed through records, joiners, runs, events and the load note never reach
the full report once the slice 7a sections are wired. Counts do. Synthetic data only.
"""

from datetime import datetime

from joiner_fakes import joiner, rec

from riro.core.models import SyncRun
from riro.services import report_sections
from riro.services.diagnostics import Diagnostics
from riro.services.joiners import local_id
from riro.store.repo import Repo

DATA_TITLE = report_sections.DATA_TITLE
SYNCS_TITLE = report_sections.SYNCS_TITLE
data_lines = report_sections.data_lines
sync_run_lines = report_sections.sync_run_lines
NOW = datetime(2026, 10, 30, 10, 0, 0)
NAME_A = "Zz Synthetic Joiner A"
NAME_B = "Zz Synthetic Joiner B"
FILE_A = f"{NAME_A}.xlsx"
FILE_B = f"{NAME_B} Checklist.xlsx"
ENTERPRISE_ID = "zz.synthetic.joiner"
TOKEN = "Bearer eyJZZSECRET"
FORBIDDEN = [
    NAME_A,
    NAME_B,
    "Synthetic Joiner",
    "Zz Synthetic",
    FILE_A,
    FILE_B,
    ".xlsx",
    ENTERPRISE_ID,
    TOKEN,
    "eyJ",
    "ZZSECRET",
    "Bearer",
    "local-",
]


def build_repo():
    repo = Repo.in_memory()
    records = [
        rec("id-a", owner=NAME_A, name=FILE_A, problem=f"{ENTERPRISE_ID} {TOKEN}"),
        rec("id-b", owner=NAME_B, name=FILE_B),
    ]
    joiners = [
        joiner("id-a", name=NAME_A, owner_key=ENTERPRISE_ID, roll_on=NOW.date()),
        joiner("id-b", name=NAME_B),  # waiting
        joiner(
            "id-c",
            file_id=local_id(ENTERPRISE_ID),
            name=TOKEN,
            roll_on=NOW.date(),
        ),  # imported
        joiner("id-d", name=f"{NAME_A} Old", hidden=True),
    ]
    skipped = ((FILE_B, f"{ENTERPRISE_ID} could not read {TOKEN}"),)
    repo.apply(
        records,
        NOW,
        SyncRun(datetime(2026, 10, 30, 9, 0, 0), "partial", 2, 1, 0, skipped),
        joiners=joiners,
    )
    return repo


def build_report(tmp_path):
    repo = build_repo()
    note = f"{NAME_A} {ENTERPRISE_ID} {TOKEN}"
    diag = Diagnostics(tmp_path, versions={"app": "0.1.0-test"}, now=lambda: NOW)
    try:
        diag.add_section(SYNCS_TITLE, lambda: sync_run_lines(repo))
        diag.add_section(DATA_TITLE, lambda: data_lines(repo, note))
        diag.event("sign_in", result="ok", user=ENTERPRISE_ID, token=TOKEN)
        diag.event("renewal", result="failed", error_kind=TOKEN, duration_s=4.5)
        diag.event("sync", result="ok", note=NAME_A, files_count=2)
        return diag.report()
    finally:
        diag.close()


def test_adr007_no_name_id_or_token_reaches_the_full_report(tmp_path):
    text = build_report(tmp_path)
    for secret in FORBIDDEN:
        assert secret not in text, secret


def test_us16_full_report_has_the_counts(tmp_path):
    lines = build_report(tmp_path).splitlines()
    assert lines[lines.index(SYNCS_TITLE) + 1] == (
        "2026-10-30 09:00 partial: files read 2, updated 1, unchanged 0, skipped 1"
    )
    assert lines[lines.index(DATA_TITLE) + 1 : lines.index(DATA_TITLE) + 3] == [
        "joiners 3, waiting 1, hidden 1, imported 1",
        "",
    ]
    summary = lines.index("Sign-in summary (last 7 days):")
    assert lines[summary + 1] == (
        "2026-10-30: visible sign-ins 1 (failed 0), silent renewals 1 (failed 1), longest renewal 4.5 s"
    )
    assert (
        summary
        < lines.index(SYNCS_TITLE)
        < lines.index(DATA_TITLE)
        < lines.index("Recent steps:")
    )
