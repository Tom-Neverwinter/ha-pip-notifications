# HA PiP Notifications

Camera snapshot popups on Android TV / Google TV from Home Assistant, with an optional AI analysis line.
Two small pieces, no third-party libraries:

| Piece | Where | What |
|---|---|---|
| TV receiver | `android/` (Java, ~250 lines) | Corner overlay: image, camera name · location, timestamp, optional AI line |
| HA integration | `ha/custom_components/pip_notifications/` | Action `pip_notifications.show`: grabs the snapshot, optional AI Task analysis, pushes to TVs |

## TV receiver security
- Listens on **7979**; answers only allow-listed IPs (HA), then requires `Authorization: Bearer <token>`.
  Missing config = refuses everything.
- Popup is capped at a quarter of the screen (½ width × ½ height), top-right, 5 s by default.
- Image arrives inline (base64): the TV **never fetches URLs** and makes **no outbound connections**.
- **Stores nothing** except its token + allowlist. No launcher icon, no UI.
- Config receiver is guarded by `android.permission.DUMP` → only adb/system can change it.
- Permissions: INTERNET, overlay, foreground service, boot-completed.

## Build + install
```bash
bash android/build.sh                         # -> android/build/ha-pip-notifications.apk (needs SDK build-tools 35 + platform 35)
adb -s <tv> install -r android/build/ha-pip-notifications.apk
adb -s <tv> shell appops set io.github.tomneverwinter.hapip SYSTEM_ALERT_WINDOW allow
adb -s <tv> shell am broadcast -f 32 -n io.github.tomneverwinter.hapip/.ConfigReceiver \
    --es token "<token>" --es allow <HA IP>
```
Signed with your Android debug key (`~/.android/debug.keystore`); updates must use the same key.

## HA side
1. Copy `ha/custom_components/pip_notifications` to `/config/custom_components/`.
2. Copy `ha/pip_notifications/config.example.yaml` → `/config/pip_notifications/config.yaml` (TV names + IPs) and
   `ha/pip_notifications/secrets.example.yaml` → `/config/pip_notifications/secrets.yaml` (the token).
   HA resolves `!secret` from that folder's own `secrets.yaml` first.
3. `configuration.yaml`: `pip_notifications: !include pip_notifications/config.yaml`, then restart HA.

```yaml
action: pip_notifications.show
data:
  camera: camera.front_door
  name: Front door
  location: Porch
  # optional AI: popup shows immediately, then updates with the analysis
  ai_task_entity: ai_task.<your provider>
response_variable: shown   # -> {camera, location, timestamp, analysis, delivered, ...}
```
- **AI in:** pass `analysis:` text from any system, or `ai_task_entity` to use HA's AI Task.
- **AI out:** the action's response and the `pip_notifications_shown` event carry the metadata + analysis
  for other automations/systems. A failed AI call never blocks the popup.

## Threat model / known limits
- **Plain HTTP on the LAN.** The token is not encrypted in transit; someone who can sniff your LAN
  can read it. They would also have to spoof HA's IP to use it (IP allowlist). Keep TVs and HA on a
  trusted network/VLAN. Worst case is a fake popup — the app can't do anything else.
- **Single-threaded listener** with a 5 s socket timeout: an allow-listed host could slow it down,
  a non-allow-listed host is dropped before anything is read.
- Hardening tested on a real TV: bad/negative/non-numeric/overflowing lengths, 16 KB header lines,
  101 headers, garbage bytes, slowloris, truncated bodies, invalid base64, wrong JSON types, 8 MiB
  deeply-nested JSON (stack overflow → 400), a 500×2,000,000 px PNG decompression bomb (subsampled),
  auth edge cases (case, prefix/suffix, duplicates, Basic), 300-connection flood from a
  non-allow-listed host, 400 random fuzz requests, unicode/RTL/emoji text, and 80 rapid popups
  (memory returns to baseline).
- Token is excluded from cloud backup **and** device-to-device transfer (`data_extraction_rules.xml`).
- Not debuggable; config receiver only accepts action-less broadcasts from DUMP holders (adb/system).

## Tests
- `ha/tests/`: HA integration tests using HA's own harness (Linux only — run in CI):
  `cd ha && python -m pytest tests` with `pytest-homeassistant-custom-component` installed.
- CI (`.github/workflows/ci.yml`): HA tests on the latest HA, ruff, bandit, shellcheck, gitleaks over
  full history, and a clean APK build.

## Secrets
Secrets only ever live in their own files, none of which are in this repo:
`/config/pip_notifications/secrets.yaml` on HA, and your own local token file. `.gitignore` excludes
secret-looking files and build output, and `.githooks/pre-commit` refuses commits containing tokens,
private IPs or key files. Enable it once per clone: `git config core.hooksPath .githooks`.
