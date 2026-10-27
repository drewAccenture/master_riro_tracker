"""A small DevTools client: send one command, wait for its answer with a time limit (ADR-002, ADR-003)."""

import contextlib
import json
import threading
import time
from collections.abc import Callable
from typing import Protocol

from riro.connectors.sharepoint.errors import TimedOut, Unreachable


class Transport(Protocol):
    def send(self, text: str) -> None: ...

    def recv(self, timeout_s: float) -> str:
        """Raises TimeoutError if nothing arrives within timeout_s."""

    def close(self) -> None: ...


class WebSocketTransport:
    """websocket-client to Edge's DevTools address on 127.0.0.1."""

    def __init__(self, ws_url: str, timeout_s: float):
        import websocket

        self._websocket = websocket
        try:
            # suppress_origin: Edge refuses DevTools websockets that send an Origin it does not know.
            self._ws = websocket.create_connection(
                ws_url, timeout=timeout_s, suppress_origin=True
            )
        except (OSError, websocket.WebSocketException) as exc:
            raise Unreachable("DevTools connection failed") from exc

    def send(self, text: str) -> None:
        try:
            self._ws.send(text)
        except (OSError, self._websocket.WebSocketException) as exc:
            raise ConnectionError("DevTools connection lost") from exc

    def recv(self, timeout_s: float) -> str:
        self._ws.settimeout(max(timeout_s, 0.001))
        try:
            return self._ws.recv()
        except self._websocket.WebSocketTimeoutException as exc:
            raise TimeoutError from exc
        except TimeoutError:
            raise
        except (OSError, self._websocket.WebSocketException) as exc:
            raise ConnectionError("DevTools connection lost") from exc

    def close(self) -> None:
        with contextlib.suppress(
            Exception
        ):  # closing a dead connection must never raise
            self._ws.close(timeout=0.5)


class CdpClient:
    def __init__(
        self, transport: Transport, clock: Callable[[], float] = time.monotonic
    ):
        self._transport = transport
        self._clock = clock
        self._next_id = 0
        self._lock = threading.Lock()

    def call(
        self,
        method: str,
        params: dict | None = None,
        *,
        timeout_s: float,
        session_id: str | None = None,
    ) -> dict:
        """The answer's "result". The limit covers the whole call, including waiting for another call to end
        and however many unrelated messages arrive."""
        deadline = self._clock() + timeout_s
        if not self._lock.acquire(timeout=max(timeout_s, 0.0)):
            raise TimedOut("DevTools busy")
        try:
            self._next_id += 1
            message_id = self._next_id
            message = {"id": message_id, "method": method, "params": params or {}}
            if session_id:
                message["sessionId"] = session_id
            try:
                self._transport.send(json.dumps(message))
            except OSError as exc:
                raise Unreachable("DevTools connection lost") from exc
            while (remaining := deadline - self._clock()) > 0:
                try:
                    text = self._transport.recv(remaining)
                except TimeoutError:
                    continue
                except OSError as exc:
                    raise Unreachable("DevTools connection lost") from exc
                try:
                    answer = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(answer, dict) or answer.get("id") != message_id:
                    continue  # an event, or an answer to an earlier call that timed out
                if "error" in answer:
                    raise Unreachable("DevTools command failed")
                return answer.get("result", {})
            raise TimedOut("DevTools did not answer in time")
        finally:
            self._lock.release()


class CdpPage:
    """One page target, used through a flat session on the browser connection."""

    def __init__(self, client: CdpClient, target_id: str, session_id: str):
        self._client, self._target_id, self._session_id = client, target_id, session_id

    @classmethod
    def open(cls, client: CdpClient, *, timeout_s: float) -> "CdpPage":
        """A new tab of our own, so start-up or welcome tabs Edge may open are never the one we watch."""
        created = client.call(
            "Target.createTarget", {"url": "about:blank"}, timeout_s=timeout_s
        )
        target_id = created.get("targetId")
        if not isinstance(target_id, str):
            raise Unreachable("no tab created")
        attached = client.call(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            timeout_s=timeout_s,
        )
        session_id = attached.get("sessionId")
        if not isinstance(session_id, str):
            raise Unreachable("tab not attached")
        return cls(client, target_id, session_id)

    def evaluate(self, expression: str, *, timeout_s: float) -> object:
        result = self._client.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
            timeout_s=timeout_s,
            session_id=self._session_id,
        )
        if "exceptionDetails" in result:
            raise Unreachable("page script failed")
        return result.get("result", {}).get("value")

    def current_url(self, *, timeout_s: float) -> str:
        info = self._client.call(
            "Target.getTargetInfo", {"targetId": self._target_id}, timeout_s=timeout_s
        )
        return str(info.get("targetInfo", {}).get("url", ""))

    def navigate(self, url: str, *, timeout_s: float) -> None:
        """Returns once the next document is committed (checked against real Edge, 2026-10-27)."""
        result = self._client.call(
            "Page.navigate",
            {"url": url},
            timeout_s=timeout_s,
            session_id=self._session_id,
        )
        if result.get("errorText"):
            raise Unreachable("navigation failed")
