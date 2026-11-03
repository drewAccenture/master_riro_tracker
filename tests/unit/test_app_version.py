"""Slice 8a (plan 3.4): the app version names the slice, so the report shows which package she runs (US-16)."""

import riro.__main__ as app


def test_us15_app_version_is_0_8_0_for_slice_8a():
    assert app.APP_VERSION == "0.8.0"
