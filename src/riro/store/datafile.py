"""The one data file: atomic save, .bak copy, retries, load fallbacks, schema_version (ADR-004).

Only store/ reads or writes these files.
"""

import copy
import json
import os
import shutil
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
RESTORED_FROM_BACKUP = "Your data was restored from the backup copy."
STARTED_EMPTY = "Your data file was broken and no backup could be read. The app started with no data."
_ATTEMPTS = 6  # ADR-004: 1 attempt + 5 retries
_RETRY_WAIT_S = 0.2


class SaveFailed(Exception):
    """Windows kept refusing to replace the data file. The old file is unchanged."""


def _empty() -> dict:
    return {"schema_version": SCHEMA_VERSION}


class DataFile:
    def __init__(
        self,
        path: Path,
        *,
        now: Callable[[], datetime] = datetime.now,
        replace: Callable = os.replace,
        sleep: Callable[[float], None] = time.sleep,
        validate: Callable[[dict], None] = lambda data: None,
    ):
        """validate raises when the layout is wrong (store.repo.check_layout); that file then counts as broken."""
        self._path = Path(path)
        self._bak = Path(f"{path}.bak")
        self._tmp = Path(f"{path}.tmp")
        self._now = now
        self._replace = replace
        self._sleep = sleep
        self._lock = threading.Lock()
        self._validate = validate

    def _read(self, path: Path) -> dict | None:
        """The data in `path`, or None when it is missing, not JSON, another schema or the wrong layout."""
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            return None
        try:
            self._validate(data)
        except Exception:  # noqa: BLE001 - any layout problem means "broken", so the backup is used
            return None
        return data

    def load(self) -> tuple[dict, str | None]:
        with self._lock:
            data = self._read(self._path) if self._path.exists() else None
            if data is not None:
                return data, None
            backup = self._read(self._bak) if self._bak.exists() else None
            if backup is not None:
                return backup, RESTORED_FROM_BACKUP
            if not self._path.exists():
                return _empty(), None
            broken = self._path.with_name(
                f"{self._path.name}.broken-{self._now():%Y%m%d-%H%M%S}"
            )
            try:
                self._replace(self._path, broken)
            except OSError:
                pass  # held by another program: it stays, and is never copied to .bak (save checks it)
            return _empty(), STARTED_EMPTY

    def save(self, data: dict) -> None:
        payload = {**data, "schema_version": SCHEMA_VERSION}
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._tmp, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=1)
                    handle.flush()
                    os.fsync(handle.fileno())
                # Only a good file becomes the backup: a broken one must never replace the copy it was restored from.
                if self._read(self._path) is not None:
                    shutil.copyfile(self._path, self._bak)
            except OSError as exc:  # disk full, no permission, .bak held: tracker.json is still untouched
                raise SaveFailed("the data file could not be written") from exc
            for attempt in range(_ATTEMPTS):
                try:
                    self._replace(self._tmp, self._path)
                    return
                except OSError:
                    if attempt + 1 < _ATTEMPTS:
                        self._sleep(_RETRY_WAIT_S)
            raise SaveFailed("the data file could not be replaced")


class MemoryDataFile:
    """Same interface, kept in memory (tests, and a SyncService built without a data file)."""

    def __init__(self):
        self._data = _empty()

    def load(self) -> tuple[dict, str | None]:
        return copy.deepcopy(self._data), None

    def save(self, data: dict) -> None:
        self._data = copy.deepcopy({**data, "schema_version": SCHEMA_VERSION})
