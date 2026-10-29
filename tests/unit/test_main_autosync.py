"""US-06, ADR-010: at app exit auto-sync is stopped first, then Edge is closed, then the log."""

from riro.__main__ import finish


class Recorder:
    def __init__(self, calls, name):
        self.calls = calls
        self.name = name

    def stop(self):
        self.calls.append(f"{self.name}.stop")

    def shutdown(self):
        self.calls.append(f"{self.name}.shutdown")

    def close(self):
        self.calls.append(f"{self.name}.close")


def test_us06_finish_stops_auto_sync_before_closing_edge_and_log():
    calls = []
    finish(
        Recorder(calls, "service"),
        Recorder(calls, "diagnostics"),
        autosync=Recorder(calls, "autosync"),
    )
    assert calls == ["autosync.stop", "service.shutdown", "diagnostics.close"]


def test_us06_finish_without_auto_sync_still_closes_edge_and_log():
    calls = []
    finish(Recorder(calls, "service"), Recorder(calls, "diagnostics"))
    assert calls == ["service.shutdown", "diagnostics.close"]
