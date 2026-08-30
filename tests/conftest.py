"""Pytest fixtures for fuzzy-train.

The script filename contains a hyphen, so it can't be imported normally;
we load it via importlib from its file path.
"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "fuzzy-train.py"


def _load(faker_absent: bool) -> ModuleType:
    """Load fuzzy-train.py as a fresh module.

    If faker_absent is True, block `import faker` first (by swapping sys.modules)
    so the module's try/except sets FAKER_AVAILABLE = False (built-in fallback
    path). A fresh exec per call also resets the module's TRACE_ID_COUNTER global,
    keeping tests isolated.
    """
    saved = sys.modules.get("faker")
    if faker_absent:
        sys.modules["faker"] = None  # forces ImportError on `from faker import Faker`
    try:
        spec = importlib.util.spec_from_file_location("fuzzy_train_under_test", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {SCRIPT}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        # restore whatever was there so other fixtures load cleanly
        if faker_absent:
            if saved is None:
                sys.modules.pop("faker", None)
            else:
                sys.modules["faker"] = saved
    return mod


@pytest.fixture
def ft() -> ModuleType:
    """fuzzy-train module loaded normally (faker present if installed)."""
    return _load(faker_absent=False)


@pytest.fixture
def ft_no_faker() -> ModuleType:
    """fuzzy-train module loaded with faker forced absent (fallback path)."""
    return _load(faker_absent=True)


@pytest.fixture
def script_path() -> str:
    """Absolute path to the script, for subprocess/CLI tests."""
    return str(SCRIPT)
