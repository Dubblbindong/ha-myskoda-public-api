<img src="https://raw.githubusercontent.com/Dubblbindong/ha-myskoda-public-api/main/custom_components/myskoda_public_api/brand/icon.png" alt="" width="96" align="right">

# MyŠkoda Public API for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Validate](https://github.com/Dubblbindong/ha-myskoda-public-api/actions/workflows/validate.yml/badge.svg)](https://github.com/Dubblbindong/ha-myskoda-public-api/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Connect your Škoda to Home Assistant through the **official
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs)**.
You authenticate with an API key created in the MyŠkoda app. No account
password is stored in Home Assistant, the endpoints and the rate limits are
documented by Škoda.

> **Personal use only.** Škoda provides the Public API for personal end-user
> use. This project is not affiliated with, endorsed by or supported by
> Škoda Auto. Škoda and MyŠkoda are trademarks of Škoda Auto a.s.

Deutsche Anleitung: [README.de.md](README.de.md)

## What you get

Only entities your vehicle actually reports are created.

<table border="1" width="100%">
<tr><th align="left" width="22%">&nbsp;Area&nbsp;</th><th align="left">&nbsp;Entities&nbsp;</th></tr>
<tr><td valign="top">&nbsp;<b>Battery and charging</b>&nbsp;</td><td>&nbsp;state of charge, electric range, charging state, AC/DC, charging power and rate, remaining time, fully charged at, plug connected and locked, charging switch, charging limit slider (50 to 100 %), charge mode, battery care mode, maximum charging current, current charging profile&nbsp;</td></tr>
<tr><td valign="top">&nbsp;<b>Combustion engine</b>&nbsp;</td><td>&nbsp;fuel level, total range, range per engine, AdBlue range, car type&nbsp;</td></tr>
<tr><td valign="top">&nbsp;<b>Status</b>&nbsp;</td><td>&nbsp;locked, doors, windows, lights, trunk, bonnet, sunroof, odometer, doors lock state&nbsp;</td></tr>
<tr><td valign="top">&nbsp;<b>Position</b>&nbsp;</td><td>&nbsp;device tracker with the last parking position and the resolved address, parking state&nbsp;</td></tr>
<tr><td valign="top">&nbsp;<b>Climate</b>&nbsp;</td><td>&nbsp;climate entity with target temperature, air conditioning state, window heating front and rear, auxiliary heating switch and state, active ventilation switch and state&nbsp;</td></tr>
<tr><td valign="top">&nbsp;<b>Vehicle</b>&nbsp;</td><td>&nbsp;render image, license plate&nbsp;</td></tr>
<tr><td valign="top">&nbsp;<b>Diagnostics</b>&nbsp;</td><td>&nbsp;API requests remaining, time the quota resets, API key expiry, data timestamps, refresh button&nbsp;</td></tr>
</table>

**Remote commands:** start and stop charging, set the charging limit, change
the charge mode, start and stop air conditioning, auxiliary heating and
active ventilation.

## Requirements

- A Škoda with Škoda Connect / MyŠkoda and an active MyŠkoda account.
- An API key from the **MyŠkoda app**. Open https://go.skoda.eu/api-keys on
  your phone, create a key and select the vehicle it may access. Keys expire;
  the integration warns you a week ahead and asks for a new key when needed.
- Home Assistant 2025.1 or newer.

## Installation

**HACS**

[![Open this repository in HACS or the Marketplace of your Home Assistant.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Dubblbindong&repository=ha-myskoda-public-api&category=integration)

Or by hand:

1. HACS → Integrations → menu (⋮) → *Custom repositories*
2. Repository `Dubblbindong/ha-myskoda-public-api`, category *Integration*
3. Install *MyŠkoda Public API* and restart Home Assistant.

**Manual**

Copy the folder `custom_components/myskoda_public_api` into the
`custom_components` folder of your configuration and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=myskoda_public_api)

1. Settings → Devices & services → *Add integration* → *MyŠkoda Public API*
2. Enter the API key and the VIN of the vehicle. The key is checked with a
   single API request.

One entry is one vehicle. Add the integration again for a second car; the
same key works if it covers both vehicles.

### Options

<table border="1">
<tr><th align="left">&nbsp;Option&nbsp;</th><th align="left">&nbsp;Default&nbsp;</th><th align="left">&nbsp;Notes&nbsp;</th></tr>
<tr><td>&nbsp;Polling interval&nbsp;</td><td align="center">&nbsp;900 s&nbsp;</td><td>&nbsp;15 minutes. Minimum 240 s. See <i>Rate limits</i>.&nbsp;</td></tr>
<tr><td>&nbsp;S-PIN&nbsp;</td><td align="center">&nbsp;–&nbsp;</td><td>&nbsp;Only needed to start the auxiliary heater. Stored in the config entry.&nbsp;</td></tr>
</table>

## Rate limits

The API allows about **20 requests per hour and vehicle**, and everything
counts against it:

- every poll is one request,
- every remote command is **two requests**: the command itself and a refresh
  15 seconds later. If the vehicle has not reported by then, a second
  refresh follows after 60 seconds, so **three**,
- every press of the *Refresh* button is one request.

The default polling interval is **15 minutes**: 4 requests per hour, which
leaves 16 for commands. You can shorten it in the options, down to 240
seconds, but mind the budget:

<table border="1">
<tr><th align="left">&nbsp;Interval&nbsp;</th><th align="left">&nbsp;Polls per hour&nbsp;</th><th align="left">&nbsp;Left for commands&nbsp;</th><th align="left">&nbsp;Means&nbsp;</th></tr>
<tr><td>&nbsp;900 s (default)&nbsp;</td><td align="center">4</td><td align="center">16</td><td>&nbsp;5 to 8 commands per hour&nbsp;</td></tr>
<tr><td>&nbsp;600 s&nbsp;</td><td align="center">6</td><td align="center">14</td><td>&nbsp;4 to 7 commands per hour&nbsp;</td></tr>
<tr><td>&nbsp;300 s&nbsp;</td><td align="center">12</td><td align="center">8</td><td>&nbsp;2 to 4 commands per hour&nbsp;</td></tr>
<tr><td>&nbsp;240 s (minimum)&nbsp;</td><td align="center">15</td><td align="center">5</td><td>&nbsp;Data every 4 minutes, 1 to 2 commands; each request spent on a command removes 4 minutes of data at the end of the hour&nbsp;</td></tr>
</table>

When the quota runs low, the integration does not fail: it reads the
rate-limit headers, stops polling when two requests are left and waits for
the hour to reset, and after a 429 response it waits as long as the API
asks. The remaining requests and the reset time are diagnostic sensors.
Avoid automations that poll or toggle something every few minutes.

## Actions

### `myskoda_public_api.start_air_conditioning`

<table border="1">
<tr><th align="left">&nbsp;Field&nbsp;</th><th align="left">&nbsp;Required&nbsp;</th><th align="left">&nbsp;Description&nbsp;</th></tr>
<tr><td>&nbsp;<code>device_id</code>&nbsp;</td><td align="center">yes</td><td>&nbsp;The vehicle&nbsp;</td></tr>
<tr><td>&nbsp;<code>temperature</code>&nbsp;</td><td align="center">no</td><td>&nbsp;Target cabin temperature in °C, 16 to 30&nbsp;</td></tr>
<tr><td>&nbsp;<code>without_external_power</code>&nbsp;</td><td align="center">no</td><td>&nbsp;Allow climatisation while unplugged&nbsp;</td></tr>
</table>

### `myskoda_public_api.start_auxiliary_heating`

<table border="1">
<tr><th align="left">&nbsp;Field&nbsp;</th><th align="left">&nbsp;Required&nbsp;</th><th align="left">&nbsp;Description&nbsp;</th></tr>
<tr><td>&nbsp;<code>device_id</code>&nbsp;</td><td align="center">yes</td><td>&nbsp;The vehicle&nbsp;</td></tr>
<tr><td>&nbsp;<code>duration</code>&nbsp;</td><td align="center">no</td><td>&nbsp;Run time in minutes&nbsp;</td></tr>
<tr><td>&nbsp;<code>start_mode</code>&nbsp;</td><td align="center">no</td><td>&nbsp;<code>heating</code> or <code>ventilation</code>&nbsp;</td></tr>
<tr><td>&nbsp;<code>temperature</code>&nbsp;</td><td align="center">no</td><td>&nbsp;Target cabin temperature in °C&nbsp;</td></tr>
<tr><td>&nbsp;<code>spin</code>&nbsp;</td><td align="center">no</td><td>&nbsp;S-PIN, falls back to the one stored in the options&nbsp;</td></tr>
</table>

The climate entity covers the everyday case: setting a temperature stores it
and applies it with the next *turn on*; while the air conditioning runs it is
restarted with the new target.

## Good to know

- **Commands are asynchronous.** The API accepts a command and the vehicle
  executes it afterwards. Switches show the expected state right away; the
  integration re-fetches the state 15 seconds later and, only if the vehicle
  has not reported yet, once more after 60 seconds.
- **Partial data is normal.** Parts the API could not fetch are missing from
  a response; the affected entities become *unavailable* until the next
  successful poll.
- **Position only while parked.** While driving the tracker has no
  coordinates.
- **No lock, unlock, flash or honk.** The API does not offer these; the lock
  state is read-only.
- **Charging profiles** are read; the current one is a sensor. Editing them
  is not implemented.

## Troubleshooting

- *The API key was rejected:* the key expired, was deleted in the app or does
  not cover this VIN. Create or update it in the MyŠkoda app.
- *Rate limit exhausted:* wait for the reset (see the diagnostic sensor) and
  raise the polling interval.
- Attach the diagnostics download from the device page when reporting a
  problem; key, VIN, license plate, position and address are redacted.
- Debug logging:

```yaml
logger:
  logs:
    custom_components.myskoda_public_api: debug
```

## Development

The API client in `api.py` has no Home Assistant dependencies and is tested
against a local fake server, so no real quota is spent. CI runs hassfest, the
HACS action, pyflakes, a translation check and that client test on every
push. See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and the policy
on AI tools, [AGENTS.md](AGENTS.md) for code-base notes and
[SECURITY.md](SECURITY.md) for reporting vulnerabilities privately.

## License

[MIT](LICENSE)
