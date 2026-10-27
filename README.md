# MyŠkoda Public API for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Validate](https://github.com/Dubblbindong/ha-myskoda-public-api/actions/workflows/validate.yml/badge.svg)](https://github.com/Dubblbindong/ha-myskoda-public-api/actions/workflows/validate.yml)

A Home Assistant custom integration for Škoda vehicles built on the **official
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs)**.

Unlike integrations that reverse-engineer the MyŠkoda app, this one uses the API
Škoda publishes for exactly this purpose: an API key created in the MyŠkoda app,
a documented contract and documented rate limits. No account password is stored
in Home Assistant.

> **Personal use only.** Škoda provides the Public API for personal end-user use.
> This integration is not affiliated with, endorsed by or supported by Škoda Auto.
> Škoda, MyŠkoda and the Škoda logo are trademarks of Škoda Auto a.s.

*Deutsche Kurzfassung weiter unten.*

## Features

Everything the vehicle reports through the API becomes an entity. Entities that
the vehicle does not support are simply not created.

| Area | Entities |
| --- | --- |
| Battery and charging | battery level, electric range, charging state, charge type (AC/DC), charging power, charging rate, remaining time, fully charged at, plug connected, plug locked, charging switch, charging limit (50–100 %), charge mode, battery care mode, maximum charging current, current charging profile |
| Combustion engine | fuel level, total range, range per engine, AdBlue range, car type |
| Status | locked, doors, windows, lights, trunk, bonnet, sunroof, odometer, doors lock state |
| Position | device tracker with the last parking position and resolved address, parking state |
| Climate | climate entity (start/stop with target temperature), air conditioning state, target temperature, window heating front/rear, auxiliary heating switch and state, active ventilation switch and state |
| Vehicle | render image of the vehicle, license plate |
| Diagnostics | API requests remaining in the current window, time the quota resets, API key expiry, timestamps of the last data captured by the vehicle, refresh button |

Remote commands: start/stop charging, set charging limit, change charge mode,
start/stop air conditioning, start/stop auxiliary heating, start/stop active
ventilation.

## Requirements

* A Škoda with Škoda Connect / MyŠkoda and an active MyŠkoda account.
* An API key created in the **MyŠkoda app**: open <https://go.skoda.eu/api-keys>
  on the phone (or scan the QR code in the [API documentation](https://public.api.connect.skoda-auto.cz/docs)),
  create a key and select the vehicle(s) it may access. Keys expire; the
  integration warns you a week in advance and asks for a new key when needed.
* Home Assistant 2025.1 or newer.

## Installation

### HACS (recommended)

1. In HACS open **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/Dubblbindong/ha-myskoda-public-api` with category
   **Integration**.
3. Install **MyŠkoda Public API** and restart Home Assistant.

### Manual

Copy `custom_components/myskoda_public_api` into the `custom_components`
folder of your Home Assistant configuration and restart Home Assistant.

## Configuration

1. **Settings → Devices & services → Add integration → MyŠkoda Public API**.
2. Enter the API key and the VIN of the vehicle. The key is checked with one
   API request. One config entry represents one vehicle; add the integration
   again for a second car (the same key can be used if it covers both vehicles).

### Options

| Option | Default | Notes |
| --- | --- | --- |
| Polling interval | 300 s | Minimum 240 s. See *Rate limits*. |
| S-PIN | – | Only needed to start the auxiliary heater. Stored in the Home Assistant config entry. |

## Rate limits

The API allows about **20 requests per hour and vehicle** (the `RateLimit-*`
response headers are authoritative). Every poll, every remote command and the
one or two refreshes the integration performs after a command count against
that quota.

The integration

* polls every 5 minutes by default (12 requests per hour),
* reads the rate-limit headers and slows down automatically when only two
  requests are left in the current window,
* backs off according to `Retry-After` after a `429` response,
* exposes the remaining requests and the time the quota resets as diagnostic
  sensors.

Pressing the *Refresh* button or calling a remote command consumes quota, so
avoid tight automations that poll or toggle things every minute.

## Actions

### `myskoda_public_api.start_air_conditioning`

| Field | Required | Description |
| --- | --- | --- |
| `device_id` | yes | The vehicle |
| `temperature` | no | Target cabin temperature in °C (16–30) |
| `without_external_power` | no | Allow climatisation while unplugged |

### `myskoda_public_api.start_auxiliary_heating`

| Field | Required | Description |
| --- | --- | --- |
| `device_id` | yes | The vehicle |
| `duration` | no | Run time in minutes |
| `start_mode` | no | `heating` or `ventilation` |
| `temperature` | no | Target cabin temperature in °C |
| `spin` | no | S-PIN; falls back to the S-PIN stored in the options |

The climate entity covers the common case: `climate.set_temperature` stores the
target and applies it with the next `climate.turn_on`; while the air
conditioning is running it is restarted with the new target.

## Behaviour worth knowing

* **Commands are asynchronous.** The API acknowledges a command with `202
  Accepted`; the vehicle executes it afterwards. Switches show the expected
  state immediately; the integration re-fetches the state 15 seconds after a
  command and, only if the vehicle has not reported fresh data by then, once
  more after 60 seconds. Sensors therefore follow a command with a short delay.
* **Partial data is normal.** The API omits parts that could not be retrieved at
  that moment; the affected entities become *unavailable* until the next
  successful poll. Fields the vehicle does not report (for example the derived
  charging state while the cable is plugged in but idle) show *unknown*.
* **Position only while parked.** GPS coordinates are reported when the
  vehicle is parked. While driving the tracker has no coordinates.
* **The API cannot lock or unlock the car**, flash lights or honk. The lock
  state is read-only.
* **Charging profiles** (saved charging locations) are read; the current
  profile is exposed as a sensor. Editing profiles is not implemented yet.

## Troubleshooting

* *The API key was rejected* – the key expired, was deleted in the app or does
  not cover this VIN. Create or update the key in the MyŠkoda app.
* *Rate limit exhausted* – wait for the window to reset (the diagnostic sensor
  shows when). Raise the polling interval in the options.
* Download diagnostics from the device page when reporting a problem; VIN,
  license plate, position and keys are redacted.
* Enable debug logging:

  ```yaml
  logger:
    logs:
      custom_components.myskoda_public_api: debug
  ```

## Development

```text
custom_components/myskoda_public_api/
├── api.py            # HA-independent aiohttp client, RFC 9457 problem handling
├── coordinator.py    # polling, rate-limit backoff, key-expiry repair issue, commands
├── config_flow.py    # user / reauth / reconfigure / options flows
├── entity.py         # base entity, availability per response part, optimistic state
├── sensor.py, binary_sensor.py, switch.py, climate.py, number.py,
│   select.py, button.py, image.py, device_tracker.py
├── services.py       # actions
└── translations/     # en, de
```

The GitHub workflow runs [hassfest](https://github.com/home-assistant/actions),
the [HACS action](https://github.com/hacs/action), pyflakes,
`scripts/check_translations.py` (translation keys, enum states, services and
icons) and `tests/test_api_client.py` (the API client against a local fake
server, so no real quota is used) on every push. Both scripts run locally with
plain Python plus `aiohttp` and `pyyaml`.

## Deutsch – Kurzfassung

Diese Integration bindet Škoda-Fahrzeuge über die **offizielle MyŠkoda Public
API** in Home Assistant ein. Du brauchst einen API-Schlüssel aus der
MyŠkoda-App (<https://go.skoda.eu/api-keys>) und die FIN des Fahrzeugs; ein
Passwort wird nicht gespeichert.

* **Installation:** HACS → Integrationen → benutzerdefiniertes Repository
  `https://github.com/Dubblbindong/ha-myskoda-public-api` (Kategorie
  Integration) → installieren → Home Assistant neu starten.
* **Einrichtung:** Einstellungen → Geräte & Dienste → Integration hinzufügen →
  *MyŠkoda Public API* → API-Schlüssel und FIN eingeben.
* **Rate-Limit:** ca. 20 Anfragen pro Stunde und Fahrzeug. Standardmäßig wird
  alle 5 Minuten abgefragt; Befehle und der *Aktualisieren*-Button zählen mit.
  Die Integration liest die Limit-Header mit und bremst sich selbst.
* **Standheizung:** Zum Starten wird die S-PIN benötigt (in den Optionen
  hinterlegen oder der Aktion übergeben).
* **Nur für den persönlichen Gebrauch** gemäß den Bedingungen von Škoda; keine
  Verbindung zu Škoda Auto.

## License

[MIT](LICENSE)
