"""US-06, US-08: services/autosync.py runs a sync every 5 minutes with a fake timer, stops on not_connected."""

import pytest

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
        timer = FakeTimer(interval, fn)
        self.timers.append(timer)
        return timer


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


def test_us06_interval_is_5_minutes():
    assert INTERVAL_S == 300.0


def test_us06_start_schedules_a_daemon_timer_for_the_interval():
    auto, service, factory = make()
    assert auto.running() is False
    auto.start()
    assert len(factory.timers) == 1
    timer = factory.timers[0]
    assert (timer.interval, timer.daemon, timer.started) == (300.0, True, True)
    assert auto.running() is True
    assert service.calls == 0  # the start-up sync is not the timer's job


def test_us06_custom_interval_is_used():
    auto, _, factory = make(interval_s=12.5)
    auto.start()
    assert factory.timers[0].interval == 12.5


@pytest.mark.parametrize("state", ["ok", "failed", "syncing"])
def test_us06_tick_syncs_and_schedules_the_next_one(state):
    auto, service, factory = make(state)
    auto.start()
    factory.timers[0].fn()
    assert service.calls == 1
    assert len(factory.timers) == 2
    nxt = factory.timers[1]
    assert (nxt.interval, nxt.daemon, nxt.started) == (300.0, True, True)
    assert auto.running() is True


def test_us06_ticks_keep_going_every_interval():
    auto, service, factory = make()
    auto.start()
    for n in range(3):
        factory.timers[n].fn()
    assert service.calls == 3
    assert len(factory.timers) == 4


def test_us08_not_connected_stops_auto_sync():
    auto, service, factory = make("not_connected")
    auto.start()
    factory.timers[0].fn()
    assert service.calls == 1
    assert len(factory.timers) == 1
    assert auto.running() is False


def test_us08_start_again_after_sign_in_restarts_it():
    auto, service, factory = make("not_connected")
    auto.start()
    factory.timers[0].fn()
    service.state = "ok"
    auto.start()  # Connect worked
    assert auto.running() is True
    assert len(factory.timers) == 2
    factory.timers[1].fn()
    assert len(factory.timers) == 3


def test_us06_start_twice_cancels_the_pending_timer():
    auto, _, factory = make()
    auto.start()
    auto.start()
    assert factory.timers[0].cancelled is True
    assert factory.timers[1].cancelled is False
    assert auto.running() is True


def test_us06_stop_cancels_the_pending_timer():
    auto, _, factory = make()
    auto.start()
    auto.stop()
    assert factory.timers[0].cancelled is True
    assert auto.running() is False


def test_us06_tick_after_stop_does_not_reschedule():
    auto, _, factory = make()
    auto.start()
    auto.stop()
    factory.timers[0].fn()  # a timer that fired just as the app closed
    assert len(factory.timers) == 1
    assert auto.running() is False


def test_us06_stop_before_start_is_harmless():
    auto, _, factory = make()
    auto.stop()
    assert factory.timers == []
    assert auto.running() is False
