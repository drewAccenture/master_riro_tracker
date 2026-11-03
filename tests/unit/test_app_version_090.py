"""Slice 8b (plan 3.5): the app version names the slice, so the report shows which package she runs (US-16)."""

import riro.__main__ as app


def test_us16_app_version_is_0_9_0_for_slice_8b():
    assert app.APP_VERSION == "0.9.0"
