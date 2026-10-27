"""Slice 1 sync: connect, sync on start, Sync now, one sync at a time, plain-word errors (US-01, US-07, ADR-003).

Nobody waits on a lock: a second sync while one runs returns "Syncing..." at once. A watchdog kills Edge when a
sync runs past the whole-sync limit, so a stuck call ends instead of waiting for its own limit.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from riro.connectors.sharepoint.client import FOLDER_PATH
from riro.connectors.sharepoint.errors import (
    ConnectorError,
    EdgeNotStarted,
    NeedsSignIn,
    TimedOut,
)
from riro.core.checklist import UnreadableFile, check_headers
from riro.core.models import HeaderReport

SYNC_LIMIT_S = 180.0  # ADR-003: whole sync
SIGN_IN_NOT_FINISHED = (
    "The sign-in did not finish. Click Connect to SharePoint to try again."
)
SYNCING = "Syncing..."
NOT_CONNECTED = "SharePoint: Not connected"
UNREADABLE_FILE = (
    "The checklist file could not be read. It may be open, broken or not an .xlsx file."
)
EDGE_NOT_STARTED = "Microsoft Edge could not be started. Click Sync now to try again."
UNEXPECTED = (
    "Something went wrong. Click Copy diagnostic report and send it to the maintainer."
)
FOLDER_LABEL = " / ".join(FOLDER_PATH.split("/")[3:])

MESSAGES = {
    "NeedsSignIn": "Your SharePoint sign-in has expired. Click Sign in again.",
    "NoAccess": "You do not have access to the folder. Ask the folder owner for read access.",
    "NotFound": "The folder was not found. It may have been moved or renamed.",
    "Unreachable": "SharePoint could not be reached. Check your network or VPN.",
    # Slice 1 has no timer. Back to "The app will try again in 5 minutes." (US-07) with the US-06 timer.
    "TimedOut": "SharePoint did not answer in time. Click Sync now to try again.",
    "EdgeMissing": "Microsoft Edge was not found. Install Microsoft Edge and try again.",
}


def message_for(error: ConnectorError) -> str:
    """Plain words for the error kind. The error's own text is never shown."""
    if isinstance(error, EdgeNotStarted):
        return EDGE_NOT_STARTED
    return MESSAGES.get(type(error).kind, MESSAGES["Unreachable"])


@dataclass(frozen=True)
class SyncResult:
    state: str  # "ok", "failed", "syncing", "not_connected", "sign_in_not_finished"
    message: str
    files_listed: int = 0
    report: HeaderReport | None = None
    last_success: datetime | None = None


class _OverLimit(Exception):
    pass


class SyncService:
    def __init__(
        self,
        connector,
        diagnostics,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
        limit_s: float = SYNC_LIMIT_S,
    ):
        self._connector = connector
        self._diagnostics = diagnostics
        self._clock = clock
        self._now = now
        self._limit_s = limit_s
        self._running = threading.Lock()
        self._overran = threading.Event()
        self._current_run: object | None = None
        self._last_success: datetime | None = None
        self._last = SyncResult("not_connected", NOT_CONNECTED)

    def last_result(self) -> SyncResult:
        return self._last

    def is_running(self) -> bool:
        return self._running.locked()

    def is_connected(self) -> bool:
        """A sync has worked, and the last one did not end in "sign in again"."""
        return self._last_success is not None and self._last.state != "not_connected"

    def _syncing(self) -> SyncResult:
        return SyncResult("syncing", SYNCING, last_success=self._last_success)

    def sync(self) -> SyncResult:
        if not self._running.acquire(blocking=False):
            return self._syncing()
        try:
            self._last = self._run()
            return self._last
        finally:
            self._running.release()

    def connect(self) -> SyncResult:
        """Visible sign-in, then a first sync. A sign-in that does not finish changes nothing (US-01)."""
        if not self._running.acquire(blocking=False):
            return self._syncing()
        try:
            try:
                self._connector.sign_in()
            except ConnectorError as error:
                self._diagnostics.event(
                    "sign_in", result="failed", error_kind=error.kind
                )
                return SyncResult(
                    "sign_in_not_finished",
                    SIGN_IN_NOT_FINISHED,
                    last_success=self._last_success,
                )
            except Exception as error:  # noqa: BLE001 - plain words for her; the report gets the type only
                self._diagnostics.event(
                    "sign_in",
                    result="failed",
                    error_kind="Unexpected",
                    exception=type(error).__name__,
                )
                return SyncResult("failed", UNEXPECTED, last_success=self._last_success)
            self._last = self._run()
            return self._last
        finally:
            self._running.release()

    def shutdown(self) -> None:
        """App exit: the connector closes Edge politely."""
        self._connector.shutdown()

    # --- one sync ------------------------------------------------------------------------------------------

    def _ping(self) -> None:
        started = self._clock()
        try:
            self._connector.health_ping()
        except EdgeNotStarted:
            raise  # its 3 attempts are already used up (ADR-009)
        except TimedOut:
            # ADR-003: the connector killed the stuck Edge; try once more with a fresh one.
            self._diagnostics.event(
                "health_ping", result="failed", error_kind="TimedOut"
            )
            self._connector.health_ping()
        self._diagnostics.event(
            "health_ping", result="ok", duration_s=self._clock() - started
        )

    def _overrun(self, run: object) -> None:
        if run is not self._current_run:
            return  # a late timer from a sync that already ended
        self._overran.set()
        self._connector.close()  # kills Edge, also one still starting; the call in progress fails at once

    def _run(self) -> SyncResult:
        started = self._clock()
        self._overran.clear()
        run = self._current_run = object()
        watchdog = threading.Timer(self._limit_s, self._overrun, args=(run,))
        watchdog.daemon = True
        watchdog.start()

        def within_limit() -> None:
            if self._clock() - started > self._limit_s:
                raise _OverLimit()

        files: list[dict] = []
        exception = None
        try:
            self._ping()
            within_limit()
            files = self._connector.list_files()
            within_limit()
            checklists = [f for f in files if str(f["name"]).lower().endswith(".xlsx")]
            report = None
            if checklists:
                data = self._connector.download(checklists[0]["id"])
                within_limit()
                report = check_headers(data)
                self._diagnostics.event(
                    "header_check", result="ok", rows_count=report.row_count
                )
                self._diagnostics.file_report(1, len(checklists), report)
            self._last_success = self._now()
            result = SyncResult(
                "ok",
                f"Sync OK: {len(files)} files listed, {len(checklists)} checklists.",
                files_listed=len(files),
                report=report,
                last_success=self._last_success,
            )
            kind = None
        except _OverLimit:
            self._connector.close()
            kind = TimedOut.kind
            result = self._failed("failed", MESSAGES[kind], files)
        except ConnectorError as error:
            if self._overran.is_set():
                kind = TimedOut.kind
                result = self._failed("failed", MESSAGES[kind], files)
            elif isinstance(error, NeedsSignIn):
                kind = error.kind
                result = self._failed("not_connected", message_for(error), files)
            else:
                kind = error.kind
                result = self._failed("failed", message_for(error), files)
        except UnreadableFile:
            kind = "UnreadableFile"
            result = self._failed("failed", UNREADABLE_FILE, files)
        except Exception as error:  # noqa: BLE001 - reported in plain words; the report gets the type only
            if self._overran.is_set():
                kind = TimedOut.kind
                result = self._failed("failed", MESSAGES[kind], files)
            else:
                kind = "Unexpected"
                exception = type(error).__name__
                result = self._failed("failed", UNEXPECTED, files)
        finally:
            watchdog.cancel()
            self._current_run = None
        self._diagnostics.event(
            "sync",
            result="ok" if kind is None else "failed",
            error_kind=kind,
            exception=exception,
            files_count=len(files),
            duration_s=self._clock() - started,
        )
        return result

    def _failed(self, state: str, message: str, files: list[dict]) -> SyncResult:
        return SyncResult(
            state, message, files_listed=len(files), last_success=self._last_success
        )
