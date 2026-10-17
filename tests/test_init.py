"""Behaviour + safety tests for pip_notifications.show (HA's own test harness, no real network)."""

import asyncio
import re
import base64
from unittest.mock import patch

import aiohttp
import pytest
import voluptuous as vol

from homeassistant.components.camera import Image
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component

DOMAIN = "pip_notifications"
TOKEN = "t" * 32
TV1, TV2 = "http://192.0.2.10:7979/notify", "http://192.0.2.11:7979/notify"
JPEG = b"\xff\xd8\xff fake jpeg bytes"


@pytest.fixture
async def setup(
    hass: HomeAssistant, aioclient_mock
):  # mock first: setup grabs the session
    hass.states.async_set("camera.front", "idle", {"friendly_name": "Front Door"})
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            DOMAIN: {
                "token": TOKEN,
                "tvs": {"living_room": "192.0.2.10", "kitchen": "192.0.2.11"},
            }
        },
    )
    with patch(
        "custom_components.pip_notifications.async_get_image",
        return_value=Image("image/jpeg", JPEG),
    ):
        yield


async def show(hass, **data):
    return await hass.services.async_call(
        DOMAIN,
        "show",
        {"camera": "camera.front", **data},
        blocking=True,
        return_response=True,
    )


def ai_service(hass, handler):
    hass.services.async_register(
        "ai_task", "generate_data", handler, supports_response=SupportsResponse.ONLY
    )


async def test_short_token_rejected(hass: HomeAssistant, caplog):
    assert not await async_setup_component(
        hass, DOMAIN, {DOMAIN: {"token": "short", "tvs": {"a": "192.0.2.1"}}}
    )
    # Must fail on the token length, not because the integration wasn't found.
    assert "Integration not found" not in caplog.text
    assert "Invalid config for 'pip_notifications'" in caplog.text
    assert not hass.services.has_service(DOMAIN, "show")


async def test_valid_config_registers_service(hass: HomeAssistant, setup):
    assert hass.services.has_service(DOMAIN, "show")


async def test_delivers_to_all_tvs(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")
    events = []
    hass.bus.async_listen(f"{DOMAIN}_shown", events.append)

    res = await show(hass, location="Porch")
    await hass.async_block_till_done()

    assert sorted(res["delivered"]) == ["kitchen", "living_room"]
    assert len(aioclient_mock.mock_calls) == 2
    for _method, _url, payload, headers in aioclient_mock.mock_calls:
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        assert payload["camera"] == "Front Door"  # friendly name
        assert payload["location"] == "Porch"
        assert payload["duration"] == 5
        assert base64.b64decode(payload["image"]) == JPEG
        assert payload["timestamp"]
    # The image and the token never leak into the response or the event bus.
    assert "image" not in res and TOKEN not in str(res)
    assert (
        len(events) == 1
        and "image" not in events[0].data
        and TOKEN not in str(events[0].data)
    )


async def test_subset_and_name_override(hass, setup, aioclient_mock):
    aioclient_mock.post(TV2, text="ok")
    res = await show(hass, tvs=["kitchen"], name="Back gate", duration=12)
    assert res["delivered"] == ["kitchen"]
    (_m, url, payload, _h) = aioclient_mock.mock_calls[0]
    assert (
        str(url) == TV2
        and payload["camera"] == "Back gate"
        and payload["duration"] == 12
    )


async def test_unknown_tv(hass, setup, aioclient_mock):
    with pytest.raises(ServiceValidationError):
        await show(hass, tvs=["garage"])
    assert not aioclient_mock.mock_calls


@pytest.mark.parametrize(
    "bad", [{"duration": 2}, {"duration": 121}, {"camera": "not an entity"}]
)
async def test_schema_rejects(hass, setup, bad):
    with pytest.raises(vol.Invalid):
        await show(hass, **bad)


async def test_tv_failures_are_isolated(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, exc=aiohttp.ClientError("down"))
    aioclient_mock.post(TV2, status=401)
    res = await show(hass)
    assert res["delivered"] == []  # nothing raised, nothing claimed


async def test_tv_timeout(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, exc=TimeoutError())
    aioclient_mock.post(TV2, text="ok")
    assert (await show(hass))["delivered"] == ["kitchen"]


async def test_ai_analysis_updates_popup(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")
    seen = {}

    async def handler(call):
        seen.update(call.data)
        return {"data": "  A courier holding a parcel.  "}

    ai_service(hass, handler)
    res = await show(hass, ai_task_entity="ai_task.local")

    assert res["analysis"] == "A courier holding a parcel."
    assert len(aioclient_mock.mock_calls) == 4  # popup first, then the analysed version
    assert all(c[2]["analysis"] == "" for c in aioclient_mock.mock_calls[:2])
    assert all(
        c[2]["analysis"] == res["analysis"] for c in aioclient_mock.mock_calls[2:]
    )
    assert seen["entity_id"] == "ai_task.local"
    assert (
        seen["attachments"][0]["media_content_id"]
        == "media-source://camera/camera.front"
    )


async def test_ai_failure_never_blocks_alert(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")

    async def handler(call):
        raise HomeAssistantError("provider down")

    ai_service(hass, handler)
    res = await show(hass, ai_task_entity="ai_task.local")
    assert res["analysis"] == "" and len(res["delivered"]) == 2


async def test_ai_timeout(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")

    async def handler(call):
        await asyncio.sleep(5)
        return {"data": "too late"}

    ai_service(hass, handler)
    with patch("custom_components.pip_notifications.AI_TIMEOUT", 0.05):
        res = await asyncio.wait_for(show(hass, ai_task_entity="ai_task.local"), 2)
    assert res["analysis"] == "" and len(res["delivered"]) == 2


async def test_missing_ai_service(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")
    res = await show(
        hass, ai_task_entity="ai_task.missing"
    )  # ai_task not set up at all
    assert res["analysis"] == "" and len(res["delivered"]) == 2


async def test_analysis_passthrough(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")
    res = await show(hass, analysis="From my own pipeline")
    assert res["analysis"] == "From my own pipeline"
    assert all(
        c[2]["analysis"] == "From my own pipeline" for c in aioclient_mock.mock_calls
    )


async def test_snapshot_failure_sends_text_only(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")
    ai_calls = []

    async def handler(call):
        ai_calls.append(call)
        return {"data": "should not run"}

    ai_service(hass, handler)
    with patch(
        "custom_components.pip_notifications.async_get_image",
        side_effect=HomeAssistantError("WebRTC-only camera"),
    ):
        res = await show(hass, location="Porch", ai_task_entity="ai_task.local")

    assert len(res["delivered"]) == 2 and res["has_image"] is False
    assert all("image" not in c[2] for c in aioclient_mock.mock_calls)
    assert all(c[2]["camera"] == "Front Door" for c in aioclient_mock.mock_calls)
    assert not ai_calls  # nothing to analyse


async def test_has_image_true(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")
    assert (await show(hass))["has_image"] is True


async def test_custom_time_format(hass, aioclient_mock):
    hass.states.async_set("camera.front", "idle")
    assert await async_setup_component(
        hass,
        DOMAIN,
        {DOMAIN: {"token": TOKEN, "tvs": {"tv": "192.0.2.10"}, "time_format": "%H:%M"}},
    )
    aioclient_mock.post(TV1, text="ok")
    with patch(
        "custom_components.pip_notifications.async_get_image",
        return_value=Image("image/jpeg", JPEG),
    ):
        res = await show(hass)
    assert re.fullmatch(r"\d\d:\d\d", res["timestamp"])


async def test_blank_ai_entity_means_no_ai(hass, setup, aioclient_mock):
    aioclient_mock.post(TV1, text="ok")
    aioclient_mock.post(TV2, text="ok")
    res = await show(hass, ai_task_entity="", name="", tvs=[])  # blueprint defaults
    assert res["analysis"] == "" and len(res["delivered"]) == 2
    assert res["camera"] == "Front Door" and len(aioclient_mock.mock_calls) == 2
