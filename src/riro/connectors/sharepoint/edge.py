"""Find Edge's DevTools port and open a session on it (ADR-002, ADR-009).

The port is chosen by us and confirmed through http://127.0.0.1:<port>/json/version. Nothing in the profile folder
is opened, read or listed. Starting and killing the Windows process lives in edge_process.py.
"""

import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from riro.connectors.sharepoint.cdp import CdpClient, CdpPage, WebSocketTransport
from riro.connectors.sharepoint.client import EdgeSession
from riro.connectors.sharepoint.edge_process import (  # noqa: F401 - build_command: part of this module's interface
    EdgeProcess,
    build_command,
    find_edge,
    launch_edge,
)
from riro.connectors.sharepoint.errors import ConnectorError, EdgeNotStarted, TimedOut

DEVTOOLS_START_LIMIT_S = (
    30.0  # ADR-003: Edge start until DevTools answers, all attempts
)
DEVTOOLS_ATTEMPTS = 3  # ADR-009
POLL_S = 0.2
PROBE_S = 0.5  # one /json/version request; short, so a stop() is seen quickly
CONNECT_S = 5.0  # websocket connect and opening our tab, after /json/version answered
PAGE_S = 30.0  # ADR-003 request limit: first page committed and loaded
START_TOTAL_S = DEVTOOLS_START_LIMIT_S + PAGE_S  # one deadline for a whole Edge start
READY_JS = "document.readyState"

_NOT_OURS = object()
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _probe(port: int, timeout_s: float):
    """websocket address if the answer is ours, _NOT_OURS if someone else answers, None if nobody answers yet."""
    try:
        with _NO_PROXY.open(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout_s
        ) as answer:
            body = answer.read(64 * 1024)
    except urllib.error.HTTPError:
        return _NOT_OURS
    except (OSError, ValueError):
        return None  # nobody listening yet, or the connection dropped
    except http.client.HTTPException:
        return _NOT_OURS  # something that does not speak HTTP holds the port
    try:
        data = json.loads(body)
    except ValueError:
        return _NOT_OURS
    if not isinstance(data, dict):
        return _NOT_OURS
    browser, ws_url = data.get("Browser"), data.get("webSocketDebuggerUrl")
    if not (isinstance(browser, str) and browser.startswith("Edg/")):
        return _NOT_OURS
    if not isinstance(ws_url, str):
        return _NOT_OURS
    try:
        parts = urlsplit(ws_url)
        ws_port = parts.port
    except ValueError:
        return _NOT_OURS
    if parts.scheme != "ws" or parts.hostname != "127.0.0.1" or ws_port != port:
        return _NOT_OURS
    return ws_url


def start_devtools(
    launch: Callable[[int], object],
    *,
    pick_port: Callable[[], int] = pick_free_port,
    limit_s: float = DEVTOOLS_START_LIMIT_S,
    attempts: int = DEVTOOLS_ATTEMPTS,
    poll_s: float = POLL_S,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    on_event: Callable[..., None] | None = None,
    stop: Callable[[], bool] | None = None,
) -> tuple[object, str]:
    """Launch Edge on a free port until its DevTools answer is ours. Returns (process, websocket address).

    stop() is asked between polls; when it says True the attempt ends, Edge is killed and no new attempt starts.
    """
    deadline = clock() + limit_s
    for attempt in range(1, attempts + 1):
        if stop and stop():
            raise TimedOut("Edge start stopped")
        started = clock()
        # The time left is shared by the attempts left, so a quick "not ours" gives later attempts more time.
        attempt_end = started + max(deadline - started, 0.0) / (attempts - attempt + 1)
        port = pick_port()
        process = launch(port)
        try:
            while (remaining := attempt_end - clock()) > 0:
                if stop and stop():
                    raise TimedOut("Edge start stopped")
                answer = _probe(port, min(remaining, PROBE_S))
                if isinstance(answer, str):
                    if on_event:
                        on_event(
                            "edge_start",
                            result="ok",
                            attempt=attempt,
                            duration_s=clock() - started,
                        )
                    return process, answer
                if answer is _NOT_OURS:
                    break
                sleep(min(poll_s, max(attempt_end - clock(), 0.0)))
        except BaseException:
            process.kill()
            raise
        process.kill()
        if on_event:
            on_event(
                "edge_start",
                result="failed",
                attempt=attempt,
                duration_s=clock() - started,
            )
    raise EdgeNotStarted("Edge could not be started")


def _wait_until_loaded(
    page: CdpPage,
    timeout_s: float,
    poll_s: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> None:
    deadline = clock() + timeout_s
    while (remaining := deadline - clock()) > 0:
        try:
            if (
                page.evaluate(READY_JS, timeout_s=min(CONNECT_S, remaining))
                == "complete"
            ):
                return
        except TimedOut:
            pass
        except ConnectorError:
            pass  # the document changed while we asked (a redirect); ask again
        sleep(min(poll_s, max(deadline - clock(), 0.0)))
    raise TimedOut("page did not finish loading")


class _SessionProcess:
    def __init__(self, process: EdgeProcess, transport, cdp: CdpClient | None = None):
        self._process, self._transport, self.cdp = process, transport, cdp

    def close(self, timeout_s: float) -> bool:
        """Ask Edge to close so it saves its profile (ADR-010). One limit for asking and waiting;
        the caller kills the job right after. True if Edge exited by itself in time."""
        if self.cdp is None:
            return False
        deadline = time.monotonic() + timeout_s
        try:
            self.cdp.call("Browser.close", timeout_s=timeout_s)
        except ConnectorError:
            pass  # Edge often drops the connection while it closes
        return bool(self._process.wait(max(deadline - time.monotonic(), 0.0)))

    def kill(self) -> None:
        self._transport.close()
        self._process.kill()


def make_start_edge(profile_dir: Path, **options) -> "EdgeStarter":
    """The real start_edge(headless, url) for SharePointClient."""
    return EdgeStarter(profile_dir, **options)


class EdgeStarter:
    """start_edge(headless, url), plus abort() for the watchdog and app exit.

    Edge starts on about:blank. Our own tab is then sent to the URL: Page.navigate returns once the first document
    is committed, and we wait for it to finish loading. Until then the reported URL can be the one still loading,
    so it would look "on the site" too early (checked against real Edge, 2026-10-27). The whole start has one
    deadline: the DevTools limit (ADR-003) plus one page load.
    """

    def __init__(
        self,
        profile_dir: Path,
        *,
        limit_s: float = DEVTOOLS_START_LIMIT_S,
        on_event: Callable[..., None] | None = None,
        on_version: Callable[[str], None] | None = None,
        find: Callable[[], Path] = find_edge,
        launch: Callable[..., EdgeProcess] = launch_edge,
        start: Callable[..., tuple] = start_devtools,
        connect: Callable[[str, float], object] = WebSocketTransport,
        page_s: float = PAGE_S,
        poll_s: float = POLL_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._profile_dir = profile_dir
        self._limit_s, self._on_event, self._on_version = limit_s, on_event, on_version
        self._find, self._launch, self._start, self._connect = (
            find,
            launch,
            start,
            connect,
        )
        self._page_s, self._poll_s, self._clock, self._sleep = (
            page_s,
            poll_s,
            clock,
            sleep,
        )
        self._lock = threading.Lock()
        self._aborted = False
        self._current = None

    def abort(self) -> None:
        """Stop a start in progress from another thread. The start raises TimedOut and kills its Edge."""
        with self._lock:
            self._aborted = True
            current = self._current
        if current is not None:
            current.kill()

    def _track(self, process):
        with self._lock:
            self._current = process
            aborted = self._aborted
        if aborted:
            process.kill()
            raise TimedOut("Edge start stopped")
        return process

    def __call__(self, headless: bool, url: str) -> EdgeSession:
        with self._lock:
            self._aborted = False
            self._current = None
        deadline = self._clock() + self._limit_s + self._page_s

        def left(limit: float) -> float:
            remaining = deadline - self._clock()
            if self._aborted or remaining <= 0:
                raise TimedOut("Edge start stopped or too slow")
            return min(limit, remaining)

        exe = self._find()
        process, ws_url = self._start(
            lambda port: self._track(
                self._launch(
                    exe, self._profile_dir, port, headless=headless, url="about:blank"
                )
            ),
            limit_s=self._limit_s,
            on_event=self._on_event,
            stop=lambda: self._aborted,
        )
        try:
            transport = self._connect(ws_url, left(CONNECT_S))
        except BaseException:
            process.kill()
            raise
        cdp = CdpClient(transport, clock=self._clock)
        session_process = self._track(_SessionProcess(process, transport, cdp))
        try:
            if self._on_version:
                version = cdp.call("Browser.getVersion", timeout_s=left(CONNECT_S))
                self._on_version(str(version.get("product", "")))
            page = CdpPage.open(cdp, timeout_s=left(CONNECT_S))
            page.navigate(url, timeout_s=left(self._page_s))
            _wait_until_loaded(
                page, left(self._page_s), self._poll_s, self._clock, self._sleep
            )
            left(CONNECT_S)  # an abort that came in during the load still counts
        except BaseException:
            session_process.kill()
            raise
        finally:
            with self._lock:
                self._current = None
        return EdgeSession(process=session_process, page=page)
