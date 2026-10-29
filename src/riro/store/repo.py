"""Read and change what the app keeps: file records, joiners and their roll-on dates, last successful sync, sync runs.

The JSON layout stays inside store/. Services only see the dataclasses from core.models.
"""

import copy
import threading
from collections.abc import Iterable
from datetime import date, datetime

from riro.core.models import FileRecord, Joiner, SyncRun
from riro.store import codec
from riro.store.datafile import MemoryDataFile

MAX_RUNS = 20


def check_layout(data: dict) -> None:
    """Decode everything once; raises when the layout is wrong. Passed to DataFile(validate=...)."""
    for file_id, record in data.get("files", {}).items():
        codec.record_in(file_id, record)
    for run in data.get("sync_runs", []):
        codec.run_in(run)
    for joiner_id, joiner in data.get("joiners", {}).items():
        codec.joiner_in(joiner_id, joiner)
    if data.get("last_success") is not None:
        datetime.fromisoformat(data["last_success"])


class Repo:
    def __init__(self, datafile):
        self._datafile = datafile
        self._data, self.load_note = datafile.load()
        # A sync (timer thread) and set_roll_on (page) may change the data at the same time.
        self._lock = threading.Lock()

    @classmethod
    def in_memory(cls) -> "Repo":
        return cls(MemoryDataFile())

    def file(self, file_id: str) -> FileRecord | None:
        data = self._data.get("files", {}).get(file_id)
        return None if data is None else codec.record_in(file_id, data)

    def files(self) -> tuple[FileRecord, ...]:
        stored = self._data.get("files", {})
        return tuple(
            codec.record_in(file_id, stored[file_id]) for file_id in sorted(stored)
        )

    def last_success(self) -> datetime | None:
        value = self._data.get("last_success")
        return None if value is None else datetime.fromisoformat(value)

    def runs(self) -> tuple[SyncRun, ...]:
        return tuple(codec.run_in(run) for run in self._data.get("sync_runs", []))

    def joiners(self) -> tuple[Joiner, ...]:
        stored = self._data.get("joiners", {})
        return tuple(codec.joiner_in(jid, stored[jid]) for jid in sorted(stored))

    def apply(
        self,
        records: Iterable[FileRecord],
        last_success: datetime,
        run: SyncRun,
        joiners: Iterable[Joiner] | None = None,
    ) -> None:
        """One save for a whole sync. On SaveFailed nothing changes, on disk or here.

        joiners replaces the joiners section, but a stored roll-on date always wins: only set_roll_on changes a date,
        so a date typed while the sync ran is never lost (US-03).
        """
        with self._lock:
            data = copy.deepcopy(self._data)
            files = data.setdefault("files", {})
            for record in records:
                files[record.id] = codec.record_out(record)
            if joiners is not None:
                stored = data.get("joiners", {})
                section = {}
                for joiner in joiners:
                    out = codec.joiner_out(joiner)
                    if joiner.id in stored:
                        out["roll_on"] = stored[joiner.id]["roll_on"]
                    section[joiner.id] = out
                data["joiners"] = section
            data["last_success"] = last_success.isoformat()
            self._commit(data, run)

    def add_run(self, run: SyncRun) -> None:
        with self._lock:
            self._commit(copy.deepcopy(self._data), run)

    def set_roll_on(self, joiner_id: str, roll_on: date) -> None:
        """One save. KeyError for an unknown joiner."""
        with self._lock:
            data = copy.deepcopy(self._data)
            data.get("joiners", {})[joiner_id]["roll_on"] = roll_on.isoformat()
            self._datafile.save(data)
            self._data = data

    def _commit(self, data: dict, run: SyncRun) -> None:
        data["sync_runs"] = [*data.get("sync_runs", []), codec.run_out(run)][-MAX_RUNS:]
        self._datafile.save(data)
        self._data = data
