"""Redacted event log and the "Copy diagnostic report" text (US-16, ADR-007).

Redaction happens when an event is written: only allowed fields with allowed value types are kept. Free text from
files or from SharePoint is never accepted, except the template wording ADR-007 allows in file_report().
"""

import logging
import re
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit

from riro.connectors.sharepoint.session import POLITE_CLOSE_NOT_FINISHED
from riro.connectors.sharepoint.urls import SITE_PATH, SITE_URL
from riro.core.models import HeaderReport

STEPS = {
    "edge_start",
    "sign_in",
    "renewal",
    "health_ping",
    "list",
    "download",
    "header_check",
    "file_read",
    "sync",
    "edge_close",
    "local_import",  # US-13
}
NOTES = {POLITE_CLOSE_NOT_FINISHED}  # fixed sentences only, never free text
RESULTS = {"ok", "failed"}
ERROR_KINDS = {
    "NeedsSignIn",
    "NoAccess",
    "NotFound",
    "Unreachable",
    "TimedOut",
    "EdgeMissing",
    "UnreadableFile",
    "NotAChecklist",
    "SaveFailed",
    "Unexpected",
}
_CLASS_NAME = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]{0,59}"
)  # an exception's class name, never its text
SITE = SITE_URL
KEEP_EVENTS = 300
LOG_BYTES = 512 * 1024
LOG_BACKUPS = 3


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _url(value) -> str | None:
    """Scheme and host only, plus the site path when it is our site. Never a query or the folder path."""
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    base = f"{parts.scheme}://{parts.hostname}/"
    if base + SITE_PATH[1:] == SITE and parts.path.startswith(SITE_PATH):
        return SITE
    return base


def _allowed(name: str, value) -> str | None:
    """The value as report text, or None to drop it."""
    if name == "result":
        return value if value in RESULTS else None
    if name == "error_kind":
        return value if value in ERROR_KINDS else None
    if name == "url":
        return _url(value)
    if name == "note":
        return value if value in NOTES else None
    if name == "exception":
        return (
            value if isinstance(value, str) and _CLASS_NAME.fullmatch(value) else None
        )
    if name == "duration_s":
        return f"{value:.2f}".rstrip("0").rstrip(".") if _number(value) else None
    if name in ("http_status", "attempt", "file_index") or name.endswith("_count"):
        return (
            str(value)
            if isinstance(value, int) and not isinstance(value, bool)
            else None
        )
    return None


class Diagnostics:
    def __init__(
        self,
        log_dir: Path | None,
        *,
        versions: dict[str, str],
        now: Callable[[], datetime] = datetime.now,
    ):
        self._versions = dict(versions)
        self._now = now
        self._lines: deque[str] = deque(maxlen=KEEP_EVENTS)
        self._files: list[str] = []
        self._lock = threading.Lock()
        self._log = None
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            self._log = logging.getLogger(f"riro.diagnostics.{id(self)}")
            self._log.propagate = False
            self._log.setLevel(logging.INFO)
            handler = RotatingFileHandler(
                log_dir / "riro.log",
                maxBytes=LOG_BYTES,
                backupCount=LOG_BACKUPS,
                encoding="utf-8",
            )
            self._log.addHandler(handler)

    def close(self) -> None:
        """Close the log file. Under the same lock as writing, so a late event never meets a half-closed log."""
        with self._lock:
            if self._log is not None:
                for handler in list(self._log.handlers):
                    handler.close()
                    self._log.removeHandler(handler)
                self._log = None

    def set_version(self, name: str, value: str) -> None:
        """Versions only come from our own code (app, Python, pywebview, WebView2, Edge)."""
        with self._lock:
            self._versions[name] = value

    def _write(self, line: str) -> None:
        if self._log is not None:
            self._log.info(line)
            for handler in self._log.handlers:
                handler.flush()

    def event(self, step: str, **fields) -> None:
        step = step if step in STEPS else "other"
        kept = []
        for name in sorted(fields):
            text = _allowed(name, fields[name])
            if text is not None:
                kept.append(f"{name}={text}")
        line = " ".join([f"{self._now():%Y-%m-%d %H:%M:%S}", step, *kept])
        with self._lock:
            self._lines.append(line)
            self._write(line)

    def file_report(self, index: int, total: int, report: HeaderReport) -> None:
        """File position, headers, rows and the template values with counts. Never the file or sheet name."""
        lines = [
            (
                f"file {int(index)} of {int(total)}: rows {int(report.row_count)}, "
                f"sheet {'named roll-in' if report.sheet_matched else 'first sheet'}"
            ),
            "  headers found: " + ", ".join(report.headers_found),
            "  headers missing: " + (", ".join(report.headers_missing) or "none"),
        ]
        for label, counts in (
            ("Deadline", report.deadline_counts),
            ("Completion Status", report.status_counts),
        ):
            for value, count in sorted(counts.items()):
                lines.append(f"  {label}: {value} = {int(count)}")
        with self._lock:
            self._files = lines
            for line in lines:
                self._write(line)

    def report(self) -> str:
        with self._lock:
            parts = ["RIRO Tracker diagnostic report", ""]
            parts += [f"{name}: {value}" for name, value in self._versions.items()]
            parts += ["", "Recent steps:"]
            parts += list(self._lines) or ["(none)"]
            parts += ["", "Last file checked:"]
            parts += self._files or ["(none)"]
        return "\n".join(parts) + "\n"
