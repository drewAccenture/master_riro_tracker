"""The one data file: atomic save, .bak copy, retries, load fallbacks, schema_version (ADR-004, ADR-013).

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
# Step from layout n to n+1 (ADR-004). Empty while SCHEMA_VERSION is 1.
UPGRADES: dict[int, Callable[[dict], dict]] = {}
RESTORED_FROM_BACKUP = "Your data was restored from the backup copy."
STARTED_EMPTY = "Your data file was broken and no backup could be read. The app started with no data."
NEWER_VERSION = (
    "Your data was saved by a newer version of the tracker. "
    "Install the newer version again; nothing was changed."
)
_ATTEMPTS = 6  # ADR-004: 1 attempt + 5 retries
_RETRY_WAIT_S = 0.2


class SaveFailed(Exception):
    """Windows kept refusing to replace the data file. The old file is unchanged."""


def _empty(version: int = SCHEMA_VERSION) -> dict:
    return {"schema_version": version}


class _Newer:
    """_read's answer for a file from a newer version (ADR-013): its data, or None when the layout check fails."""

    def __init__(self, data: dict | None):
        self.data = data


class DataFile:
    def __init__(
        self,
        path: Path,
        *,
        now: Callable[[], datetime] = datetime.now,
        replace: Callable = os.replace,
        sleep: Callable[[float], None] = time.sleep,
        validate: Callable[[dict], None] = lambda data: None,
        schema_version: int = SCHEMA_VERSION,
        upgrades: dict[int, Callable[[dict], dict]] | None = None,
    ):
        """validate raises when the layout is wrong (store.repo.check_layout); that file then counts as broken.
        schema_version and upgrades are for tests; upgrades=None means UPGRADES."""
        self._path = Path(path)
        self._bak = Path(f"{path}.bak")
        self._tmp = Path(f"{path}.tmp")
        self._now = now
        self._replace = replace
        self._sleep = sleep
        self._lock = threading.Lock()
        self._validate = validate
        self._version = schema_version
        self._upgrades = upgrades
        self._read_only = False

    def _valid(self, data: dict) -> bool:
        try:
            self._validate(data)
        except Exception:  # noqa: BLE001 - any layout problem means "broken", so the backup is used
            return False
        return True

    def _keep_copy(self, path: Path, raw: bytes, version: int) -> None:
        """ADR-004: the file as it was, before any upgrade step. An existing copy is never overwritten."""
        stamp = f"{self._now():%Y%m%d-%H%M%S}"
        for n in range(100):
            name = f"{path.name}.v{version}-{stamp}" + (f"-{n}" if n else "")
            try:
                with open(path.with_name(name), "xb") as handle:
                    handle.write(raw)
                return
            except FileExistsError:
                continue
            except OSError:
                return  # the original is still on disk and becomes .bak at the next save

    def _upgrade(
        self, data: dict, version: int, keep: Callable[[], None]
    ) -> dict | None:
        upgrades = UPGRADES if self._upgrades is None else self._upgrades
        steps = [upgrades.get(n) for n in range(version, self._version)]
        if None in steps:
            return None  # no way from this layout to ours
        keep()
        try:
            for n, step in zip(range(version, self._version), steps, strict=True):
                data = {**step(data), "schema_version": n + 1}
        except Exception:  # noqa: BLE001 - a step that cannot read this file means "broken"
            return None
        return data

    def _read(self, path: Path, *, keep_copy: bool = False):
        """The data in `path` (upgraded when older), a _Newer, or None when missing, not JSON or the wrong layout."""
        try:
            raw = path.read_bytes()
            data = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        version = data.get("schema_version")
        if type(version) is not int or version < 1:
            return None  # layouts start at 1 (ADR-004); never build a step list for a hand-edited number
        if version > self._version:
            return _Newer(data if self._valid(data) else None)
        if version < self._version:
            data = self._upgrade(
                data,
                version,
                lambda: keep_copy and self._keep_copy(path, raw, version),
            )
            if data is None:
                return None
        return data if self._valid(data) else None

    def _opened_newer(self, answer: "_Newer") -> tuple[dict, str]:
        self._read_only = True
        return (
            answer.data if answer.data is not None else _empty(self._version)
        ), NEWER_VERSION

    def load(self) -> tuple[dict, str | None]:
        with self._lock:
            self._read_only = False
            data = (
                self._read(self._path, keep_copy=True) if self._path.exists() else None
            )
            if isinstance(data, _Newer):
                return self._opened_newer(data)
            if data is not None:
                return data, None
            backup = (
                self._read(self._bak, keep_copy=True) if self._bak.exists() else None
            )
            if isinstance(backup, _Newer):
                return self._opened_newer(backup)
            if backup is not None:
                return backup, RESTORED_FROM_BACKUP
            if not self._path.exists():
                return _empty(self._version), None
            broken = self._path.with_name(
                f"{self._path.name}.broken-{self._now():%Y%m%d-%H%M%S}"
            )
            try:
                self._replace(self._path, broken)
            except OSError:
                pass  # held by another program: it stays, and is never copied to .bak (save checks it)
            return _empty(self._version), STARTED_EMPTY

    def save(self, data: dict) -> None:
        payload = {**data, "schema_version": self._version}
        with self._lock:
            if self._read_only:
                raise SaveFailed("the data file was saved by a newer version")
            current = self._read(self._path) if self._path.exists() else None
            if isinstance(current, _Newer):
                self._read_only = (
                    True  # ADR-013: never overwrite what a newer version wrote
                )
                raise SaveFailed("the data file was saved by a newer version")
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._tmp, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=1)
                    handle.flush()
                    os.fsync(handle.fileno())
                # Only a good file becomes the backup: a broken one must never replace the copy it was restored from.
                if current is not None:
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
