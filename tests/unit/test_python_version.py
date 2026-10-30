"""The dev venv runs the same Python minor as the packaged runtime (docs/constraints.md, Python)."""

import sys


def test_dev_python_minor_matches_packaged_runtime():
    assert sys.version_info[:2] == (3, 13)
