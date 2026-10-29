"""ADR-010, ADR-007: at app exit Edge is closed before the log is closed, so the exit event reaches logs\\."""

from riro.__main__ import finish
from riro.connectors.sharepoint.session import POLITE_CLOSE_NOT_FINISHED
from riro.services.diagnostics import Diagnostics


class Service:
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        self.calls = []

    def shutdown(self):
        self.calls.append("shutdown")
        self.diagnostics.event(
            "edge_close", result="failed", note=POLITE_CLOSE_NOT_FINISHED
        )


def test_adr010_exit_close_event_reaches_the_log_file(tmp_path):
    diagnostics = Diagnostics(tmp_path, versions={"app": "test"})
    service = Service(diagnostics)
    finish(service, diagnostics)
    assert service.calls == ["shutdown"]
    log = (tmp_path / "riro.log").read_text(encoding="utf-8")
    assert "edge_close" in log
    assert POLITE_CLOSE_NOT_FINISHED in log


def test_adr007_event_after_the_log_is_closed_is_kept_in_memory_only(tmp_path):
    diagnostics = Diagnostics(tmp_path, versions={"app": "test"})
    diagnostics.close()
    diagnostics.event("sync", result="ok")  # must not raise
    assert "sync" in diagnostics.report()
