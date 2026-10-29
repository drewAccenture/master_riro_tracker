"""US-16, ADR-007: known names, enterprise ids, a cookie, a token and a URL query never reach the report or the log.

Real Diagnostics with tmp_path as log_dir, real SyncService and check_headers, fake connector. Synthetic data only.
"""

from datetime import datetime

from riro.connectors.sharepoint import errors
from riro.core.models import HeaderReport
from riro.services.diagnostics import Diagnostics
from riro.services.sync import SyncService

REQUIRED_HEADERS = (
    "Checklist Owner",
    "Role",
    "Task Number",
    "Description",
    "Completion Status",
    "Completion Date",
    "Deadline",
)
NAME = "Test Person A"
ENTERPRISE_ID = "test.person.a"
COOKIE = "FedAuth=SECRET123"
TOKEN = "Bearer eyJSECRET"
QUERY_URL = (
    "https://ts.accenture.com/sites/WFR-USTEAM/Shared%20Documents/Test%20Person%20A.xlsx"
    "?token=SECRET&user=test.person.a"
)
FORBIDDEN = [
    NAME,
    NAME.lower(),
    "Test%20Person%20A",
    "Person A",
    ENTERPRISE_ID,
    COOKIE,
    "FedAuth",
    TOKEN,
    "eyJ",
    "SECRET",
    "token=",
]
VERSIONS = {"app": "0.1.0-test", "python": "3.13.9"}
NOW = datetime(2026, 10, 27, 9, 0, 0)


class FakeConnector:
    def __init__(self, data):
        self.data = data
        self.fail_list = None

    def sign_in(self):
        pass

    def health_ping(self):
        pass

    def list_files(self):
        if self.fail_list:
            raise self.fail_list
        return [
            {
                "id": "id-" + ENTERPRISE_ID,
                "name": NAME + " - checklist.xlsx",
                "etag": COOKIE,
                "modified": "2026-10-20T08:00:00Z",
                "size": 1234,
            }
        ]

    def download(self, file_id):
        return self.data

    def close(self):
        pass


def personal_checklist(make_xlsx):
    header = list(REQUIRED_HEADERS) + ["Assigned Enterprise Id", "Remarks (Tracker)"]
    row = [
        NAME,
        "PMO",
        1,
        "Task for " + NAME,
        "Completed",
        None,
        "On Roll On",
        ENTERPRISE_ID,
        TOKEN,
    ]
    # Sheet named after the person: no "roll-in" in it, so it is the sheet chosen.
    return make_xlsx([(NAME, [header, row, row])])


def feed_everything(diag):
    # Unknown fields.
    diag.event(
        "list", nickname=NAME, owner=ENTERPRISE_ID, cookie=COOKIE, authorization=TOKEN
    )
    # Strings in number fields and in enum fields.
    diag.event(
        "list",
        duration_s=NAME,
        http_status=COOKIE,
        attempt=TOKEN,
        files_count=ENTERPRISE_ID,
    )
    diag.event("download", result=NAME, error_kind=COOKIE)
    # URL with a query string and a folder path.
    diag.event("download", url=QUERY_URL, result="ok")
    # Unknown step holding a name.
    diag.event(NAME, result="ok")
    # Header report whose sheet name is a person's name.
    diag.file_report(
        1,
        1,
        HeaderReport(
            sheet_name=NAME,
            sheet_matched=False,
            headers_found=tuple(REQUIRED_HEADERS),
            headers_missing=(),
            row_count=2,
            deadline_counts={"On Roll On": 2},
            status_counts={"Completed": 2},
        ),
    )


def all_log_text(log_dir):
    files = [p for p in log_dir.rglob("*") if p.is_file()]
    return files, "".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files
    )


def assert_clean(text, where):
    leaks = [secret for secret in FORBIDDEN if secret in text]
    assert leaks == [], f"{where} contains {leaks}"


def test_us16_adr007_direct_events_never_leak(tmp_path):
    diag = Diagnostics(tmp_path, versions=VERSIONS, now=lambda: NOW)
    feed_everything(diag)

    report = diag.report()
    files, log = all_log_text(tmp_path)

    assert "list" in report  # the events were recorded, so the check below is not empty
    assert files, "no log file written under log_dir"
    assert "list" in log
    assert_clean(report, "report()")
    assert_clean(log, "log file")


def test_us16_adr007_sync_run_never_leaks(tmp_path, make_xlsx):
    diag = Diagnostics(tmp_path, versions=VERSIONS, now=lambda: NOW)
    connector = FakeConnector(personal_checklist(make_xlsx))
    service = SyncService(connector, diag, now=lambda: NOW)

    ok = service.sync()
    connector.fail_list = errors.NoAccess(
        f"{NAME} {ENTERPRISE_ID} {COOKIE} {TOKEN} {QUERY_URL}"
    )
    failed = service.sync()

    assert ok.state == "ok"
    assert failed.state == "failed"
    report = diag.report()
    files, log = all_log_text(tmp_path)
    assert "file 1 of" in report
    assert files, "no log file written under log_dir"
    assert_clean(report, "report()")
    assert_clean(log, "log file")
    assert_clean(failed.message, "SyncResult.message")
