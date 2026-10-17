# HA PiP Notifications

[![CI](https://github.com/Tom-Neverwinter/ha-pip-notifications/actions/workflows/ci.yml/badge.svg)](https://github.com/Tom-Neverwinter/ha-pip-notifications/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Tom-Neverwinter/ha-pip-notifications)](https://github.com/Tom-Neverwinter/ha-pip-notifications/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.8%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Android TV](https://img.shields.io/badge/Android%20TV-8.0%2B-3DDC84?logo=android&logoColor=white)](#tv-app)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Tom-Neverwinter&repository=ha-pip-notifications&category=integration)

Show a camera snapshot as a small picture-in-picture popup on your Android TV / Google TV when
something happens (doorbell, motion, …), with an optional one-line AI description.
Two small pieces, no third-party libraries: a Home Assistant integration and a tiny TV app.

**Status:** early (0.4.x). Running on one Google TV (Android 14) with Home Assistant 2026.10; tested
there and in CI on the latest Home Assistant.
Options may still change between minor versions.

## What it can do
- Show a **camera snapshot**, a **title** (camera name by default), an optional **location**, the
  **time** of the snapshot (Home Assistant's local time) and optional **analysis text** in the
  top-right corner, **over whatever is playing**.
- Keep it small: the popup never covers more than **a quarter of the screen** (½ width × ½ height),
  stays for **5 s** by default (3–120 s per call) and never takes focus, so the remote keeps working.
- Send to **several TVs at once**, or only to the ones you name.
- **AI (optional):** use any [AI Task](https://www.home-assistant.io/integrations/ai_task/) provider
  you have set up in Home Assistant. The popup appears immediately, then updates with the AI's
  description. If the AI is slow (60 s limit) or fails, you still get the plain popup.
- Or pass your **own text** (`analysis:`) from any other system.
- **Pipe results onward:** the action returns what was shown (title, location, time, analysis,
  whether there was an image, which TVs received it) and fires a `pip_notifications_shown` event.
- **Still alert when there's no picture:** if the camera can't give a snapshot (offline, WebRTC-only
  Nest, cloud hiccup), you get a text-only popup instead of nothing.
- **Your units and time format:** add any sensor (e.g. outdoor temperature) and it's shown in your
  own units (°C or °F, as set in Home Assistant); pick 12- or 24-hour time with `time_format`.
- **Works with any camera integration** — Blink, Frigate, Nest, Ring, Reolink, UniFi Protect,
  Blue Iris, generic RTSP/ONVIF — via the [example blueprint](#examples).

## What it can't do
- **No live video.** It shows still snapshots, not a camera stream.
- **Android TV / Google TV only** (Android 8.0+), e.g. Chromecast with Google TV, onn. 4K, NVIDIA
  Shield, or a TV with Google TV built in. Samsung (Tizen), LG (webOS), Roku, Vizio SmartCast and
  Apple TV can't run the app — plug in an Android TV box instead. Fire TV is untested.
- **No interaction:** no buttons, no dismiss, no "unlock door". It's display-only, on purpose.
- **No sound.** Pair it with your own TTS/speaker automation if you want an announcement.
- **One popup at a time.** A new popup replaces the current one; there is no queue or history.
- **No on-screen settings** and **not in the Play Store**: you sideload the app and configure it once
  with `adb` (needs Developer options on the TV).
- **YAML setup only** in Home Assistant (no UI config flow yet).
- **No encryption on the LAN** (plain HTTP + token) — see [Security](#security).
- **Doesn't recognise people.** The default AI prompt asks for a short description and tells the AI
  not to guess identities; how good the description is depends on your AI provider.
- **Snapshot freshness depends on your camera integration** (battery cameras such as Blink may
  deliver the last motion thumbnail, a little delayed; some cameras give no snapshot at all — see
  [CAMERAS.md](examples/CAMERAS.md)). Size/position of the popup aren't configurable yet, and
  weekday/month names in the time are English.

## Install

### Home Assistant integration
- **HACS:** add this repository as a custom repository (category *Integration*), install, restart.
- **Manual:** copy `custom_components/pip_notifications` to `/config/custom_components/`, restart.

Then create two files (templates in [`examples/`](examples/)):

`/config/pip_notifications/config.yaml`
```yaml
token: !secret pip_notifications_token
tvs:
  living_room: 192.0.2.10   # your TV's IP
```
`/config/pip_notifications/secrets.yaml` (only the token — never commit it)
```yaml
pip_notifications_token: "<long random token>"
```
and add to `configuration.yaml`: `pip_notifications: !include pip_notifications/config.yaml`, then
restart. Generate a token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Optional in `config.yaml`: `time_format: "%H:%M:%S · %a %d %b"` for 24-hour time (default
`3:05:51 PM · Sat Oct 17`).

### TV app
Build it (needs JDK 17 and Android SDK build-tools 35 + platform 35; no Gradle):
```bash
bash android/build.sh        # -> android/build/ha-pip-notifications.apk
```
Install and configure over adb (enable *Developer options → USB/Wireless debugging* on the TV):
```bash
adb -s <tv> install -r android/build/ha-pip-notifications.apk
adb -s <tv> shell appops set io.github.tomneverwinter.hapip SYSTEM_ALERT_WINDOW allow
adb -s <tv> shell am broadcast -f 32 -n io.github.tomneverwinter.hapip/.ConfigReceiver \
    --es token "<same token>" --es allow <Home Assistant IP>
```
The app has no icon in the launcher; it runs as a small background service and starts again after
the TV reboots. The APK is signed with your local Android debug key; updates must use the same key.

## Use
```yaml
action: pip_notifications.show
data:
  camera: camera.front_door
  name: Front door          # optional, defaults to the camera name
  location: Porch           # optional
  duration: 5               # optional, 3-120 s
  ai_task_entity: ai_task.my_provider   # optional
response_variable: shown    # {camera, location, timestamp, analysis, duration, has_image, delivered, entity_id}
```
Typical automation: motion/doorbell trigger → `pip_notifications.show` → your TTS → a cooldown delay.

## Examples
- **Blueprint** — *Camera event → TV popup*: pick a trigger (motion/person/doorbell binary sensor or
  a doorbell event entity), a camera, and optionally a title, location, extra sensor (°C/°F), AI
  entity, duration and cooldown.

  [![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTom-Neverwinter%2Fha-pip-notifications%2Fblob%2Fmain%2Fexamples%2Fblueprints%2Fcamera_popup.yaml)

  Or copy [`examples/blueprints/camera_popup.yaml`](examples/blueprints/camera_popup.yaml) to
  `/config/blueprints/automation/`.
- **[CAMERAS.md](examples/CAMERAS.md)** — which trigger and camera to pick for Blink, Frigate, Nest,
  Ring, Reolink, UniFi Protect, Blue Iris and generic cameras, units, time formats, and a plain
  YAML automation.

## Security
**TV app**
- Listens on port **7979** and answers only allow-listed IPs (your Home Assistant), then requires
  `Authorization: Bearer <token>`. Not configured = refuses everything.
- The image arrives inside the request: the TV **never fetches URLs** and makes **no outbound
  connections**. It **stores nothing** except its token and allowlist.
- Permissions: internet (to listen), display over other apps, foreground service, start at boot.
  Not debuggable; token excluded from cloud backup and device-to-device transfer.
- Only adb/the system can change its settings (the config receiver requires `android.permission.DUMP`).

**Known limits**
- Plain HTTP on your LAN: someone sniffing the network could read the token. They would also need to
  impersonate Home Assistant's IP to use it, and the worst they can do is show a fake popup. Keep TVs
  and Home Assistant on a trusted network/VLAN.
- The listener handles one request at a time with a 5 s timeout; a misbehaving *allow-listed* host
  could slow it down. Other hosts are dropped before anything is read.

**Tested** on a real Google TV: malformed/negative/overflowing lengths, oversized headers, garbage and
random fuzz input (400 requests), slow clients, truncated bodies, invalid images, deeply nested JSON,
a decompression-bomb PNG, auth edge cases, a 300-connection flood from a non-allow-listed host,
unicode/RTL/emoji text, and 80 rapid popups (memory returns to baseline). See CI for the automated
checks.

## Development
- `tests/`: Home Assistant tests using HA's own test harness (Linux only) — the action, and the
  blueprint loaded exactly as users load it:
  `pip install pytest-homeassistant-custom-component PyTurboJPEG && python -m pytest tests`.
- CI: hassfest, HACS validation, version consistency, HA tests on the latest Home Assistant,
  ruff, bandit, shellcheck, gitleaks over the full history, and a clean APK build. Runs weekly too,
  to catch breakage from new Home Assistant releases.
- `manifest.json` and the APK share one version; release tags must match it (e.g. `v0.4.0`).
- Secrets live only in their own files. `.gitignore` excludes secret-looking files and
  `.githooks/pre-commit` blocks commits with tokens, private IPs or keys — enable it once per clone:
  `git config core.hooksPath .githooks`.

## License
[MIT](LICENSE)
