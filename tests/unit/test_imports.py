"""Every module under src/riro/ imports cleanly (plan slice 1, section 3.1)."""

import importlib
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
PACKAGE = SRC / "riro"

# docs/architecture.md section 4
EXPECTED = {
    "riro.__main__",
    "riro.ui.bridge",
    "riro.services.sync",
    "riro.services.joiners",
    "riro.services.diagnostics",
    "riro.core.checklist",
    "riro.core.deadlines",
    "riro.core.status",
    "riro.core.models",
    "riro.connectors.sharepoint.edge",
    "riro.connectors.sharepoint.edge_process",
    "riro.connectors.sharepoint.cdp",
    "riro.connectors.sharepoint.client",
    "riro.connectors.sharepoint.session",
    "riro.connectors.sharepoint.urls",
    "riro.connectors.sharepoint.errors",
    "riro.store.datafile",
    "riro.store.repo",
}


def discover_modules() -> list[str]:
    # File system walk, not pkgutil: without __init__.py files pkgutil misses the subpackages.
    names = []
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(SRC).with_suffix("").parts
        names.append(".".join(parts))
    return names


def test_discovery_finds_every_module_in_the_architecture():
    assert EXPECTED <= set(discover_modules())


@pytest.mark.parametrize("name", discover_modules())
def test_module_imports(name):
    importlib.import_module(name)
