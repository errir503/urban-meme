"""Train information for departures and delays, provided by Trafikverket."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from pytrafikverket import TrafikverketTrain
from pytrafikverket.trafikverket_train import StationInfo, TrainStop
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_WEEKDAY, WEEKDAYS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.dt import as_utc, get_time_zone, parse_time

from .const import CONF_FROM, CONF_TIME, CONF_TO, CONF_TRAINS, DOMAIN
from .util import create_unique_id

_LOGGER = logging.getLogger(__name__)

ATTR_DEPARTURE_STATE = "departure_state"
ATTR_CANCELED = "canceled"
ATTR_DELAY_TIME = "number_of_minutes_delayed"
ATTR_PLANNED_TIME = "planned_time"
ATTR_ESTIMATED_TIME = "estimated_time"
ATTR_ACTUAL_TIME = "actual_time"
ATTR_OTHER_INFORMATION = "other_information"
ATTR_DEVIATIONS = "deviations"

ICON = "mdi:train"
SCAN_INTERVAL = timedelta(minutes=5)
STOCKHOLM_TIMEZONE = get_time_zone("Europe/Stockholm")

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_TRAINS): [
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_TO): cv.string,
                vol.Required(CONF_FROM): cv.string,
                vol.Optional(CONF_TIME): cv.time,
                vol.Optional(CONF_WEEKDAY, default=WEEKDAYS): vol.All(
                    cv.ensure_list, [vol.In(WEEKDAYS)]
                ),
            }
        ],
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import Trafikverket Train configuration from YAML."""
    _LOGGER.warning(
        # Config flow added in Home Assistant Core 2022.3, remove import flow in 2022.7
        "Loading Trafikverket Train via platform setup is deprecated; Please remove it from your configuration"
    )

    for train in config[CONF_TRAINS]:

        new_config = {
            CONF_API_KEY: config[CONF_API_KEY],
            CONF_FROM: train[CONF_FROM],
            CONF_TO: train[CONF_TO],
            CONF_TIME: str(train.get(CONF_TIME)),
            CONF_WEEKDAY: train.get(CONF_WEEKDAY, WEEKDAYS),
        }
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=new_config,
            )
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Trafikverket sensor entry."""

    httpsession = async_get_clientsession(hass)
    train_api = TrafikverketTrain(httpsession, entry.data[CONF_API_KEY])

    try:
        to_station = await train_api.async_get_train_station(entry.data[CONF_TO])
        from_station = await train_api.async_get_train_station(entry.data[CONF_FROM])
    except ValueError as error:
        if "Invalid authentication" in error.args[0]:
            raise ConfigEntryAuthFailed from error
        raise ConfigEntryNotReady(
            f"Problem when trying station {entry.data[CONF_FROM]} to {entry.data[CONF_TO]}. Error: {error} "
        ) from error

    train_time = (
        parse_time(entry.data.get(CONF_TIME, "")) if entry.data.get(CONF_TIME) else None
    )

    async_add_entities(
        [
            TrainSensor(
                train_api,
                entry.data[CONF_NAME],
                from_station,
                to_station,
                entry.data[CONF_WEEKDAY],
                train_time,
                entry.entry_id,
            )
        ],
        True,
    )


def next_weekday(fromdate: date, weekday: int) -> date:
    """Return the date of the next time a specific weekday happen."""
    days_ahead = weekday - fromdate.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return fromdate + timedelta(days_ahead)


def next_departuredate(departure: list[str]) -> date:
    """Calculate the next departuredate from an array input of short days."""
    today_date = date.today()
    today_weekday = date.weekday(today_date)
    if WEEKDAYS[today_weekday] in departure:
        return today_date
    for day in departure:
        next_departure = WEEKDAYS.index(day)
        if next_departure > today_weekday:
            return next_weekday(today_date, next_departure)
    return next_weekday(today_date, WEEKDAYS.index(departure[0]))


def _to_iso_format(traintime: datetime) -> str:
    """Return isoformatted utc time."""
    return as_utc(traintime.replace(tzinfo=STOCKHOLM_TIMEZONE)).isoformat()


class TrainSensor(SensorEntity):
    """Contains data about a train depature."""

    _attr_icon = ICON
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        train_api: TrafikverketTrain,
        name: str,
        from_station: StationInfo,
        to_station: StationInfo,
        weekday: list,
        departuretime: time | None,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        self._train_api = train_api
        self._attr_name = name
        self._from_station = from_station
        self._to_station = to_station
        self._weekday = weekday
        self._time = departuretime
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry_id)},
            manufacturer="Trafikverket",
            model="v1.2",
            name=name,
            configuration_url="https://api.trafikinfo.trafikverket.se/",
        )
        self._attr_unique_id = create_unique_id(
            from_station.name, to_station.name, departuretime, weekday
        )

    async def async_update(self) -> None:
        """Retrieve latest state."""
        when = datetime.now()
        _state: TrainStop | None = None
        if self._time:
            departure_day = next_departuredate(self._weekday)
            when = datetime.combine(departure_day, self._time).replace(
                tzinfo=STOCKHOLM_TIMEZONE
            )
        try:
            if self._time:
                _state = await self._train_api.async_get_train_stop(
                    self._from_station, self._to_station, when
                )
            else:

                _state = await self._train_api.async_get_next_train_stop(
                    self._from_station, self._to_station, when
                )
        except ValueError as output_error:
            _LOGGER.error("Departure %s encountered a problem: %s", when, output_error)

        if not _state:
            self._attr_available = False
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return

        self._attr_available = True

        # The original datetime doesn't provide a timezone so therefore attaching it here.
        self._attr_native_value = _state.advertised_time_at_location.replace(
            tzinfo=STOCKHOLM_TIMEZONE
        )
        if _state.time_at_location:
            self._attr_native_value = _state.time_at_location.replace(
                tzinfo=STOCKHOLM_TIMEZONE
            )
        if _state.estimated_time_at_location:
            self._attr_native_value = _state.estimated_time_at_location.replace(
                tzinfo=STOCKHOLM_TIMEZONE
            )

        self._update_attributes(_state)

    def _update_attributes(self, state: TrainStop) -> None:
        """Return extra state attributes."""

        attributes: dict[str, Any] = {
            ATTR_DEPARTURE_STATE: state.get_state().name,
            ATTR_CANCELED: state.canceled,
            ATTR_DELAY_TIME: None,
            ATTR_PLANNED_TIME: None,
            ATTR_ESTIMATED_TIME: None,
            ATTR_ACTUAL_TIME: None,
            ATTR_OTHER_INFORMATION: None,
            ATTR_DEVIATIONS: None,
        }

        if delay_in_minutes := state.get_delay_time():
            attributes[ATTR_DELAY_TIME] = delay_in_minutes.total_seconds() / 60

        if advert_time := state.advertised_time_at_location:
            attributes[ATTR_PLANNED_TIME] = _to_iso_format(advert_time)

        if est_time := state.estimated_time_at_location:
            attributes[ATTR_ESTIMATED_TIME] = _to_iso_format(est_time)

        if time_location := state.time_at_location:
            attributes[ATTR_ACTUAL_TIME] = _to_iso_format(time_location)

        if other_info := state.other_information:
            attributes[ATTR_OTHER_INFORMATION] = ", ".join(other_info)

        if deviation := state.deviations:
            attributes[ATTR_DEVIATIONS] = ", ".join(deviation)

        self._attr_extra_state_attributes = attributes
