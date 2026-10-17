"""TEMPORARY diagnostic: why the loader can't see the integration."""

import sys

from homeassistant import loader


async def test_diag(hass):
    import custom_components  # noqa: PLC0415

    print("\nDIAG module path", list(custom_components.__path__))
    print("DIAG sys.path head", sys.path[:5])
    print("DIAG found", sorted(await loader.async_get_custom_components(hass)))
