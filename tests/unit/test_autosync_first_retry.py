"""Slice 8b, ADR-014, US-06: one early retry after a failed first sync.

- AutoSync.start(first_delay_s=...) uses first_delay_s for the first timer only; later timers use the interval.
- App start (__main__.sync_on_start): a "failed" start sync -> first auto-sync after FIRST_RETRY_S (60 s); any other
  state except "not_connected" -> after 5 minutes; "not_connected" (sign-in expired) -> auto-sync not started.

Fake timers, a fake service and a fake webview (demo mode, files under tmp_path only): no window, no Edge.
Names the code must provide are read from the module at test time, so each test fails on its own.
"""

import pytest

import riro.__main__ as app
from riro.services import autosync
from riro.services.autosync import INTERVAL_S, AutoSync
from riro.services.sync import SyncResult


class FakeTimer:
    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class TimerFactory:
    def __init__(self):
        self.timers = []

    def __call__(self, interval, fn):
        self.timers.append(FakeTimer(interval, fn))
        return self.timers[-1]


class FakeService:
    def __init__(self, state="ok"):
        self.state = state
        self.calls = 0

    def sync(self):
        self.calls += 1
        return SyncResult(self.state, "synthetic message")


def make(state="ok", **kwargs):
    service, factory = FakeService(state), TimerFactory()
    return AutoSync(service, timer_factory=factory, **kwargs), service, factory


def intervals(factory):
    return [t.interval for t in factory.timers]


# --- AutoSync ---------------------------------------------------------------------------------------------------


def test_adr014_first_retry_is_60_s():
    assert autosync.FIRST_RETRY_S == 60.0


def test_adr014_first_delay_is_used_for_the_first_timer_only():
    auto, service, factory = make()
    auto.start(first_delay_s=autosync.FIRST_RETRY_S)
    first = factory.timers[0]
    assert (first.interval, first.daemon, first.started) == (60.0, True, True)
    assert service.calls == 0
    factory.timers[0].fn()
    factory.timers[1].fn()
    assert service.calls == 2
    assert intervals(factory) == [60.0, INTERVAL_S, INTERVAL_S]
    assert auto.running() is True


def test_adr014_start_without_first_delay_still_uses_the_interval():
    auto, _, factory = make()
    auto.start()
    auto.start(first_delay_s=None)
    assert intervals(factory) == [INTERVAL_S, INTERVAL_S]


def test_adr014_first_delay_works_with_a_custom_interval():
    auto, _, factory = make(interval_s=12.5)
    auto.start(first_delay_s=3.0)
    factory.timers[0].fn()
    assert intervals(factory) == [3.0, 12.5]


@pytest.mark.parametrize("state", ["ok", "failed", "syncing"])
def test_adr014_tick_after_the_early_retry_goes_back_to_the_interval(state):
    auto, _, factory = make(state)
    auto.start(first_delay_s=60.0)
    factory.timers[0].fn()
    assert factory.timers[1].interval == INTERVAL_S


def test_us08_early_retry_that_finds_the_sign_in_expired_stops_auto_sync():
    auto, service, factory = make("not_connected")
    auto.start(first_delay_s=60.0)
    factory.timers[0].fn()
    assert service.calls == 1
    assert len(factory.timers) == 1
    assert auto.running() is False


def test_adr014_start_again_after_an_early_start_uses_the_interval_and_cancels_it():
    auto, _, factory = make()
    auto.start(first_delay_s=60.0)
    auto.start()  # e.g. Connect worked meanwhile
    assert factory.timers[0].cancelled is True
    assert intervals(factory) == [60.0, INTERVAL_S]
    factory.timers[0].fn()  # the cancelled early timer fires anyway: it does nothing
    assert len(factory.timers) == 2


def test_adr014_stop_cancels_a_pending_early_timer():
    auto, service, factory = make()
    auto.start(first_delay_s=60.0)
    auto.stop()
    factory.timers[0].fn()
    assert factory.timers[0].cancelled is True
    assert service.calls == 0
    assert auto.running() is False


class Crashing:
    def sync(self):
        raise RuntimeError("synthetic crash inside a sync")


def test_us06_early_tick_whose_sync_raises_schedules_the_next_at_the_interval():
    factory = TimerFactory()
    auto = AutoSync(Crashing(), timer_factory=factory)
    auto.start(first_delay_s=60.0)
    with pytest.raises(RuntimeError):
        factory.timers[0].fn()
    assert intervals(factory) == [60.0, INTERVAL_S]


# --- app start: __main__.sync_on_start --------------------------------------------------------------------------


class FakeEvents:
    def __init__(self):
        self.loaded = self

    def __iadd__(self, handler):
        return self


class FakeWindow:
    def __init__(self):
        self.events = FakeEvents()


class FakeWebview:
    """Stands in for pywebview: no window. start(func) runs func at once (pywebview runs it once the window is up)."""

    class FileDialog:
        OPEN = "open"

    def create_window(self, *args, **kwargs):
        return FakeWindow()

    def start(self, func=None, *args, **kwargs):
        if func is not None:
            func()


class StartService:
    """Stands in for SyncService in main(): the start sync returns the given state."""

    def __init__(self, state):
        self.state = state
        self.syncs = 0

    def __call__(self, connector, diagnostics, **kwargs):
        return self

    def sync(self):
        self.syncs += 1
        return SyncResult(self.state, "synthetic message")

    def shutdown(self):
        pass


class RecordingAutoSync:
    def __init__(self):
        self.starts = []  # the keyword arguments of each start()
        self.stops = 0

    def __call__(self, service, **kwargs):
        return self

    def start(self, **kwargs):
        self.starts.append(kwargs)

    def stop(self):
        self.stops += 1


def run_app(tmp_path, monkeypatch, state, signed_in=True):
    monkeypatch.setenv(
        "RIRO_DATA_DIR", str(tmp_path)
    )  # demo mode: SharePoint switched off
    if signed_in:
        (tmp_path / "edge_profile").mkdir()  # Connect has run on this PC before
    service, recorder = StartService(state), RecordingAutoSync()
    monkeypatch.setattr(app, "webview", FakeWebview())
    monkeypatch.setattr(app, "SyncService", service)
    monkeypatch.setattr(app, "AutoSync", recorder)
    app.main()
    return service, recorder


def test_adr014_failed_start_sync_starts_auto_sync_with_the_early_retry(
    tmp_path, monkeypatch
):
    service, recorder = run_app(tmp_path, monkeypatch, "failed")
    assert service.syncs == 1
    assert recorder.starts == [{"first_delay_s": autosync.FIRST_RETRY_S}]


@pytest.mark.parametrize("state", ["ok", "syncing", "sign_in_not_finished"])
def test_adr014_start_sync_that_did_not_fail_starts_auto_sync_at_5_minutes(
    tmp_path, monkeypatch, state
):
    service, recorder = run_app(tmp_path, monkeypatch, state)
    assert service.syncs == 1
    assert len(recorder.starts) == 1
    assert recorder.starts[0].get("first_delay_s") is None


def test_us08_start_sync_with_sign_in_expired_does_not_start_auto_sync(
    tmp_path, monkeypatch
):
    service, recorder = run_app(tmp_path, monkeypatch, "not_connected")
    assert service.syncs == 1
    assert recorder.starts == []


def test_us06_before_the_first_connect_there_is_no_start_sync_and_no_auto_sync(
    tmp_path, monkeypatch
):
    service, recorder = run_app(tmp_path, monkeypatch, "failed", signed_in=False)
    assert service.syncs == 0
    assert recorder.starts == []
