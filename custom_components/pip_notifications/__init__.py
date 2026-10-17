"""HA PiP Notifications: camera snapshot popups (+ optional AI) on Android TV."""

from __future__ import annotations

import asyncio
import base64
import logging

import aiohttp
import voluptuous as vol
from homeassistant.components.camera import async_get_image
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

DOMAIN = "pip_notifications"
PORT = 7979
AI_TIMEOUT = 60  # s; a hung AI provider must not block the automation
DEFAULT_TIME_FORMAT = "%-I:%M:%S %p · %a %b %-d"  # strftime; e.g. "%H:%M:%S · %a %d %b"
DEFAULT_PROMPT = (
    "In one short sentence, describe who or what is at the door "
    "and what they are doing. Do not guess identities."
)
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("token"): vol.All(cv.string, vol.Length(min=16)),
                vol.Required("tvs"): {cv.slug: cv.string},
                vol.Optional("time_format", default=DEFAULT_TIME_FORMAT): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SHOW_SCHEMA = vol.Schema(
    {
        vol.Required("camera"): cv.entity_id,
        vol.Optional("tvs"): vol.All(cv.ensure_list, [cv.slug]),
        vol.Optional("name"): cv.string,
        vol.Optional("location", default=""): cv.string,
        vol.Optional("analysis", default=""): cv.string,
        # "" = no AI (blueprints pass empty optional inputs as "")
        vol.Optional("ai_task_entity"): vol.Any("", cv.entity_id),
        vol.Optional("ai_prompt", default=DEFAULT_PROMPT): cv.string,
        vol.Optional("duration", default=5): vol.All(
            vol.Coerce(int), vol.Range(min=3, max=120)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    conf = config[DOMAIN]
    session = async_get_clientsession(hass)
    headers = {"Authorization": f"Bearer {conf['token']}"}

    async def push(tv: str, payload: dict) -> bool:
        try:
            async with session.post(
                f"http://{conf['tvs'][tv]}:{PORT}/notify",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    return True
                _LOGGER.warning("TV %s answered %s", tv, r.status)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("TV %s unreachable: %s", tv, err)
        return False

    async def push_all(tvs: list[str], payload: dict) -> list[str]:
        ok = await asyncio.gather(*(push(tv, payload) for tv in tvs))
        return [tv for tv, sent in zip(tvs, ok) if sent]

    async def show(call: ServiceCall) -> ServiceResponse:
        d = call.data
        tvs = d.get("tvs") or list(conf["tvs"])
        if unknown := [tv for tv in tvs if tv not in conf["tvs"]]:
            raise ServiceValidationError(f"Unknown TV(s): {', '.join(unknown)}")

        camera = d["camera"]
        try:
            image = await async_get_image(hass, camera)
        except HomeAssistantError as err:
            # e.g. WebRTC-only Nest cameras, offline cameras: still alert, text only.
            _LOGGER.warning("No snapshot from %s (%s); sending text only", camera, err)
            image = None
        state = hass.states.get(camera)
        payload = {
            "camera": d.get("name") or (state.name if state else camera),
            "location": d["location"],
            "timestamp": dt_util.now().strftime(conf["time_format"]),
            "analysis": d["analysis"],
            "duration": d["duration"],
        }
        if image:
            payload["image"] = base64.b64encode(image.content).decode()
        delivered = await push_all(tvs, payload)

        # Popup goes up first; AI (often slow) then replaces it with the analysed one.
        if (ai := d.get("ai_task_entity")) and image:
            try:
                async with asyncio.timeout(AI_TIMEOUT):
                    res = await hass.services.async_call(
                        "ai_task",
                        "generate_data",
                        {
                            "entity_id": ai,
                            "task_name": "pip_notifications",
                            "instructions": d["ai_prompt"],
                            "attachments": [
                                {
                                    "media_content_id": f"media-source://camera/{camera}",
                                    "media_content_type": image.content_type,
                                }
                            ],
                        },
                        blocking=True,
                        return_response=True,
                    )
                # New dict: never mutate a payload that was already handed to a send.
                payload = {**payload, "analysis": str(res.get("data", "")).strip()}
                delivered = await push_all(tvs, payload)
            except Exception as err:  # noqa: BLE001 - AI failure never blocks the alert
                _LOGGER.warning("AI analysis failed: %s", err)

        result = {k: v for k, v in payload.items() if k != "image"} | {
            "entity_id": camera,
            "has_image": image is not None,
            "delivered": delivered,
        }
        hass.bus.async_fire(f"{DOMAIN}_shown", result)
        return result

    hass.services.async_register(
        DOMAIN,
        "show",
        show,
        schema=SHOW_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True
