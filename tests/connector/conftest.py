"""Fixtures shared by the connector tests. The fakes themselves live in sharepoint_fakes.py."""

import pytest
from sharepoint_fakes import (  # noqa: F401 - pytest finds fixtures by name here
    assert_throwaway_profile,
    hanging_port,
    servers,
)


@pytest.fixture
def live_profile(tmp_path):
    """Throwaway Edge profile for a live test (ADR-011): under pytest's temp folder, never the app's profile
    (%LOCALAPPDATA%\\RIROTracker) or the everyday Edge profile."""
    return assert_throwaway_profile(tmp_path / "edge_profile")
