"""SharePoint through the app's own Edge: sign_in, list_files, download, renew (ADR-002, ADR-003).

Every request is a GET run as fetch() inside the page, so cookies stay inside Edge. Returns plain data only.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from riro.connectors.sharepoint.errors import (
    ConnectorError,
    NeedsSignIn,
    TimedOut,
    Unreachable,
)
from riro.connectors.sharepoint.session import (
    POLITE_CLOSE_NOT_FINISHED,
    EdgeSession,
    Page,
    SessionSlot,
    stop,
)
from riro.connectors.sharepoint.urls import (  # noqa: F401 - FOLDER_PATH, check_url: part of this module's interface
    FOLDER_PATH,
    FOLDER_URL,
    LIST_URL,
    SITE_URL,
    build_fetch_js,
    check_url,
    is_expired,
    is_not_ready,
    is_site_page,
    read_body,
)

POLL_S = 0.5
SETTLE_S = 10.0  # a page on its way back from a Microsoft login settles by itself first (silent renewal)

_FILE_ID = re.compile(r"[0-9A-Za-z-]{1,64}")


@dataclass(frozen=True)
class Limits:
    """ADR-003. Tests pass small ones."""

    edge_start_s: float = 30.0
    health_ping_s: float = 5.0
    request_s: float = 30.0
    renewal_s: float = 45.0
    sign_in_s: float = 180.0


DEFAULT_LIMITS = Limits()


class SharePointClient:
    def __init__(
        self,
        start_edge: Callable[[bool, str], EdgeSession],
        *,
        limits: Limits = DEFAULT_LIMITS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        on_event: Callable[..., None] | None = None,
    ):
        self._start_edge = start_edge
        self._slot = SessionSlot(start_edge)
        self._limits = limits
        self._clock = clock
        self._sleep = sleep
        self._on_event = on_event or (lambda step, **fields: None)
        self._visible: EdgeSession | None = None

    # --- session ---------------------------------------------------------------------------------------------

    def _page_call(self, call: Callable[[Page], object]):
        session = self._slot.get()
        try:
            return call(session.page)
        except ConnectorError:
            # A stuck or lost Edge is killed; the next call starts a fresh one (US-07).
            self._slot.drop(session)
            raise

    def close(self) -> None:
        """Kill Edge at once, also one that is still starting (time-outs, ADR-003)."""
        self._slot.clear(graceful=False)

    def shutdown(self) -> None:
        """App exit: stop a sign-in in progress, let headless Edge save its profile, then kill it."""
        visible = self._visible
        finished = self._slot.clear(graceful=True, stopping=True)
        if visible is not None:
            stop(visible, graceful=False)
        if finished is False:
            # ADR-010: Edge was killed without saving; a sign-in it renewed today may be lost.
            self._on_event(
                "edge_close", result="failed", note=POLITE_CLOSE_NOT_FINISHED
            )

    # --- sign-in and renewal ---------------------------------------------------------------------------------

    def sign_in(self) -> None:
        """Visible Edge on the folder page. Done once a site page (not a sign-in page) shows on two polls."""
        # Visible and headless Edge cannot share the profile. Killed at once: ADR-010 allows a polite close only
        # after a finished sign-in and at app exit.
        self._slot.clear(graceful=False)
        started = self._clock()
        deadline = started + self._limits.sign_in_s
        session = self._start_edge(False, FOLDER_URL)
        self._visible = session
        graceful = False
        try:
            on_site_before = False
            while True:
                if self._slot.stopping:
                    raise TimedOut("the app was closed during sign-in")
                try:
                    url = session.page.current_url(timeout_s=self._limits.health_ping_s)
                except TimedOut:
                    url = ""
                on_site = is_site_page(url)
                if on_site and on_site_before:
                    graceful = True
                    break
                on_site_before = on_site
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimedOut("sign-in did not finish")
                self._sleep(min(POLL_S, remaining))
        except BaseException:
            self._on_event(
                "sign_in", result="failed", duration_s=self._clock() - started
            )
            raise
        finally:
            self._visible = None
            if stop(session, graceful) is False:
                # ADR-010: the visible Edge was killed before it saved the new sign-in.
                self._on_event(
                    "edge_close", result="failed", note=POLITE_CLOSE_NOT_FINISHED
                )
        self._on_event("sign_in", result="ok", duration_s=self._clock() - started)
        if self._slot.stopping:
            return
        try:
            self._slot.put(self._start_edge(True, FOLDER_URL))
        except ConnectorError:
            # The sign-in worked. A blocked headless Edge is reported by the next call, in its own words.
            pass

    def renew(self, deadline: float | None = None) -> bool:
        """Send the page to the folder once; True once it shows a site page again, within the limit (US-08)."""
        started = self._clock()
        if deadline is None:
            deadline = started + self._limits.renewal_s
        if deadline - started <= 0:
            self._on_event("renewal", result="failed", duration_s=0.0)
            return False
        self._page_call(
            lambda page: page.navigate(
                FOLDER_URL, timeout_s=min(self._limits.request_s, deadline - started)
            )
        )
        while True:
            url = self._page_call(
                lambda page: page.current_url(timeout_s=self._limits.health_ping_s)
            )
            if is_site_page(url):
                self._on_event(
                    "renewal", result="ok", duration_s=self._clock() - started
                )
                return True
            remaining = deadline - self._clock()
            if remaining <= 0:
                self._on_event(
                    "renewal", result="failed", duration_s=self._clock() - started
                )
                return False
            self._sleep(min(POLL_S, remaining))

    # --- requests --------------------------------------------------------------------------------------------

    def health_ping(self) -> None:
        self._page_call(
            lambda page: page.evaluate("1 + 1", timeout_s=self._limits.health_ping_s)
        )

    def _fetch(self, url: str) -> dict:
        expression = build_fetch_js(url)
        answer = self._page_call(
            lambda page: page.evaluate(expression, timeout_s=self._limits.request_s)
        )
        if not isinstance(answer, dict):
            raise Unreachable("unreadable answer")
        if answer.get("type") == "error":
            raise Unreachable(
                "network error"
            )  # the page is a loaded site page, so this is the network
        return answer

    def _fetch_when_ready(self, url: str, deadline: float, answer: dict | None = None):
        """Ask again while the page is not a loaded site page, until the deadline."""
        if answer is None:
            answer = self._fetch(url)
        while is_not_ready(answer):
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            self._sleep(min(POLL_S, remaining))
            answer = self._fetch(url)
        return answer

    def _get(self, url: str, step: str) -> bytes:
        started = self._clock()
        renew_by = (
            started + self._limits.renewal_s
        )  # ADR-003: settling and renewal share 45 s
        try:
            answer = self._fetch(url)
            if is_not_ready(answer):
                settle_by = started + min(SETTLE_S, self._limits.renewal_s)
                answer = self._fetch_when_ready(url, settle_by, answer)
            if is_expired(answer) or is_not_ready(answer):
                if not self.renew(renew_by):
                    raise NeedsSignIn()
                answer = self._fetch_when_ready(url, renew_by)
                if is_expired(answer) or is_not_ready(answer):
                    raise NeedsSignIn()
            body = read_body(answer)
        except Exception as exc:
            self._on_event(
                step,
                result="failed",
                error_kind=getattr(exc, "kind", None),
                duration_s=self._clock() - started,
            )
            raise
        self._on_event(
            step,
            result="ok",
            http_status=answer.get("status"),
            bytes_count=len(body),
            duration_s=self._clock() - started,
        )
        return body

    def list_files(self) -> list[dict]:
        body = self._get(LIST_URL, "list")
        try:
            data = json.loads(body)
            items = data.get("value")
            if items is None:
                items = data["d"]["results"]
            return [
                {
                    "id": str(item["UniqueId"]),
                    "name": str(item["Name"]),
                    "etag": str(item.get("ETag", "")),
                    "modified": str(item.get("TimeLastModified", "")),
                    "size": int(item.get("Length", 0)),
                }
                for item in items
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise Unreachable("unreadable folder listing") from exc

    def download(self, file_id: str) -> bytes:
        if not _FILE_ID.fullmatch(file_id):
            raise ValueError("refused: unexpected file id")
        return self._get(
            f"{SITE_URL}_api/web/GetFileById('{file_id}')/$value", "download"
        )
