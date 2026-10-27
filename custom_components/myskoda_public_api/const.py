"""Constants for the MyŠkoda Public API integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "myskoda_public_api"
MANUFACTURER: Final = "Škoda"

API_KEY_MANAGEMENT_URL: Final = "https://go.skoda.eu/api-keys"
API_DOCS_URL: Final = "https://public.api.connect.skoda-auto.cz/docs"

CONF_VIN: Final = "vin"
CONF_SPIN: Final = "spin"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_REMOVE_SPIN: Final = "remove_spin"

# The API is rate-limited per VIN (20 requests per hour at the time of writing; the
# RateLimit-* response headers are authoritative). 900 s polling = 4 requests/hour,
# which leaves 16 for remote commands: a command costs two requests (the command
# and the refresh 15 s later), three when a second refresh after 60 s is needed.
# At the minimum of 240 s polling alone uses 15 of the 20 requests.
DEFAULT_SCAN_INTERVAL: Final = 900
MIN_SCAN_INTERVAL: Final = 240
MAX_SCAN_INTERVAL: Final = 3600
# Seconds after a remote command at which the state is re-fetched. The second
# refresh only happens when the vehicle has not reported fresh data by the first.
POST_COMMAND_REFRESH_DELAYS: Final = (15, 60)
# Requests kept in reserve for remote commands before polling slows down.
RATE_LIMIT_RESERVE: Final = 2
API_KEY_EXPIRY_WARNING_DAYS: Final = 7

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Remote operations as reported in ``vehicle.operations``.
OP_START_CHARGING: Final = "startCharging"
OP_STOP_CHARGING: Final = "stopCharging"
OP_SET_CHARGING_LIMIT: Final = "setChargingLimit"
OP_SET_CHARGE_MODE: Final = "setChargeMode"
OP_UPDATE_CHARGING_PROFILE: Final = "updateChargingProfile"
OP_START_AIR_CONDITIONING: Final = "startAirConditioning"
OP_STOP_AIR_CONDITIONING: Final = "stopAirConditioning"
OP_START_AUXILIARY_HEATING: Final = "startAuxiliaryHeating"
OP_STOP_AUXILIARY_HEATING: Final = "stopAuxiliaryHeating"
OP_START_ACTIVE_VENTILATION: Final = "startActiveVentilation"
OP_STOP_ACTIVE_VENTILATION: Final = "stopActiveVentilation"

# Top-level parts of the vehicle response.
SECTION_STATUS: Final = "status"
SECTION_FUEL_STATUS: Final = "fuelStatus"
SECTION_ODOMETER: Final = "odometer"
SECTION_PARKING_POSITION: Final = "parkingPosition"
SECTION_AIR_CONDITIONING: Final = "airConditioning"
SECTION_AUXILIARY_HEATING: Final = "auxiliaryHeating"
SECTION_ACTIVE_VENTILATION: Final = "activeVentilation"
SECTION_CHARGING: Final = "charging"
SECTION_CHARGING_PROFILES: Final = "chargingProfiles"

CHARGE_MODES: Final = [
    "MANUAL",
    "TIMER",
    "TIMER_CHARGING_WITH_CLIMATISATION",
    "PREFERRED_CHARGING_TIMES",
    "ONLY_OWN_CURRENT",
    "IMMEDIATE_DISCHARGING",
    "HOME_STORAGE_CHARGING",
]

AC_RUNNING_STATES: Final = {"COOLING", "HEATING", "HEATING_AUXILIARY", "VENTILATION"}
AUX_HEATING_RUNNING_STATES: Final = {"PREHEATING", "HEATING_AUXILIARY", "VENTILATION"}
ACTIVE_VENTILATION_RUNNING_STATES: Final = {"PREHEATING", "VENTILATION"}

MIN_TARGET_TEMPERATURE: Final = 16.0
MAX_TARGET_TEMPERATURE: Final = 30.0
TARGET_TEMPERATURE_STEP: Final = 0.5
