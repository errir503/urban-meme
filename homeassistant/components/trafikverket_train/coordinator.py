"""DataUpdateCoordinator for the Trafikverket Train integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging

from pytrafikverket import TrafikverketTrain
from pytrafikverket.exceptions import (
    InvalidAuthentication,
    MultipleTrainAnnouncementFound,
    NoTrainAnnouncementFound,
    UnknownError,
)
from pytrafikverket.trafikverket_train import StationInfo, TrainStop

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_WEEKDAY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_TIME, DOMAIN
from .util import next_departuredate


@dataclass
class TrainData:
    """Dataclass for Trafikverket Train data."""

    departure_time: datetime | None
    departure_state: str
    cancelled: bool
    delayed_time: int | None
    planned_time: datetime | None
    estimated_time: datetime | None
    actual_time: datetime | None
    other_info: str | None
    deviation: str | None
    product_filter: str | None


_LOGGER = logging.getLogger(__name__)
TIME_BETWEEN_UPDATES = timedelta(minutes=5)


def _get_as_utc(date_value: datetime | None) -> datetime | None:
    """Return utc datetime or None."""
    if date_value:
        return dt_util.as_utc(date_value)
    return None


def _get_as_joined(information: list[str] | None) -> str | None:
    """Return joined information or None."""
    if information:
        return ", ".join(information)
    return None


class TVDataUpdateCoordinator(DataUpdateCoordinator[TrainData]):
    """A Trafikverket Data Update Coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        to_station: StationInfo,
        from_station: StationInfo,
        filter_product: str | None,
    ) -> None:
        """Initialize the Trafikverket coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=TIME_BETWEEN_UPDATES,
        )
        self._train_api = TrafikverketTrain(
            async_get_clientsession(hass), entry.data[CONF_API_KEY]
        )
        self.from_station: StationInfo = from_station
        self.to_station: StationInfo = to_station
        self._time: time | None = dt_util.parse_time(entry.data[CONF_TIME])
        self._weekdays: list[str] = entry.data[CONF_WEEKDAY]
        self._filter_product = filter_product

    async def _async_update_data(self) -> TrainData:
        """Fetch data from Trafikverket."""

        when = dt_util.now()
        state: TrainStop | None = None
        if self._time:
            departure_day = next_departuredate(self._weekdays)
            when = datetime.combine(
                departure_day,
                self._time,
                dt_util.get_time_zone(self.hass.config.time_zone),
            )
        try:
            if self._time:
                state = await self._train_api.async_get_train_stop(
                    self.from_station, self.to_station, when, self._filter_product
                )
            else:
                state = await self._train_api.async_get_next_train_stop(
                    self.from_station, self.to_station, when, self._filter_product
                )
        except InvalidAuthentication as error:
            raise ConfigEntryAuthFailed from error
        except (
            NoTrainAnnouncementFound,
            MultipleTrainAnnouncementFound,
            UnknownError,
        ) as error:
            raise UpdateFailed(
                f"Train departure {when} encountered a problem: {error}"
            ) from error

        departure_time = state.advertised_time_at_location
        if state.estimated_time_at_location:
            departure_time = state.estimated_time_at_location
        elif state.time_at_location:
            departure_time = state.time_at_location

        delay_time = state.get_delay_time()

        states = TrainData(
            departure_time=_get_as_utc(departure_time),
            departure_state=state.get_state().value,
            cancelled=state.canceled,
            delayed_time=delay_time.seconds if delay_time else None,
            planned_time=_get_as_utc(state.advertised_time_at_location),
            estimated_time=_get_as_utc(state.estimated_time_at_location),
            actual_time=_get_as_utc(state.time_at_location),
            other_info=_get_as_joined(state.other_information),
            deviation=_get_as_joined(state.deviations),
            product_filter=self._filter_product,
        )

        return states
