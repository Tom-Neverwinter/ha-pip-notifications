# Camera integrations: what to pick

The [blueprint](blueprints/camera_popup.yaml) needs two things: a **trigger** (a binary sensor that
turns *on*, or an *event* entity) and a **camera** entity. Entity names depend on what you called
your devices, so pick them from the dropdowns — the hints below tell you what to look for.

| Integration | Trigger to pick | Camera to pick | Good to know |
|---|---|---|---|
| **Blink** | the camera's *Motion* binary sensor | the Blink camera | Cloud and polled: motion can arrive a minute or more late, and the image is Blink's last motion thumbnail. Don't add `blink.trigger_camera` — it wakes battery cameras again. Use a cooldown. |
| **Frigate** (integration) | a *Person occupancy* (or *Motion*) binary sensor for that camera | the Frigate camera | Local and fast. Object-type sensors (person, car, …) avoid popups for leaves and shadows. |
| **Google Nest** | the doorbell's *Chime* event, or the camera's *Motion* / *Person* event | the Nest camera | Newer battery Nest cameras/doorbells are WebRTC-only and **don't give Home Assistant a snapshot** — you'll get a text-only popup (title, location, time). Wired/older models with RTSP give images. |
| **Ring** | the doorbell's *Ding* event (or motion) | the Ring camera | Cloud. The image is usually the last recording's thumbnail and may need a Ring subscription. |
| **Reolink** | *Visitor* (doorbell press) or *Person* binary sensor | the camera's *Fluent* or *Clear* stream camera | Local and fast. |
| **UniFi Protect** | *Doorbell* or *Person detected* binary sensor | the camera's high-resolution channel | Local and fast. |
| **Blue Iris** | a motion/alert binary sensor (Blue Iris HACS integration, or an MQTT binary sensor from Blue Iris alerts) | a Blue Iris camera, or a *Generic Camera* pointed at Blue Iris' snapshot URL | Give Home Assistant its own Blue Iris user; keep credentials in `secrets.yaml`. |
| **Generic camera / RTSP / ONVIF** | any motion, contact or doorbell-button sensor | the camera | Any binary sensor works — even a Zigbee doorbell button or a gate contact. |

## No snapshot?
If a camera can't give a snapshot (offline, WebRTC-only, cloud hiccup), the popup is still shown
**without the image**, and the action's response has `has_image: false`. The AI step is skipped in
that case (nothing to look at).

## °C / °F and other units
Nothing to configure here: Home Assistant converts sensors to the unit system you chose under
*Settings → System → General*. The blueprint's *Extra sensor* shows the value **with its own unit**
(e.g. `Porch · 72 °F` or `Porch · 22.3 °C`). In your own automations, do the same:
```yaml
location: "Porch · {{ states('sensor.outdoor_temperature') }} {{ state_attr('sensor.outdoor_temperature', 'unit_of_measurement') }}"
```

## Time format
The popup time uses `time_format` from `config.yaml` (Python `strftime`). Default is US style
`3:05:51 PM · Sat Oct 17`. Examples:

| You want | `time_format` |
|---|---|
| 24-hour, day before month | `"%H:%M:%S · %a %d %b"` → `15:05:51 · Sat 17 Oct` |
| 24-hour, no seconds | `"%H:%M · %d.%m."` → `15:05 · 17.10.` |
| ISO | `"%Y-%m-%d %H:%M:%S"` |

Weekday/month names are English (Home Assistant's server locale).

## Without the blueprint
```yaml
automation:
  - alias: Front door popup
    mode: single
    triggers:
      - trigger: state
        entity_id: binary_sensor.front_door_person
        from: "off"
        to: "on"
    actions:
      - action: pip_notifications.show
        continue_on_error: true
        data:
          camera: camera.front_door
          location: Porch
      - delay: 120   # cooldown
```
