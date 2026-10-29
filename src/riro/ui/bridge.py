"""The methods the page may call (pywebview js_api). Plain data in and out, no rules here.

pywebview exposes every public attribute, so everything except the four methods is private.
"""

from riro.services.sync import FOLDER_LABEL, MESSAGES, SyncResult


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
        "report": report,
        "last_success": (
            result.last_success.strftime("%d %b %Y %H:%M")
            if result.last_success
            else "Never"
        ),
    }


class Bridge:
    def __init__(self, sync, diagnostics, autosync=None, data_note=None):
        self._sync = sync
        self._diagnostics = diagnostics
        self._autosync = autosync
        self._data_note = (
            data_note  # ADR-004: "restored from the backup copy" and the like
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
