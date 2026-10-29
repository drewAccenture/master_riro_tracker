"""The methods the page may call (pywebview js_api). Plain data in and out, no rules here.

pywebview exposes every public attribute, so everything except the eight methods is private.
"""

from datetime import date, datetime

from riro.services.joiners import BAD_DATE, parse_date
from riro.services.sync import FOLDER_LABEL, MESSAGES, SyncResult


def _day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _when(value: datetime | None) -> str | None:
    return None if value is None else value.strftime("%d %b %Y %H:%M")


def _plain(result: SyncResult) -> dict:
    report = None
    if result.report is not None:
        report = {
            "headers_found": list(result.report.headers_found),
            "headers_missing": list(result.report.headers_missing),
            "row_count": result.report.row_count,
        }
    return {
        "state": result.state,
        "message": result.message,
        "files_listed": result.files_listed,
        "files_read": result.files_read,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "skipped": [
            {"name": name, "reason": reason} for name, reason in result.skipped
        ],
        "joiners": result.joiners,
        "joiners_updated": result.joiners_updated,
        "warnings": list(result.warnings),
        "report": report,
        "last_success": _when(result.last_success) or "Never",
    }


def _task_rows(view) -> list[dict]:
    tasks = view.checklist.tasks if view.checklist else ()
    statuses = view.status.tasks if view.status else (None,) * len(tasks)
    return [
        {
            "number": task.number,
            "role": task.role,
            "description": task.description,
            "deadline": task.deadline,
            "status": task.status,
            "completion_date": _day(task.completion_date),
            "track": status.track if status else None,
            "due": _day(status.due) if status else None,
            "days": status.days if status else None,
        }
        for task, status in zip(tasks, statuses, strict=True)
    ]


class Bridge:
    def __init__(
        self,
        sync,
        diagnostics,
        autosync=None,
        data_note=None,
        joiners=None,
        screens=None,
    ):
        self._sync = sync
        self._diagnostics = diagnostics
        self._autosync = autosync
        # ADR-004: "restored from the backup copy" and the like.
        self._data_note = data_note
        self._joiners = joiners  # services.joiners.JoinerService
        self._screens = (
            screens  # services.screens.Screens: display text for the tracker page
        )

    def last_result(self) -> dict:
        last = self._sync.last_result()
        state = _plain(last)
        state["connected"] = self._sync.is_connected()
        state["sign_in_expired"] = last.message == MESSAGES["NeedsSignIn"]
        state["running"] = self._sync.is_running()
        state["folder"] = FOLDER_LABEL
        state["data_note"] = self._data_note
        return state

    def connect(self) -> dict:
        result = self._sync.connect()
        # US-06, US-08: a sign-in that finished turns auto-sync on again, even if its first sync failed.
        finished = result.state not in (
            "sign_in_not_finished",
            "not_connected",
            "syncing",
        )
        if finished and self._autosync is not None:
            self._autosync.start()
        return _plain(result)

    def sync_now(self) -> dict:
        result = self._sync.sync()
        # A Sync now that got through after an expiry brings a stopped auto-sync back.
        got_through = result.state not in ("not_connected", "syncing")
        if got_through and self._autosync is not None and not self._autosync.running():
            self._autosync.start()
        return _plain(result)

    def copy_report(self) -> dict:
        return {"text": self._diagnostics.report()}

    # Joiners (US-03, US-04, US-10). "Status as of" comes from the page as yyyy-mm-dd (Assumption 7).

    def joiners(self, as_of: str) -> dict:
        day = parse_date(as_of)
        if day is None:
            return {"error": BAD_DATE}
        listed = []
        for view in self._joiners.views(day):
            status = view.status
            listed.append(
                {
                    "id": view.joiner.id,
                    "name": view.joiner.name,
                    "roll_on": _day(view.joiner.roll_on),
                    "waiting": view.joiner.roll_on is None,
                    "percent": status.percent if status else None,
                    "delayed_count": status.delayed_count if status else None,
                }
            )
        return {"joiners": listed}

    def joiner(self, joiner_id: str, as_of: str) -> dict:
        day = parse_date(as_of)
        if day is None:
            return {"error": BAD_DATE}
        view = self._joiners.joiner(joiner_id, day)
        if view is None:
            return {"found": False}
        joiner, status = view.joiner, view.status
        result = {
            "found": True,
            "id": joiner.id,
            "name": joiner.name,
            "roll_on": _day(joiner.roll_on),
            "waiting": joiner.roll_on is None,
            "problem": view.problem,
            "read_at": _when(view.read_at),
            "percent": status.percent if status else None,
            "delayed": status.delayed if status else None,
            "delayed_count": status.delayed_count if status else None,
            "counts": dict(status.counts) if status else {},
            "warnings": list(status.warnings) if status else [],
            "skipped_rows": len(view.checklist.skipped_rows) if view.checklist else 0,
            "tasks": _task_rows(view),
        }
        if self._screens is not None:
            result.update(self._screens.joiner_extra(view, day))
        return result

    def overview(self, as_of: str) -> dict:
        day = parse_date(as_of)
        if day is None:
            return {"error": BAD_DATE}
        if self._screens is None:
            return {"error": "The tracker screens are not available."}
        return self._screens.overview(day)

    def set_roll_on(self, joiner_id: str, date: str) -> dict:
        ok, message = self._joiners.set_roll_on(joiner_id, date)
        return {"ok": ok, "message": message}
