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
        "report": report,
        "last_success": (
            result.last_success.strftime("%d %b %Y %H:%M")
            if result.last_success
            else "Never"
        ),
    }


class Bridge:
    def __init__(self, sync, diagnostics):
        self._sync = sync
        self._diagnostics = diagnostics

    def last_result(self) -> dict:
        last = self._sync.last_result()
        state = _plain(last)
        state["connected"] = self._sync.is_connected()
        state["sign_in_expired"] = last.message == MESSAGES["NeedsSignIn"]
        state["running"] = self._sync.is_running()
        state["folder"] = FOLDER_LABEL
        return state

    def connect(self) -> dict:
        return _plain(self._sync.connect())

    def sync_now(self) -> dict:
        return _plain(self._sync.sync())

    def copy_report(self) -> dict:
        return {"text": self._diagnostics.report()}
