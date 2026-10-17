"""Run from ha/: python -m pytest tests"""

import pathlib
import sys

import pytest

# The test plugin ships its own `custom_components` package; make sure ours wins.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.modules.pop("custom_components", None)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return
