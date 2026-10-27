# Security Policy

## Supported versions

Only the latest release on the `main` branch receives fixes.

## Reporting a vulnerability

Please report vulnerabilities **privately** through GitHub's advisory workflow:

[Report a vulnerability](https://github.com/Dubblbindong/ha-myskoda-public-api/security/advisories/new)

Do not open a public issue for security problems. Please include a description,
the affected version and steps to reproduce or a proof of concept.

This is a hobby project maintained by one person in their spare time. Expect a
first reply within about 14 days.

## What this integration handles

* The MyŠkoda **API key** and, optionally, the **S-PIN** are stored in Home
  Assistant's config entry storage (`.storage/core.config_entries`), the same
  place other integrations keep their credentials. Protect your Home Assistant
  instance and its backups accordingly.
* Vehicle **position, address, license plate and VIN** end up as entity states
  and attributes in Home Assistant's recorder database.
* **Diagnostics** downloads redact the key, S-PIN, VIN, license plate, position
  and address. Still review a diagnostics file before sharing it.
* The integration talks only to `https://public.api.connect.skoda-auto.cz`
  over HTTPS and sends the key exclusively in the `X-API-Key` header. It never
  logs the key or the S-PIN.

## If your API key leaks

Revoke or replace the key in the MyŠkoda app (<https://go.skoda.eu/api-keys>)
and re-authenticate the integration. Keys are bound to the vehicles you select
and expire automatically.

## Disclosure

Once a fix is released, a security advisory is published, with credit to the
reporter if wanted.
