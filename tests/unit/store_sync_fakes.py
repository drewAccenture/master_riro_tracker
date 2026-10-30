"""Fakes for the slice 3 sync tests (US-06, US-07, US-09, US-10). Synthetic data only, invented names."""


class Folder:
    """A fake connector over a synthetic SharePoint folder. Files keep the order they were put in."""

    def __init__(self):
        self.files = {}  # id -> {"name", "etag", "modified", "data"}
        self.fail = {}  # step name -> exception for the whole call
        self.download_fail = {}  # file id -> exception for that one download
        self.calls = []
        self.downloads = []

    def put(self, file_id, name, data, etag=None, modified="2026-10-20"):
        self.files[file_id] = {
            "name": name,
            "etag": etag or f"e-{file_id}-1",
            "modified": modified,
            "data": data,
        }

    def change(self, file_id, data, etag):
        self.files[file_id]["data"] = data
        self.files[file_id]["etag"] = etag

    def remove(self, file_id):
        del self.files[file_id]

    def _step(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]

    def sign_in(self):
        self._step("sign_in")

    def health_ping(self):
        self._step("health_ping")

    def list_files(self):
        self._step("list_files")
        return [
            {
                "id": file_id,
                "name": f["name"],
                "etag": f["etag"],
                "modified": f["modified"],
                "size": len(f["data"]),
            }
            for file_id, f in self.files.items()
        ]

    def download(self, file_id):
        self._step("download")
        self.downloads.append(file_id)
        if file_id in self.download_fail:
            raise self.download_fail[file_id]
        return self.files[file_id]["data"]

    def close(self):
        self.calls.append("close")

    def shutdown(self):
        self.calls.append("shutdown")


class FakeDiagnostics:
    def __init__(self):
        self.events = []
        self.file_reports = []

    def event(self, step, **fields):
        self.events.append((step, fields))

    def file_report(self, index, total, report):
        self.file_reports.append((index, total, report))

    def of(self, step):
        return [fields for name, fields in self.events if name == step]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Wall:
    """A wall clock the test moves by hand: every call returns the same time until the test changes it."""

    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t
