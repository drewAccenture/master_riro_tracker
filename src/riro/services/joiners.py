"""Joiners: files -> joiners (ADR-005), roll-on dates (US-03), hidden and returning joiners (US-10).

match_joiners is pure and runs inside each sync, before the one save. Status rules stay in core/status.py.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from riro.core.models import FileRecord, Joiner, JoinerView
from riro.core.status import compute
from riro.store.datafile import SaveFailed

BAD_DATE = "Type the roll-on date as a date, for example 2026-11-02."
UNKNOWN_JOINER = "This joiner is no longer in the list."
DATE_NOT_SAVED = (
    "The roll-on date could not be saved. Close other programs that may use "
    "the tracker's data and click Confirm again."
)
_XLSX = re.compile(r"\.xlsx$", re.IGNORECASE)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_REUPLOAD_WINDOW = 1
_FIRST_YEAR, _LAST_YEAR = 2000, 2099  # ADR-005: the same sync or the next one


LOCAL_PREFIX = (
    "local-"  # US-13: a file imported from the PC, keyed by normalized owner (ADR-005)
)


def local_id(key: str) -> str:
    """The record id of a local import. A hash, so no name reaches an id or the diagnostics log."""
    return LOCAL_PREFIX + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def is_local(file_id: str) -> bool:
    return str(file_id).startswith(LOCAL_PREFIX)


def normalize_owner(text: str) -> str:
    return " ".join(str(text).lower().split())


def parse_date(text) -> date | None:
    """yyyy-mm-dd only (what <input type="date"> sends), years 2000-2099, else None."""
    cleaned = str(text or "").strip()
    if not _ISO_DATE.fullmatch(cleaned):
        return None
    try:
        day = date.fromisoformat(cleaned)
    except ValueError:
        return None
    # A date box sends a half-typed year (e.g. 0002-11-05) while she types; never a real roll-on or as-of date.
    return day if _FIRST_YEAR <= day.year <= _LAST_YEAR else None


def duplicate_warning(other: str, used: str) -> str:
    return f"Two files have the same Checklist Owner: {other} and {used}. Using {used}."


def _display_name(record: FileRecord) -> str:
    return record.checklist.owner.strip() or _XLSX.sub("", record.name)


def owner_key(record: FileRecord) -> str:
    """Normalized Checklist Owner, else the normalized file name (ADR-005). Shared with the local import."""
    return normalize_owner(record.checklist.owner) or normalize_owner(
        _XLSX.sub("", record.name)
    )


def _newest(records: Sequence[FileRecord]) -> FileRecord:
    return max(records, key=lambda r: (r.modified, r.id))


@dataclass(frozen=True)
class Match:
    joiners: tuple[Joiner, ...]
    warnings: tuple[str, ...]
    moved: int
    duplicates: int


def match_joiners(records: Sequence[FileRecord], joiners: Sequence[Joiner]) -> Match:
    usable = [r for r in records if r.present and r.checklist is not None]
    usable_ids = {r.id for r in usable}
    groups: dict[str, list[FileRecord]] = {}
    for record in usable:
        groups.setdefault(owner_key(record), []).append(record)

    winners: dict[str, Joiner] = {}
    taken = {
        j.id for j in joiners
    }  # a new joiner never reuses an id (its first file may now carry another joiner)
    warnings: list[str] = []
    moved = duplicates = 0
    for key, group in groups.items():
        newest = _newest(group)
        ids = {r.id for r in group}
        attached = [j for j in joiners if j.file_id in ids and j.id not in winners]
        # A joiner whose file is gone (re-upload, or the newer duplicate left) in the window.
        returning = [
            j
            for j in joiners
            if j.owner_key == key
            and j.file_id not in usable_ids
            and j.missing_syncs <= _REUPLOAD_WINDOW
            and j.id not in winners
        ]
        candidates = attached + [j for j in returning if not attached or j.roll_on]
        if candidates:
            # A date first, then the joiner she saw last sync, then the one already on the newest file.
            winner = min(
                candidates,
                key=lambda j: (
                    j.roll_on is None,
                    j.hidden,
                    j.file_id != newest.id,
                    j.id,
                ),
            )
            moved += winner not in attached
        else:
            new_id, n = newest.id, 2
            while new_id in taken:
                new_id, n = f"{newest.id}~{n}", n + 1
            taken.add(new_id)
            winner = Joiner(new_id, newest.id, "", key, None, False, 0)
        winners[winner.id] = replace(
            winner,
            file_id=newest.id,
            name=_display_name(newest),
            owner_key=key,
            hidden=False,
            missing_syncs=0,
        )
        for other in (r for r in group if r.id != newest.id):
            warnings.append(duplicate_warning(other.name, newest.name))
            duplicates += 1

    result = dict(winners)
    for joiner in joiners:
        if joiner.id not in result:
            result[joiner.id] = replace(
                joiner, hidden=True, missing_syncs=joiner.missing_syncs + 1
            )
    return Match(
        joiners=tuple(result[jid] for jid in sorted(result)),
        warnings=tuple(warnings),
        moved=moved,
        duplicates=duplicates,
    )


class JoinerService:
    def __init__(self, repo):
        self._repo = repo

    def _view(self, joiner: Joiner, as_of: date) -> JoinerView:
        record = self._repo.file(joiner.file_id)
        checklist = record.checklist if record else None
        status = None
        if joiner.roll_on is not None and checklist is not None:
            status = compute(checklist.tasks, joiner.roll_on, as_of)
        return JoinerView(
            joiner=joiner,
            checklist=checklist,
            status=status,
            problem=record.problem if record else None,
            read_at=record.read_at if record else None,
        )

    def _visible(self) -> list[Joiner]:
        shown = [j for j in self._repo.joiners() if not j.hidden]
        return sorted(shown, key=lambda j: (j.name.casefold(), j.id))

    def views(self, as_of: date) -> tuple[JoinerView, ...]:
        return tuple(self._view(j, as_of) for j in self._visible())

    def waiting(self) -> tuple[Joiner, ...]:
        return tuple(j for j in self._visible() if j.roll_on is None)

    def joiner(self, joiner_id: str, as_of: date) -> JoinerView | None:
        found = [j for j in self._repo.joiners() if j.id == joiner_id]
        return self._view(found[0], as_of) if found else None

    def set_roll_on(self, joiner_id: str, text: str) -> tuple[bool, str]:
        roll_on = parse_date(text)
        if roll_on is None:
            return False, BAD_DATE
        try:
            self._repo.set_roll_on(joiner_id, roll_on)
        except KeyError:
            return False, UNKNOWN_JOINER
        except SaveFailed:
            return (
                False,
                DATE_NOT_SAVED,
            )  # ADR-004: the old file stays; she is told, never left guessing
        return True, ""
