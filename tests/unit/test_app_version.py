"""Slice 8a (plan 3.4): the app version names the slice, so the report shows which package she runs (US-16)."""

import riro.__main__ as app


def test_us15_app_version_is_0_9_0_after_slice_8b():
    assert app.APP_VERSION == "0.9.0"
