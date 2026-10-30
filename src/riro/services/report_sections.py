"""Extra sections of the diagnostic report: recent syncs and data counts (US-16, ADR-007).

Numbers and fixed words only: never a file name, a skip reason, a joiner name or an id.
"""

from riro.services.joiners import is_local
from riro.store.datafile import RESTORED_FROM_BACKUP, STARTED_EMPTY

SYNCS_TITLE = "Recent syncs (newest first):"
DATA_TITLE = "Data:"
_KNOWN_NOTES = (RESTORED_FROM_BACKUP, STARTED_EMPTY)
_RESULTS = ("ok", "partial", "failed")


def _n(value) -> int:
    """A count from the data file; anything else (a hand-edited or old file) shows as 0, never as text."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def sync_run_lines(repo, limit: int = 20) -> list[str]:
    runs = list(reversed(repo.runs()))[:limit]
    return [
        f"{run.at:%Y-%m-%d %H:%M} {run.result if run.result in _RESULTS else 'unknown'}: "
        f"files read {_n(run.files_read)}, updated {_n(run.updated)}, "
        f"unchanged {_n(run.unchanged)}, skipped {len(run.skipped)}"
        for run in runs
    ]


def data_lines(repo, data_note: str | None = None) -> list[str]:
    joiners = repo.joiners()
    visible = [j for j in joiners if not j.hidden]
    waiting = sum(1 for j in visible if j.roll_on is None)
    imported = sum(1 for j in visible if is_local(j.file_id))
    hidden = len(joiners) - len(visible)
    lines = [
        f"joiners {len(visible)}, waiting {waiting}, hidden {hidden}, imported {imported}"
    ]
    if data_note in _KNOWN_NOTES:
        lines.append(f"data note: {data_note}")
    return lines
