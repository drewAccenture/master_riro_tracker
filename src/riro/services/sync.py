"""Sync: connect, sync on start, Sync now, one sync at a time, the folder summary, plain-word errors.

US-01, US-06, US-07, US-09, US-10, ADR-003, ADR-004. The per-file work is in sync_files.py.

Nobody waits on a lock: a second sync while one runs returns "Syncing..." at once. A watchdog kills Edge when a
sync runs past the whole-sync limit, so a stuck call ends instead of waiting for its own limit.
"""

import threading
import time
from collections.abc import Callable
from datetime import datetime

from riro.connectors.sharepoint.errors import (
    ConnectorError,
    EdgeNotStarted,
    NeedsSignIn,
    TimedOut,
)
from riro.core.models import SyncRun
from riro.services.local_import import BUSY, MAX_BYTES, ImportResult, import_paths
from riro.services.sync_apply import read_folder
from riro.services.sync_messages import (
    EDGE_NOT_STARTED,
    FOLDER_LABEL,
    MESSAGES,
    NOT_CONNECTED,
    SAVE_FAILED,
    SIGN_IN_NOT_FINISHED,
    SYNCING,
    UNEXPECTED,
    SyncResult,
    message_for,
    summary,
)
from riro.store.datafile import SaveFailed
from riro.store.repo import Repo

# Re-exported: the bridge and the tests import these from here.
__all__ = [
    "EDGE_NOT_STARTED",
    "FOLDER_LABEL",
    "MESSAGES",
    "NOT_CONNECTED",
    "SAVE_FAILED",
    "SIGN_IN_NOT_FINISHED",
    "SYNCING",
    "UNEXPECTED",
    "SyncResult",
    "SyncService",
    "message_for",
    "summary",
]

SYNC_LIMIT_S = 180.0  # ADR-003: whole sync


class _OverLimit(Exception):
    pass


class SyncService:
    def __init__(
        self,
        connector,
        diagnostics,
        *,
        repo: Repo | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
        limit_s: float = SYNC_LIMIT_S,
    ):
        self._connector = connector
        self._repo = repo if repo is not None else Repo.in_memory()
        self._diagnostics = diagnostics
        self._clock = clock
        self._now = now
        self._limit_s = limit_s
        self._running = threading.Lock()
        self._overran = threading.Event()
        self._current_run: object | None = None
        self._last_success: datetime | None = self._repo.last_success()
        self._last = SyncResult(
            "not_connected", NOT_CONNECTED, last_success=self._last_success
        )

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

    def import_files(self, paths, max_bytes: int = MAX_BYTES) -> ImportResult:
        """US-13. Shares the sync lock, so a sync never overwrites an import's joiners. Never waits."""
        if not self._running.acquire(blocking=False):
            return ImportResult("busy", BUSY)
        try:
            return import_paths(
                list(paths), self._repo, self._diagnostics, self._now(), max_bytes
            )
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
        counts: dict = {}
        exception = None
        try:
            self._ping()
            within_limit()
            files = self._connector.list_files()
            within_limit()
            result, counts = read_folder(
                self._connector,
                self._diagnostics,
                self._repo,
                files,
                self._now(),
                within_limit,
                self._last_success,
            )
            self._last_success = result.last_success
            kind = None if result.state == "ok" else "SaveFailed"
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
        if kind is not None and kind != "SaveFailed":
            self._add_failed_run()
        self._diagnostics.event(
            "sync",
            result="ok" if kind is None else "failed",
            error_kind=kind,
            exception=exception,
            files_count=len(files),
            updated_count=result.updated,
            unchanged_count=result.unchanged,
            skipped_count=len(result.skipped),
            **counts,
            duration_s=self._clock() - started,
        )
        return result

    def _add_failed_run(self) -> None:
        try:
            self._repo.add_run(SyncRun(self._now(), "failed", 0, 0, 0, ()))
        except SaveFailed:
            pass  # the sync already failed; its plain-word message stays

    def _failed(self, state: str, message: str, files: list[dict]) -> SyncResult:
        return SyncResult(
            state, message, files_listed=len(files), last_success=self._last_success
        )
