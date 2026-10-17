"""TEMPORARY diagnostic: why the loader can't see the integration."""

import inspect

from homeassistant import loader


async def test_diag(hass):
    print("\nDIAG recovery_mode", hass.config.recovery_mode, "safe_mode", hass.config.safe_mode)
    print("DIAG config_dir", hass.config.config_dir)
    src = inspect.getsource(loader._async_get_custom_components)
    print("DIAG source:\n" + "\n".join("DIAG| " + line for line in src.splitlines()[:40]))
    comps = await loader.async_get_custom_components(hass)
    print("DIAG found", sorted(comps))
