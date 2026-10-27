"""US-07: the six connector error types (architecture section 4, errors.py)."""

import pytest

from riro.connectors.sharepoint import errors

KINDS = [
    "NeedsSignIn",
    "NoAccess",
    "NotFound",
    "Unreachable",
    "TimedOut",
    "EdgeMissing",
]


def test_us07_connector_error_is_an_exception():
    assert issubclass(errors.ConnectorError, Exception)


@pytest.mark.parametrize("name", KINDS)
def test_us07_each_error_is_a_connector_error_with_kind_equal_to_its_name(name):
    cls = getattr(errors, name)
    assert issubclass(cls, errors.ConnectorError)
    assert cls.kind == name
    assert cls().kind == name
