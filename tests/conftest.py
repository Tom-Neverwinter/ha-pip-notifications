"""Run from the repo root: python -m pytest tests (Linux; see CI)."""

import pathlib

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

OURS = str(pathlib.Path(__file__).resolve().parents[1] / "custom_components")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    # The test plugin imports its own `custom_components` package (testing_config);
    # add our folder to that package so HA's loader finds pip_notifications.
    import custom_components  # noqa: PLC0415

    if OURS not in custom_components.__path__:
        custom_components.__path__.append(OURS)
