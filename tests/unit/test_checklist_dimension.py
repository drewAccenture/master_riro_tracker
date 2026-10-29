"""US-05: rows are never dropped without a message, even when the file's stored sheet size is wrong.

Some tools write a <dimension> smaller than the real data; openpyxl read-only mode trusts it unless reset.
"""

import re
import zipfile
from io import BytesIO

from riro.core.checklist import check_headers, read


def _with_dimension(data: bytes, ref: str) -> bytes:
    """Rewrite the first worksheet's stored size, like a non-Excel tool that got it wrong."""
    source = zipfile.ZipFile(BytesIO(data))
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = re.sub(
                    rb'<dimension ref="[^"]*"',
                    f'<dimension ref="{ref}"'.encode(),
                    content,
                )
            target.writestr(item, content)
    return out.getvalue()


def test_us05_rows_past_a_wrong_stored_size_are_still_read(make_checklist, make_row):
    rows = [make_row(n, f"Invented task {n}") for n in range(1, 6)]
    data = _with_dimension(make_checklist(rows), "A1:I3")
    assert [t.number for t in read(data).tasks] == ["1", "2", "3", "4", "5"]
    assert check_headers(data).row_count == 5


def test_us02_row_shorter_than_header_reads_missing_cells_as_empty(
    make_checklist, make_row
):
    # No Assigned Enterprise Id or Remarks cells.
    short = make_row(1, "Invented short row")[:7]
    data = _with_dimension(make_checklist([short]), "A1:G2")
    task = read(data).tasks[0]
    assert (task.description, task.assigned_id, task.remarks) == (
        "Invented short row",
        "",
        "",
    )
