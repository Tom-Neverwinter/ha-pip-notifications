"""TEMPORARY diagnostic: why the loader can't see the integration."""

import inspect

from homeassistant import loader


async def test_diag(hass):
    print("\nDIAG config_dir", hass.config.config_dir)
    print("DIAG names", [n for n in dir(loader) if "custom" in n.lower()])
    for name in dir(loader):
        obj = getattr(loader, name)
        if "custom" in name.lower() and inspect.isfunction(obj):
            for line in inspect.getsource(obj).splitlines()[:45]:
                print(f"DIAG {name}| {line}")
    comps = await loader.async_get_custom_components(hass)
    print("DIAG found", sorted(comps))
