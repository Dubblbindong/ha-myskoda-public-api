"""Sensors for the MyŠkoda Public API integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import VehicleData
from .const import (
    CHARGE_MODES,
    OP_SET_CHARGE_MODE,
    OP_SET_CHARGING_LIMIT,
    SECTION_ACTIVE_VENTILATION,
    SECTION_AIR_CONDITIONING,
    SECTION_AUXILIARY_HEATING,
    SECTION_CHARGING,
    SECTION_CHARGING_PROFILES,
    SECTION_FUEL_STATUS,
    SECTION_ODOMETER,
    SECTION_PARKING_POSITION,
    SECTION_STATUS,
)
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity
from .helpers import enum_value, get_in, has_operation, parse_timestamp, section_present

PARALLEL_UPDATES = 0

type VehicleMapping = Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class MySkodaSensorDescription(SensorEntityDescription):
    """Describes a MyŠkoda sensor."""

    value_fn: Callable[[VehicleData], StateType | datetime]
    section: str | None = None
    exists_fn: Callable[[VehicleMapping], bool] | None = None
    unit_fn: Callable[[VehicleMapping], str | None] | None = None
    attrs_fn: Callable[[VehicleMapping], dict[str, Any]] | None = None


def _value(
    path: str, transform: Callable[[Any], Any] | None = None
) -> Callable[[VehicleData], Any]:
    """Return a value function reading ``path`` from the vehicle data."""

    def _get(data: VehicleData) -> Any:
        value = get_in(data.vehicle, path)
        if value is None or transform is None:
            return value
        return transform(value)

    return _get


def _enum(path: str) -> Callable[[VehicleData], str | None]:
    return _value(path, enum_value)


def _timestamp(path: str) -> Callable[[VehicleData], datetime | None]:
    return _value(path, parse_timestamp)


def _temperature_unit(path: str) -> Callable[[VehicleMapping], str]:
    def _get(vehicle: VehicleMapping) -> str:
        if get_in(vehicle, f"{path}.unit") == "FAHRENHEIT":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    return _get


def _present(path: str) -> Callable[[VehicleMapping], bool]:
    return lambda vehicle: get_in(vehicle, path) is not None


def _lacks_operation(name: str) -> Callable[[VehicleMapping], bool]:
    return lambda vehicle: not has_operation(vehicle, name)


def _combustion_engine(vehicle: VehicleMapping) -> VehicleMapping | None:
    """Return the engine range object of the combustion engine, if any."""
    for key in ("primaryEngineRange", "secondaryEngineRange"):
        engine = get_in(vehicle, f"{SECTION_FUEL_STATUS}.{key}")
        if isinstance(engine, Mapping) and engine.get("engineType") not in (
            None,
            "ELECTRIC",
        ):
            return engine
    return None


def _fuel_level(data: VehicleData) -> Any:
    engine = _combustion_engine(data.vehicle)
    return engine.get("currentFuelLevelInPercent") if engine else None


def _has_fuel_level(vehicle: VehicleMapping) -> bool:
    engine = _combustion_engine(vehicle)
    return bool(engine) and engine.get("currentFuelLevelInPercent") is not None


def _engine_attrs(key: str) -> Callable[[VehicleMapping], dict[str, Any]]:
    def _get(vehicle: VehicleMapping) -> dict[str, Any]:
        engine = get_in(vehicle, f"{SECTION_FUEL_STATUS}.{key}") or {}
        return {
            "engine_type": enum_value(engine.get("engineType")),
            "state_of_charge": engine.get("currentSoCInPercent"),
            "fuel_level": engine.get("currentFuelLevelInPercent"),
        }

    return _get


def _profile_attrs(vehicle: VehicleMapping) -> dict[str, Any]:
    profile = get_in(vehicle, f"{SECTION_CHARGING_PROFILES}.currentVehiclePositionProfile") or {}
    return {
        "profile_id": profile.get("id"),
        "target_state_of_charge": profile.get("targetStateOfChargeInPercent"),
        "next_charging_time": profile.get("nextChargingTime"),
    }


def _rate_limit_remaining(data: VehicleData) -> int | None:
    return data.rate_limit.remaining if data.rate_limit else None


def _rate_limit_reset_at(data: VehicleData) -> datetime | None:
    """Return when the hourly quota is back, rounded up to the full minute.

    The headers jitter by a second or two between responses; rounding keeps the
    sensor from recording a new state on every poll.
    """
    if data.rate_limit is None or (reset_at := data.rate_limit.reset_at) is None:
        return None
    return (reset_at + timedelta(seconds=59)).replace(second=0, microsecond=0)


def _api_key_expires_at(data: VehicleData) -> datetime | None:
    return data.api_key_expires_at


CHARGING_STATES = [
    "connect_cable",
    "charging",
    "conserving",
    "ready_for_charging",
    "discharging",
    "charging_interrupted",
]
CHARGE_MODE_OPTIONS = [mode.lower() for mode in CHARGE_MODES]

SENSORS: tuple[MySkodaSensorDescription, ...] = (
    # ---------------------------------------------------------------- charging
    MySkodaSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        section=SECTION_CHARGING,
        value_fn=_value(f"{SECTION_CHARGING}.status.battery.stateOfChargeInPercent"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="electric_range",
        translation_key="electric_range",
        section=SECTION_CHARGING,
        value_fn=_value(
            f"{SECTION_CHARGING}.status.battery.remainingCruisingRangeInMeters",
            lambda meters: round(meters / 1000, 1),
        ),
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        section=SECTION_CHARGING,
        value_fn=_enum(f"{SECTION_CHARGING}.status.state"),
        device_class=SensorDeviceClass.ENUM,
        options=CHARGING_STATES,
    ),
    MySkodaSensorDescription(
        key="charge_type",
        translation_key="charge_type",
        section=SECTION_CHARGING,
        value_fn=_enum(f"{SECTION_CHARGING}.status.chargeType"),
        device_class=SensorDeviceClass.ENUM,
        options=["ac", "dc", "off"],
    ),
    MySkodaSensorDescription(
        key="charging_power",
        translation_key="charging_power",
        section=SECTION_CHARGING,
        value_fn=_value(f"{SECTION_CHARGING}.status.chargePowerInKw"),
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="charging_rate",
        translation_key="charging_rate",
        section=SECTION_CHARGING,
        value_fn=_value(f"{SECTION_CHARGING}.status.chargingRateInKilometersPerHour"),
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="remaining_charging_time",
        translation_key="remaining_charging_time",
        section=SECTION_CHARGING,
        value_fn=_value(f"{SECTION_CHARGING}.status.remainingTimeToFullyChargedInMinutes"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    MySkodaSensorDescription(
        key="fully_charged_at",
        translation_key="fully_charged_at",
        section=SECTION_CHARGING,
        value_fn=_timestamp(f"{SECTION_CHARGING}.status.fullyChargedAt"),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    # Read-only fallbacks when the vehicle does not offer the remote operation;
    # otherwise the number/select entities expose the same values.
    MySkodaSensorDescription(
        key="charging_limit",
        translation_key="charging_limit",
        section=SECTION_CHARGING,
        exists_fn=_lacks_operation(OP_SET_CHARGING_LIMIT),
        value_fn=_value(f"{SECTION_CHARGING}.settings.targetStateOfChargeInPercent"),
        native_unit_of_measurement=PERCENTAGE,
    ),
    MySkodaSensorDescription(
        key="charge_mode",
        translation_key="charge_mode",
        section=SECTION_CHARGING,
        exists_fn=_lacks_operation(OP_SET_CHARGE_MODE),
        value_fn=_enum(f"{SECTION_CHARGING}.settings.preferredChargeMode"),
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_MODE_OPTIONS,
    ),
    MySkodaSensorDescription(
        key="battery_care_mode",
        translation_key="battery_care_mode",
        section=SECTION_CHARGING,
        value_fn=_enum(f"{SECTION_CHARGING}.settings.chargingCareMode"),
        device_class=SensorDeviceClass.ENUM,
        options=["activated", "deactivated"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MySkodaSensorDescription(
        key="battery_care_target",
        translation_key="battery_care_target",
        section=SECTION_CHARGING,
        value_fn=_value(f"{SECTION_CHARGING}.settings.batteryCareModeTargetValueInPercent"),
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    MySkodaSensorDescription(
        key="max_charge_current",
        translation_key="max_charge_current",
        section=SECTION_CHARGING,
        value_fn=_enum(f"{SECTION_CHARGING}.settings.maxChargeCurrentAc"),
        device_class=SensorDeviceClass.ENUM,
        options=["reduced", "maximum"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MySkodaSensorDescription(
        key="max_charge_current_ampere",
        translation_key="max_charge_current_ampere",
        section=SECTION_CHARGING,
        value_fn=_value(f"{SECTION_CHARGING}.settings.maxChargeCurrentAcAmpere"),
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    MySkodaSensorDescription(
        key="auto_unlock_plug",
        translation_key="auto_unlock_plug",
        section=SECTION_CHARGING,
        value_fn=_enum(f"{SECTION_CHARGING}.settings.autoUnlockPlugWhenCharged"),
        device_class=SensorDeviceClass.ENUM,
        options=["permanent", "off"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    MySkodaSensorDescription(
        key="charging_updated_at",
        translation_key="charging_updated_at",
        section=SECTION_CHARGING,
        value_fn=_timestamp(f"{SECTION_CHARGING}.carCapturedTimestamp"),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ---------------------------------------------------------------- charging profiles
    MySkodaSensorDescription(
        key="current_charging_profile",
        translation_key="current_charging_profile",
        section=SECTION_CHARGING_PROFILES,
        value_fn=_value(f"{SECTION_CHARGING_PROFILES}.currentVehiclePositionProfile.name"),
        attrs_fn=_profile_attrs,
    ),
    # ---------------------------------------------------------------- fuel
    MySkodaSensorDescription(
        key="fuel_level",
        translation_key="fuel_level",
        section=SECTION_FUEL_STATUS,
        exists_fn=_has_fuel_level,
        value_fn=_fuel_level,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="total_range",
        translation_key="total_range",
        section=SECTION_FUEL_STATUS,
        value_fn=_value(f"{SECTION_FUEL_STATUS}.totalRangeInKm"),
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="primary_engine_range",
        translation_key="primary_engine_range",
        section=SECTION_FUEL_STATUS,
        exists_fn=_present(f"{SECTION_FUEL_STATUS}.primaryEngineRange"),
        value_fn=_value(f"{SECTION_FUEL_STATUS}.primaryEngineRange.remainingRangeInKm"),
        attrs_fn=_engine_attrs("primaryEngineRange"),
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="secondary_engine_range",
        translation_key="secondary_engine_range",
        section=SECTION_FUEL_STATUS,
        exists_fn=_present(f"{SECTION_FUEL_STATUS}.secondaryEngineRange"),
        value_fn=_value(f"{SECTION_FUEL_STATUS}.secondaryEngineRange.remainingRangeInKm"),
        attrs_fn=_engine_attrs("secondaryEngineRange"),
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="adblue_range",
        translation_key="adblue_range",
        section=SECTION_FUEL_STATUS,
        exists_fn=_present(f"{SECTION_FUEL_STATUS}.adBlueRange"),
        value_fn=_value(f"{SECTION_FUEL_STATUS}.adBlueRange"),
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MySkodaSensorDescription(
        key="car_type",
        translation_key="car_type",
        section=SECTION_FUEL_STATUS,
        value_fn=_enum(f"{SECTION_FUEL_STATUS}.carType"),
        device_class=SensorDeviceClass.ENUM,
        options=["hybrid", "gasoline", "diesel", "cng", "lpg"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    MySkodaSensorDescription(
        key="fuel_updated_at",
        translation_key="fuel_updated_at",
        section=SECTION_FUEL_STATUS,
        value_fn=_timestamp(f"{SECTION_FUEL_STATUS}.carCapturedTimestamp"),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ---------------------------------------------------------------- odometer
    MySkodaSensorDescription(
        key="odometer",
        translation_key="odometer",
        section=SECTION_ODOMETER,
        value_fn=_value(f"{SECTION_ODOMETER}.mileageInKm"),
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # ---------------------------------------------------------------- status
    MySkodaSensorDescription(
        key="doors_lock_state",
        translation_key="doors_lock_state",
        section=SECTION_STATUS,
        value_fn=_enum(f"{SECTION_STATUS}.overall.doorsLocked"),
        device_class=SensorDeviceClass.ENUM,
        options=["yes", "no", "opened", "trunk_opened"],
    ),
    MySkodaSensorDescription(
        key="status_updated_at",
        translation_key="status_updated_at",
        section=SECTION_STATUS,
        value_fn=_timestamp(f"{SECTION_STATUS}.carCapturedTimestamp"),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ---------------------------------------------------------------- parking position
    MySkodaSensorDescription(
        key="parking_state",
        translation_key="parking_state",
        section=SECTION_PARKING_POSITION,
        value_fn=_enum(f"{SECTION_PARKING_POSITION}.state"),
        device_class=SensorDeviceClass.ENUM,
        options=["parked", "in_motion"],
    ),
    MySkodaSensorDescription(
        key="parking_address",
        translation_key="parking_address",
        section=SECTION_PARKING_POSITION,
        value_fn=_value(f"{SECTION_PARKING_POSITION}.formattedAddress"),
    ),
    # ---------------------------------------------------------------- air conditioning
    MySkodaSensorDescription(
        key="air_conditioning_state",
        translation_key="air_conditioning_state",
        section=SECTION_AIR_CONDITIONING,
        value_fn=_enum(f"{SECTION_AIR_CONDITIONING}.state"),
        device_class=SensorDeviceClass.ENUM,
        options=["off", "cooling", "heating", "heating_auxiliary", "ventilation", "completed"],
    ),
    MySkodaSensorDescription(
        key="ac_target_temperature",
        translation_key="ac_target_temperature",
        section=SECTION_AIR_CONDITIONING,
        value_fn=_value(f"{SECTION_AIR_CONDITIONING}.targetTemperature.value"),
        unit_fn=_temperature_unit(f"{SECTION_AIR_CONDITIONING}.targetTemperature"),
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    MySkodaSensorDescription(
        key="ac_target_reached_at",
        translation_key="ac_target_reached_at",
        section=SECTION_AIR_CONDITIONING,
        value_fn=_timestamp(f"{SECTION_AIR_CONDITIONING}.estimatedReachOfTargetTemperatureAt"),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    MySkodaSensorDescription(
        key="air_conditioning_updated_at",
        translation_key="air_conditioning_updated_at",
        section=SECTION_AIR_CONDITIONING,
        value_fn=_timestamp(f"{SECTION_AIR_CONDITIONING}.carCapturedTimestamp"),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ---------------------------------------------------------------- auxiliary heating
    MySkodaSensorDescription(
        key="auxiliary_heating_state",
        translation_key="auxiliary_heating_state",
        section=SECTION_AUXILIARY_HEATING,
        value_fn=_enum(f"{SECTION_AUXILIARY_HEATING}.state"),
        device_class=SensorDeviceClass.ENUM,
        options=["off", "preheating", "heating_auxiliary", "ventilation"],
    ),
    MySkodaSensorDescription(
        key="auxiliary_heating_target_temperature",
        translation_key="auxiliary_heating_target_temperature",
        section=SECTION_AUXILIARY_HEATING,
        value_fn=_value(f"{SECTION_AUXILIARY_HEATING}.targetTemperature.value"),
        unit_fn=_temperature_unit(f"{SECTION_AUXILIARY_HEATING}.targetTemperature"),
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    MySkodaSensorDescription(
        key="auxiliary_heating_duration",
        translation_key="auxiliary_heating_duration",
        section=SECTION_AUXILIARY_HEATING,
        value_fn=_value(f"{SECTION_AUXILIARY_HEATING}.durationInSeconds"),
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    MySkodaSensorDescription(
        key="auxiliary_heating_start_mode",
        translation_key="auxiliary_heating_start_mode",
        section=SECTION_AUXILIARY_HEATING,
        value_fn=_enum(f"{SECTION_AUXILIARY_HEATING}.startMode"),
        device_class=SensorDeviceClass.ENUM,
        options=["heating", "ventilation"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ---------------------------------------------------------------- active ventilation
    MySkodaSensorDescription(
        key="active_ventilation_state",
        translation_key="active_ventilation_state",
        section=SECTION_ACTIVE_VENTILATION,
        value_fn=_enum(f"{SECTION_ACTIVE_VENTILATION}.state"),
        device_class=SensorDeviceClass.ENUM,
        options=["off", "preheating", "ventilation"],
    ),
    MySkodaSensorDescription(
        key="active_ventilation_duration",
        translation_key="active_ventilation_duration",
        section=SECTION_ACTIVE_VENTILATION,
        value_fn=_value(f"{SECTION_ACTIVE_VENTILATION}.durationInSeconds"),
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ---------------------------------------------------------------- vehicle info / API
    MySkodaSensorDescription(
        key="license_plate",
        translation_key="license_plate",
        exists_fn=_present("licensePlate"),
        value_fn=_value("licensePlate"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MySkodaSensorDescription(
        key="api_requests_remaining",
        translation_key="api_requests_remaining",
        value_fn=_rate_limit_remaining,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MySkodaSensorDescription(
        key="api_rate_limit_reset_at",
        translation_key="api_rate_limit_reset_at",
        value_fn=_rate_limit_reset_at,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MySkodaSensorDescription(
        key="api_key_expires_at",
        translation_key="api_key_expires_at",
        value_fn=_api_key_expires_at,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the sensors the vehicle supports."""
    coordinator = entry.runtime_data
    vehicle = coordinator.vehicle
    async_add_entities(
        MySkodaSensor(coordinator, description)
        for description in SENSORS
        if section_present(vehicle, description.section)
        and (description.exists_fn is None or description.exists_fn(vehicle))
    )


class MySkodaSensor(MySkodaEntity, SensorEntity):
    """A sensor backed by one value of the vehicle response."""

    entity_description: MySkodaSensorDescription

    def __init__(
        self,
        coordinator: MySkodaVehicleCoordinator,
        description: MySkodaSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key, description.section)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit, which can depend on the data (temperature unit)."""
        if self.entity_description.unit_fn is not None:
            return self.entity_description.unit_fn(self.vehicle)
        return super().native_unit_of_measurement

    @property
    def options(self) -> list[str] | None:
        """Return the enum options, tolerating values the API added later."""
        options = self.entity_description.options
        if options is None:
            return None
        value = self.native_value
        if isinstance(value, str) and value not in options:
            return [*options, value]
        return options

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.entity_description.key == "api_requests_remaining":
            rate_limit = self.coordinator.rate_limit
            if rate_limit is None:
                return None
            return {
                "limit": rate_limit.limit,
                "reset_at": rate_limit.reset_at.isoformat() if rate_limit.reset_at else None,
            }
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.vehicle)
