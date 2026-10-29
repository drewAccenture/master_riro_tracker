"""The one headless Edge session, shared by the sync worker, the watchdog and the window-closed handler.

Nobody waits on a lock while Edge starts: the start runs outside the lock. A close() during a start bumps the epoch
and stops the start (abort), so the session that comes back late is killed instead of used.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from riro.connectors.sharepoint.errors import TimedOut, Unreachable
from riro.connectors.sharepoint.urls import FOLDER_URL

GRACEFUL_CLOSE_S = 5.0  # lets Edge save the new sign-in to its profile before the kill
POLITE_CLOSE_NOT_FINISHED = (
    "polite close did not finish"  # fixed wording for the report (ADR-007)
)


class Page(Protocol):
    def evaluate(self, expression: str, *, timeout_s: float) -> object: ...

    def current_url(self, *, timeout_s: float) -> str: ...

    def navigate(self, url: str, *, timeout_s: float) -> None: ...


@dataclass
class EdgeSession:
    process: object  # kill(); optionally close(timeout_s) for a graceful close first
    page: Page


def stop(session: EdgeSession, graceful: bool) -> bool | None:
    """End Edge; always by its handle in the end (ADR-010).

    Returns None when there was no polite close, else whether Edge exited by itself in time.
    """
    finished = None
    close = getattr(session.process, "close", None)
    if graceful and close:
        try:
            finished = bool(close(GRACEFUL_CLOSE_S))
        except Exception:  # noqa: BLE001 - the kill below ends it anyway
            finished = False
    session.process.kill()
    return finished


class SessionSlot:
    def __init__(self, start_edge: Callable[[bool, str], EdgeSession]):
        self._start_edge = start_edge
        self._lock = threading.Lock()
        self._session: EdgeSession | None = None
        self._epoch = 0
        self._stopping = False

    @property
    def stopping(self) -> bool:
        return self._stopping

    def get(self) -> EdgeSession:
        """The current session, or a new headless one."""
        with self._lock:
            if self._stopping:
                raise Unreachable("the app is closing")
            session, epoch = self._session, self._epoch
        if session is not None:
            return session
        session = self._start_edge(True, FOLDER_URL)
        if self.put(session, epoch):
            return session
        raise TimedOut("Edge was closed while it started")

    def put(self, session: EdgeSession, epoch: int | None = None) -> bool:
        """Keep a session that was just started, unless a close() or shutdown() came in the meantime."""
        with self._lock:
            keep = not self._stopping and (epoch is None or epoch == self._epoch)
            if keep:
                old, self._session = self._session, session
            else:
                old = None
        if old is not None:
            stop(old, graceful=False)
        if not keep:
            stop(session, graceful=False)
        return keep

    def drop(self, session: EdgeSession) -> None:
        """Kill a session that failed. A newer session in the slot is left alone."""
        with self._lock:
            if self._session is session:
                self._session = None
        stop(session, graceful=False)

    def clear(self, graceful: bool, stopping: bool = False) -> bool | None:
        """Kill the session and stop any start in progress. Returns what stop() returned, or None."""
        with self._lock:
            session, self._session = self._session, None
            self._epoch += 1
            self._stopping = self._stopping or stopping
        abort = getattr(self._start_edge, "abort", None)
        if abort:
            abort()
        if session is None:
            return None
        return stop(session, graceful)
