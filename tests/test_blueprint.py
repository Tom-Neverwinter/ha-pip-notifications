"""The example blueprint, loaded exactly the way users load it (use_blueprint)."""

import pathlib
import shutil
from unittest.mock import patch

import pytest
from homeassistant.components.camera import Image
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

BLUEPRINT = pathlib.Path(__file__).parents[1] / "examples/blueprints/camera_popup.yaml"
TV = "http://192.0.2.10:7979/notify"


@pytest.fixture
async def ready(hass: HomeAssistant, aioclient_mock, tmp_path):
    hass.config.config_dir = str(tmp_path)
    dest = tmp_path / "blueprints/automation/hapip"
    dest.mkdir(parents=True)
    shutil.copy(BLUEPRINT, dest / "camera_popup.yaml")

    hass.states.async_set("camera.porch", "idle", {"friendly_name": "Porch Cam"})
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("event.doorbell", "2026-10-17T10:00:00.000+00:00")
    hass.states.async_set(
        "sensor.outdoor",
        "72",
        {"unit_of_measurement": "°F", "device_class": "temperature"},
    )
    assert await async_setup_component(
        hass,
        "pip_notifications",
        {"pip_notifications": {"token": "t" * 32, "tvs": {"tv": "192.0.2.10"}}},
    )
    aioclient_mock.post(TV, text="ok")
    with patch(
        "custom_components.pip_notifications.async_get_image",
        return_value=Image("image/jpeg", b"jpeg"),
    ):
        yield


async def automation(hass, **inputs):
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": "hapip/camera_popup.yaml",
                    "input": {"camera": "camera.porch", "cooldown": 0, **inputs},
                }
            }
        },
    )
    await hass.async_block_till_done()


async def set_state(hass, entity, state):
    hass.states.async_set(entity, state)
    await hass.async_block_till_done()


async def test_binary_sensor_off_to_on_only(hass, ready, aioclient_mock):
    await automation(hass, trigger_entity="binary_sensor.motion")
    await set_state(hass, "binary_sensor.motion", "on")
    assert len(aioclient_mock.mock_calls) == 1
    payload = aioclient_mock.mock_calls[0][2]
    assert payload["camera"] == "Porch Cam" and payload["duration"] == 5

    await set_state(hass, "binary_sensor.motion", "off")  # on -> off: nothing
    await set_state(hass, "binary_sensor.motion", "unavailable")
    await set_state(
        hass, "binary_sensor.motion", "on"
    )  # back from unavailable: nothing
    assert len(aioclient_mock.mock_calls) == 1


async def test_event_entity_each_new_event(hass, ready, aioclient_mock):
    await automation(hass, trigger_entity="event.doorbell", title="Doorbell")
    await set_state(hass, "event.doorbell", "2026-10-17T10:05:00.000+00:00")
    await set_state(hass, "event.doorbell", "2026-10-17T10:06:00.000+00:00")
    assert len(aioclient_mock.mock_calls) == 2
    assert aioclient_mock.mock_calls[0][2]["camera"] == "Doorbell"

    await set_state(hass, "event.doorbell", "unavailable")  # e.g. HA restart
    await set_state(hass, "event.doorbell", "2026-10-17T10:07:00.000+00:00")
    assert len(aioclient_mock.mock_calls) == 2


async def test_location_with_sensor_in_its_own_unit(hass, ready, aioclient_mock):
    await automation(
        hass,
        trigger_entity="binary_sensor.motion",
        location="Porch",
        extra_sensor="sensor.outdoor",
        duration=8,
    )
    await set_state(hass, "binary_sensor.motion", "on")
    payload = aioclient_mock.mock_calls[0][2]
    assert payload["location"] == "Porch · 72 °F" and payload["duration"] == 8


async def test_sensor_only_and_unavailable_sensor(hass, ready, aioclient_mock):
    await automation(
        hass, trigger_entity="binary_sensor.motion", extra_sensor="sensor.outdoor"
    )
    await set_state(hass, "binary_sensor.motion", "on")
    assert aioclient_mock.mock_calls[0][2]["location"] == "72 °F"

    hass.states.async_set("sensor.outdoor", "unavailable")
    await set_state(hass, "binary_sensor.motion", "off")
    await set_state(hass, "binary_sensor.motion", "on")
    assert aioclient_mock.mock_calls[1][2]["location"] == ""
