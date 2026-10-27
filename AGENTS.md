# AGENTS.md

Guidance for coding agents (and humans) working in this repository. Read it
before changing anything.

## What this is

* Home Assistant custom integration `myskoda_public_api`, distributed via HACS,
  built on the official MyŠkoda Public API:
  <https://public.api.connect.skoda-auto.cz/docs> (OpenAPI at `/v3/api-docs`).
* One config entry is one vehicle (VIN) authenticated with an API key created in
  the MyŠkoda app. No account password is involved.
* Not affiliated with Škoda. The API is licensed for personal use only.

## Repository layout

* `custom_components/myskoda_public_api/` – the integration
  * `api.py` – aiohttp client, **no Home Assistant imports** (keep it that way)
  * `coordinator.py` – polling, rate-limit handling, command execution
  * `entity.py` – shared base entity
  * platform modules: `sensor.py`, `binary_sensor.py`, `switch.py`,
    `climate.py`, `number.py`, `select.py`, `button.py`, `image.py`,
    `device_tracker.py`
  * `services.py` + `services.yaml` – actions
  * `strings.json`, `translations/en.json`, `translations/de.json`, `icons.json`
  * `brand/` – icon served locally by Home Assistant 2026.3+
* `tests/test_api_client.py` – client test against a local fake API server
* `scripts/check_translations.py` – consistency of translations, enum states,
  services and icons
* `.github/workflows/validate.yml` – hassfest, HACS action, pyflakes and the
  two scripts above

## Hard rules

* **Never call the real API** from tests, scripts, examples or ad-hoc checks.
  The quota is about 20 requests per hour and VIN and it is shared with the
  owner's running Home Assistant. Use the fake server in
  `tests/test_api_client.py`.
* **Never log or print** API keys, S-PINs, VINs, positions, addresses or
  license plates. `diagnostics.py` redacts them; extend `TO_REDACT` when adding
  personal fields.
* `strings.json` and `translations/en.json` must be identical (copy after
  editing); `translations/de.json` must carry the same keys and placeholders.
* `manifest.json` keys: `domain`, `name`, then alphabetical (hassfest).
* Entity `key`s and unique IDs (`{vin}_{key}`) are stable once released.
* Do not add `"categories"` to `manifest.json` until the hassfest GitHub action
  is based on Home Assistant 2026.11; today it rejects the key, while the HACS
  action only warns when it is missing. The value to use then is
  `vehicles_transport.cars_evs`.
* The minimum Home Assistant version is set in `hacs.json`. Do not use newer
  core APIs without raising it.
* README tables are written as HTML (`<table border="1">`, `&nbsp;` at the
  cell edges, `<code>`/`<b>` instead of markdown inside cells) on purpose:
  HACS 2.0.5 renders the README with a Home Assistant frontend from January
  2025 that has no table CSS and strips `style`, `cellpadding` and `class`
  attributes, so plain markdown tables show up there without borders or
  spacing. GitHub styles both kinds the same. Keep tables free of blank lines
  and avoid wide `<pre>` blocks and long inline code, which cannot wrap in the
  HACS dialog.
* Commands, issues, pull requests and comments are never sent autonomously;
  see [CONTRIBUTING.md](CONTRIBUTING.md).

## Commands

```bash
python -m py_compile custom_components/myskoda_public_api/*.py
python -m pyflakes custom_components/myskoda_public_api
python scripts/check_translations.py      # needs pyyaml
python tests/test_api_client.py           # needs aiohttp
```

CI runs the same plus hassfest and the HACS action. There is no pytest suite
and no Home Assistant test harness in this repository: do not claim that
Home Assistant-level tests passed. Runtime verification happens in the owner's
Home Assistant, which they restart themselves.

## Architecture notes

* `api.py` maps RFC 9457 `application/problem+json` responses to typed
  exceptions (`MySkodaAuthError`, `MySkodaNotFoundError`,
  `MySkodaRateLimitError`, `MySkodaVehicleBusyError`, `MySkodaOperationError`,
  `MySkodaServerError`, `MySkodaConnectionError`) and records the
  `RateLimit-*` and `X-API-Key-Expires-At` headers of every response, errors
  included.
* `coordinator.py` is a `DataUpdateCoordinator` per vehicle. It polls every
  `scan_interval` (default 900 s, minimum 240 s; a command costs 2 to 3
  requests of the 20 per hour), stretches the interval when
  two or fewer requests remain, backs off after a 429, raises
  `ConfigEntryAuthFailed` on key problems and opens a repair issue a week
  before the key expires. `async_execute_command()` wraps remote commands,
  translates errors into `HomeAssistantError` with translation keys and
  re-fetches the state 15 s later, and once more after 60 s only when the
  affected section's `carCapturedTimestamp` is still older than the command.
* `entity.py`: `has_entity_name`, one device per VIN, availability bound to the
  presence of the entity's response section, `_set_optimistic()` for the
  moment between a command and the next refresh.
* Platforms create entities only for sections present in the first response
  and for operations listed in `vehicle.operations`.
* Enum sensors declare `options` and matching state translations; unknown API
  values are tolerated by extending `options` dynamically.
* The climate entity only sends a target temperature when starting the air
  conditioning (the API has no separate setter); a target set while off is
  stored locally and used on the next start.

## Style

* Python 3.13+, `from __future__ import annotations`, PEP 695 `type` aliases,
  frozen `kw_only` entity descriptions, translation keys for every name.
* Keep module and function docstrings. Prefer specific exceptions. Keep
  functions small and platform modules declarative.
* Commit messages: short imperative subject, body explains why.
