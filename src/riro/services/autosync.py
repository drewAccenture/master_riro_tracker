"""US-06: sync every 5 minutes while the app is open. Stops when the sign-in expired (US-08) until Connect."""

import threading

INTERVAL_S = 300.0


class AutoSync:
    def __init__(
        self, service, *, interval_s: float = INTERVAL_S, timer_factory=threading.Timer
    ):
        self._service = service
        self._interval_s = interval_s
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._timer = None
        # Ties a tick to the timer that made it: a stopped or replaced timer's tick does nothing.
        self._token: object | None = None

    def start(self) -> None:
        with self._lock:
            self._schedule()

    def stop(self) -> None:
        with self._lock:
            self._cancel()

    def running(self) -> bool:
        return self._timer is not None

    def _cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None
        self._token = None

    def _schedule(self) -> None:
        self._cancel()
        token = self._token = object()
        self._timer = self._timer_factory(self._interval_s, lambda: self._tick(token))
        self._timer.daemon = True
        self._timer.start()

    def _tick(self, token: object) -> None:
        if token is not self._token:
            return
        result = None
        try:
            # A sync already running returns "Syncing..." at once.
            result = self._service.sync()
        finally:
            # Even if the sync raised, the next tick is scheduled: auto-sync never stops silently.
            with self._lock:
                if (
                    token is self._token
                ):  # else stopped or restarted while this sync ran
                    if result is not None and result.state == "not_connected":
                        self._cancel()
                    else:
                        self._schedule()
