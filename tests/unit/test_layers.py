"""Dependency rules between layers (docs/architecture.md section 5, plan slice 1 section 3.2)."""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_LAYERS = {
    "ui": {"ui", "services"},
    "services": {"services", "core", "store", "connectors"},
    "core": {"core"},
    "store": {"store"},  # plus riro.core.models, see allowed()
    "connectors": {"connectors"},
}
MAY_IMPORT = {
    "entry": "any layer",
    "ui": "ui, services",
    "services": "services, core, store, connectors",
    "core": "core",
    "store": "store, riro.core.models",
    "connectors": "connectors",
}


def layer_of(module: str) -> str | None:
    if module == "riro.__main__":
        return "entry"
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "riro" and parts[1] in ALLOWED_LAYERS:
        return parts[1]
    return None


def allowed(source_layer: str | None, target: str) -> bool:
    target_layer = layer_of(target)
    if target_layer is None or target_layer == "entry":
        return False  # bare riro, riro.__main__, or a riro.* name with no rule
    if source_layer == "entry":
        return True
    if source_layer == "store" and (
        target == "riro.core.models" or target.startswith("riro.core.models.")
    ):
        return True
    return target_layer in ALLOWED_LAYERS.get(source_layer, set())


def is_riro(name: str) -> bool:
    return name == "riro" or name.startswith("riro.")


def import_targets(node: ast.AST, package: str, packages: set[str]) -> list[str]:
    """riro.* names imported by one node. "?" means a dynamic import that cannot be checked."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names if is_riro(alias.name)]
    if isinstance(node, ast.ImportFrom):
        base = node.module or ""
        if node.level:
            parts = package.split(".")
            parts = parts[: len(parts) - (node.level - 1)]
            base = ".".join(parts + ([node.module] if node.module else []))
        if not is_riro(base):
            return []
        if base in packages:  # from riro.core import models -> riro.core.models
            return [base if a.name == "*" else f"{base}.{a.name}" for a in node.names]
        return [base]
    if isinstance(node, ast.Call):
        func = node.func
        name = (
            func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        )
        if name not in ("import_module", "__import__") or not node.args:
            return []
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if is_riro(arg.value):
                return [arg.value]
            return ["?"] if arg.value.startswith(".") else []
        return ["?"]
    return []


def find_violations(root: Path) -> list[str]:
    src = root / "src"
    riro = src / "riro"
    packages = {"riro"} | {
        ".".join(p.relative_to(src).parts) for p in riro.rglob("*") if p.is_dir()
    }
    found = []
    for path in sorted(riro.rglob("*.py")):
        module = ".".join(path.relative_to(src).with_suffix("").parts)
        package = module.rsplit(".", 1)[0]
        source_layer = layer_of(module)
        label = source_layer or module
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for target in import_targets(node, package, packages):
                if target == "?":
                    message = f"{label} has a dynamic import that cannot be checked"
                elif allowed(source_layer, target):
                    continue
                else:
                    may = MAY_IMPORT.get(
                        source_layer, "nothing (no rule for this folder)"
                    )
                    message = f"{label} imports {target} ({label} may import: {may})"
                found.append((rel, node.lineno, message))
    return [f"{rel}:{line}: {message}" for rel, line, message in sorted(found)]


# --- synthetic trees -------------------------------------------------------------------------------------------

PACKAGES = (
    "ui",
    "ui/web",
    "services",
    "core",
    "store",
    "connectors",
    "connectors/sharepoint",
)


def make_tree(root: Path, files: dict[str, str]) -> Path:
    riro = root / "src" / "riro"
    for package in PACKAGES:
        (riro / package).mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        path = riro / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


VIOLATIONS = {
    "core_to_services_absolute": (
        "core/status.py",
        "import os\nfrom riro.services import sync\n",
        "src/riro/core/status.py:2: core imports riro.services.sync (core may import: core)",
    ),
    "core_to_services_relative": (
        "core/status.py",
        "from ..services import sync\n",
        "src/riro/core/status.py:1: core imports riro.services.sync (core may import: core)",
    ),
    "core_to_services_inside_function": (
        "core/status.py",
        "def f():\n    import riro.services.sync\n",
        "src/riro/core/status.py:2: core imports riro.services.sync (core may import: core)",
    ),
    "core_to_services_type_checking": (
        "core/status.py",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from riro.services.sync import SyncService\n",
        "src/riro/core/status.py:3: core imports riro.services.sync (core may import: core)",
    ),
    "core_to_services_dunder_import": (
        "core/status.py",
        '__import__("riro.services.sync")\n',
        "src/riro/core/status.py:1: core imports riro.services.sync (core may import: core)",
    ),
    "store_to_core_status": (
        "store/repo.py",
        "from riro.core import status\n",
        "src/riro/store/repo.py:1: store imports riro.core.status (store may import: store, riro.core.models)",
    ),
    "ui_to_core": (
        "ui/bridge.py",
        "from riro.core.models import HeaderReport\n",
        "src/riro/ui/bridge.py:1: ui imports riro.core.models (ui may import: ui, services)",
    ),
    "connectors_to_core": (
        "connectors/sharepoint/client.py",
        "import riro.core.models\n",
        (
            "src/riro/connectors/sharepoint/client.py:1: connectors imports riro.core.models "
            "(connectors may import: connectors)"
        ),
    ),
    "services_to_ui_import_module": (
        "services/sync.py",
        'import importlib\nimportlib.import_module("riro.ui.bridge")\n',
        (
            "src/riro/services/sync.py:2: services imports riro.ui.bridge "
            "(services may import: services, core, store, connectors)"
        ),
    ),
    "dynamic_non_literal": (
        "services/sync.py",
        'import importlib\nname = "riro.ui.bridge"\nimportlib.import_module(name)\n',
        "src/riro/services/sync.py:3: services has a dynamic import that cannot be checked",
    ),
    "services_to_main": (
        "services/sync.py",
        "import riro.__main__\n",
        (
            "src/riro/services/sync.py:1: services imports riro.__main__ "
            "(services may import: services, core, store, connectors)"
        ),
    ),
    "bare_riro_package": (
        "services/sync.py",
        "import riro\n",
        "src/riro/services/sync.py:1: services imports riro (services may import: services, core, store, connectors)",
    ),
    "unknown_top_level_folder": (
        "services/sync.py",
        "from riro.utils import helpers\n",
        (
            "src/riro/services/sync.py:1: services imports riro.utils "
            "(services may import: services, core, store, connectors)"
        ),
    ),
}


@pytest.mark.parametrize("case", sorted(VIOLATIONS))
def test_violation_is_reported_once_with_file_and_line(tmp_path, case):
    name, body, expected = VIOLATIONS[case]
    root = make_tree(tmp_path, {name: body})
    found = find_violations(root)
    assert len(found) == 1, f"expected 1, got {len(found)}: {found}"
    assert found[0] == expected


ALLOWED = {
    "core_to_core_absolute": {
        "core/status.py": "from riro.core import deadlines\n",
        "core/deadlines.py": "",
    },
    "core_to_core_relative": {
        "core/status.py": "from . import deadlines\n",
        "core/deadlines.py": "",
    },
    "ui_to_services": {"ui/bridge.py": "from riro.services import sync\n"},
    "services_to_connectors": {
        "services/sync.py": "from riro.connectors.sharepoint import client, errors\n"
    },
    "services_to_core_and_store": {
        "services/sync.py": "from riro.core import checklist\nimport riro.store.repo\n"
    },
    "store_to_core_models": {
        "store/repo.py": "from riro.core.models import HeaderReport\n"
    },
    "store_to_core_models_relative": {"store/repo.py": "from ..core import models\n"},
    "store_to_core_models_module": {"store/repo.py": "from riro.core import models\n"},
    "entry_to_ui_and_store": {
        "__main__.py": "from riro.ui import bridge\nfrom riro.store import datafile\n"
    },
    "stdlib_and_third_party_ignored": {
        "core/status.py": "import os\nimport importlib\nfrom openpyxl import Workbook\n"
    },
    "import_module_of_stdlib": {
        "core/status.py": 'import importlib\nimportlib.import_module("json")\n'
    },
}


@pytest.mark.parametrize("case", sorted(ALLOWED))
def test_allowed_import_gives_no_violation(tmp_path, case):
    root = make_tree(tmp_path, ALLOWED[case])
    assert find_violations(root) == []


def test_real_tree_follows_the_layer_rules():
    assert (REPO_ROOT / "src" / "riro" / "__main__.py").exists()
    assert find_violations(REPO_ROOT) == []
