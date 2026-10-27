"""Exercise api.py against a local fake of the MyŠkoda Public API.

No request leaves the machine, so the real per-VIN quota is never touched.
Needs only aiohttp:  python tests/test_api_client.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys

from aiohttp import ClientSession, web

REPO = pathlib.Path(__file__).resolve().parents[1]
API_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else str(REPO / "custom_components" / "myskoda_public_api" / "api.py")
)

spec = importlib.util.spec_from_file_location("skoda_api", API_PATH)
api = importlib.util.module_from_spec(spec)
sys.modules["skoda_api"] = api
spec.loader.exec_module(api)

PROBLEMS = "https://public.api.connect.skoda-auto.cz/problems/"
RATE_LIMIT_HEADERS = {
    "RateLimit-Limit": "20",
    "RateLimit-Remaining": "17",
    "RateLimit-Reset": "1800",
    "X-API-Key-Expires-At": "2027-03-01T10:00:00Z",
}
VIN = "TMBJB9NY5RF999999"
calls: list[tuple] = []


def problem(status: int, ptype: str, detail: str, **headers: str) -> web.Response:
    return web.json_response(
        {"type": PROBLEMS + ptype, "title": "x", "status": status, "detail": detail},
        status=status,
        content_type="application/problem+json",
        headers=headers,
    )


async def get_vehicle(req: web.Request) -> web.Response:
    calls.append(("GET", req.path, dict(req.query)))
    if req.headers.get("X-API-Key") != "good":
        return problem(401, "api-key-expired", "expired")
    if req.match_info["vin"] == "RATELIMITEDVIN000":
        return problem(
            429, "rate-limit-exceeded", "slow down", **{"Retry-After": "30", **RATE_LIMIT_HEADERS}
        )
    if req.match_info["vin"] == "UNKNOWNVIN0000000":
        return problem(404, "about:blank", "nope")
    return web.json_response(
        {
            "vehicle": {
                "vin": req.match_info["vin"],
                "name": "Test Enyaq",
                "charging": {
                    "isVehicleInSavedLocation": True,
                    "status": {"state": "CHARGING", "battery": {"stateOfChargeInPercent": 66}},
                },
                "operations": [{"name": "startCharging"}],
            },
            "errors": [{"type": "PARKING_POSITION_UNAVAILABLE", "description": "x"}],
        },
        headers=RATE_LIMIT_HEADERS,
    )


async def accepted(req: web.Request) -> web.Response:
    calls.append((req.method, req.path, await req.text()))
    return web.Response(status=202, headers=RATE_LIMIT_HEADERS)


async def busy(req: web.Request) -> web.Response:
    calls.append((req.method, req.path, ""))
    return problem(429, "vehicle-not-accepting-requests", "busy", **{"Retry-After": "10"})


async def unsupported(req: web.Request) -> web.Response:
    calls.append((req.method, req.path, await req.text()))
    return problem(422, "operation-not-supported", "no aux")


app = web.Application()
app.router.add_get("/api/v1/vehicles/{vin}", get_vehicle)
app.router.add_post("/api/v1/vehicles/{vin}/charging/start", accepted)
app.router.add_post("/api/v1/vehicles/{vin}/charging/stop", busy)
app.router.add_put("/api/v1/vehicles/{vin}/charging/limit", accepted)
app.router.add_post("/api/v1/vehicles/{vin}/air-conditioning/start", accepted)
app.router.add_post("/api/v1/vehicles/{vin}/auxiliary-heating/start", unsupported)


async def main() -> None:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    base = f"http://127.0.0.1:{port}"
    ok = 0

    async with ClientSession() as session:
        client = api.MySkodaPublicApi(session, "good", base_url=base)

        data = await client.async_get_vehicle(VIN)
        assert data.vin == VIN and data.vehicle["name"] == "Test Enyaq"
        assert data.error_types == {"PARKING_POSITION_UNAVAILABLE"}
        ok += 1
        assert data.rate_limit.remaining == 17 and data.rate_limit.limit == 20
        assert data.rate_limit.reset_seconds == 1800
        ok += 1
        assert data.api_key_expires_at.isoformat() == "2027-03-01T10:00:00+00:00"
        ok += 1

        await client.async_get_vehicle(VIN, include=("info", "status"))
        assert calls[-1][2] == {"include": "info,status"}
        ok += 1

        await client.async_start_charging(VIN)
        assert calls[-1][:2] == ("POST", f"/api/v1/vehicles/{VIN}/charging/start")
        ok += 1

        await client.async_set_charging_limit(VIN, 80)
        assert json.loads(calls[-1][2]) == {"targetStateOfChargeInPercent": 80}
        ok += 1

        await client.async_start_air_conditioning(
            VIN, target_temperature_celsius=21.5, without_external_power=True
        )
        assert json.loads(calls[-1][2]) == {
            "targetTemperature": {"value": 21.5, "unit": "CELSIUS"},
            "airConditioningWithoutExternalPower": True,
        }
        ok += 1

        try:
            await client.async_stop_charging(VIN)
            raise SystemExit("expected vehicle-busy error")
        except api.MySkodaVehicleBusyError as err:
            assert err.retry_after == 10 and err.status == 429
            assert err.problem_type == "vehicle-not-accepting-requests"
            ok += 1

        try:
            await client.async_start_auxiliary_heating(
                VIN, spin="1234", duration_seconds=600, start_mode="HEATING"
            )
            raise SystemExit("expected 422")
        except api.MySkodaOperationError as err:
            assert err.detail == "no aux" and json.loads(calls[-1][2])["spin"] == "1234"
            ok += 1

        try:
            await client.async_get_vehicle("RATELIMITEDVIN000")
            raise SystemExit("expected 429")
        except api.MySkodaRateLimitError as err:
            assert err.retry_after == 30 and client.last_rate_limit.remaining == 17
            ok += 1

        try:
            await client.async_get_vehicle("UNKNOWNVIN0000000")
            raise SystemExit("expected 404")
        except api.MySkodaNotFoundError:
            ok += 1

        client.set_api_key("bad")
        try:
            await client.async_get_vehicle(VIN)
            raise SystemExit("expected 401")
        except api.MySkodaAuthError as err:
            assert err.problem_type == "api-key-expired" and "expired" in str(err)
            ok += 1

        unreachable = api.MySkodaPublicApi(
            session, "good", base_url="http://127.0.0.1:1", request_timeout=2
        )
        try:
            await unreachable.async_get_vehicle(VIN)
            raise SystemExit("expected connection error")
        except api.MySkodaConnectionError:
            ok += 1

    await runner.cleanup()
    print(f"api client: {ok} checks passed")


asyncio.run(main())
