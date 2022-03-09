"""Support for Google - Calendar Event Devices."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
from typing import Any

from oauth2client.client import (
    FlowExchangeError,
    OAuth2DeviceCodeError,
    OAuth2WebServerFlow,
)
from oauth2client.file import Storage
import voluptuous as vol
from voluptuous.error import Error as VoluptuousError
import yaml

from homeassistant.components import persistent_notification
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_NAME,
    CONF_OFFSET,
    Platform,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.event import track_utc_time_change
from homeassistant.helpers.typing import ConfigType

from .api import GoogleCalendarService

_LOGGER = logging.getLogger(__name__)

DOMAIN = "google"
ENTITY_ID_FORMAT = DOMAIN + ".{}"

CONF_TRACK_NEW = "track_new_calendar"

CONF_CAL_ID = "cal_id"
CONF_TRACK = "track"
CONF_SEARCH = "search"
CONF_IGNORE_AVAILABILITY = "ignore_availability"
CONF_MAX_RESULTS = "max_results"
CONF_CALENDAR_ACCESS = "calendar_access"

DEFAULT_CONF_OFFSET = "!!"

EVENT_CALENDAR_ID = "calendar_id"
EVENT_DESCRIPTION = "description"
EVENT_END_CONF = "end"
EVENT_END_DATE = "end_date"
EVENT_END_DATETIME = "end_date_time"
EVENT_IN = "in"
EVENT_IN_DAYS = "days"
EVENT_IN_WEEKS = "weeks"
EVENT_START_CONF = "start"
EVENT_START_DATE = "start_date"
EVENT_START_DATETIME = "start_date_time"
EVENT_SUMMARY = "summary"
EVENT_TYPES_CONF = "event_types"

NOTIFICATION_ID = "google_calendar_notification"
NOTIFICATION_TITLE = "Google Calendar Setup"
GROUP_NAME_ALL_CALENDARS = "Google Calendar Sensors"

SERVICE_SCAN_CALENDARS = "scan_for_calendars"
SERVICE_FOUND_CALENDARS = "found_calendar"
SERVICE_ADD_EVENT = "add_event"

DATA_SERVICE = "service"

YAML_DEVICES = f"{DOMAIN}_calendars.yaml"

TOKEN_FILE = f".{DOMAIN}.token"


class FeatureAccess(Enum):
    """Class to represent different access scopes."""

    read_only = "https://www.googleapis.com/auth/calendar.readonly"
    read_write = "https://www.googleapis.com/auth/calendar"

    def __init__(self, scope: str) -> None:
        """Init instance."""
        self._scope = scope

    @property
    def scope(self) -> str:
        """Google calendar scope for the feature."""
        return self._scope


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_CLIENT_ID): cv.string,
                vol.Required(CONF_CLIENT_SECRET): cv.string,
                vol.Optional(CONF_TRACK_NEW, default=True): cv.boolean,
                vol.Optional(CONF_CALENDAR_ACCESS, default="read_write"): cv.enum(
                    FeatureAccess
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_SINGLE_CALSEARCH_CONFIG = vol.All(
    cv.deprecated(CONF_MAX_RESULTS),
    vol.Schema(
        {
            vol.Required(CONF_NAME): cv.string,
            vol.Required(CONF_DEVICE_ID): cv.string,
            vol.Optional(CONF_IGNORE_AVAILABILITY, default=True): cv.boolean,
            vol.Optional(CONF_OFFSET): cv.string,
            vol.Optional(CONF_SEARCH): cv.string,
            vol.Optional(CONF_TRACK): cv.boolean,
            vol.Optional(CONF_MAX_RESULTS): cv.positive_int,  # Now unused
        }
    ),
)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CAL_ID): cv.string,
        vol.Required(CONF_ENTITIES, None): vol.All(
            cv.ensure_list, [_SINGLE_CALSEARCH_CONFIG]
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

_EVENT_IN_TYPES = vol.Schema(
    {
        vol.Exclusive(EVENT_IN_DAYS, EVENT_TYPES_CONF): cv.positive_int,
        vol.Exclusive(EVENT_IN_WEEKS, EVENT_TYPES_CONF): cv.positive_int,
    }
)

ADD_EVENT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(EVENT_CALENDAR_ID): cv.string,
        vol.Required(EVENT_SUMMARY): cv.string,
        vol.Optional(EVENT_DESCRIPTION, default=""): cv.string,
        vol.Exclusive(EVENT_START_DATE, EVENT_START_CONF): cv.date,
        vol.Exclusive(EVENT_END_DATE, EVENT_END_CONF): cv.date,
        vol.Exclusive(EVENT_START_DATETIME, EVENT_START_CONF): cv.datetime,
        vol.Exclusive(EVENT_END_DATETIME, EVENT_END_CONF): cv.datetime,
        vol.Exclusive(EVENT_IN, EVENT_START_CONF, EVENT_END_CONF): _EVENT_IN_TYPES,
    }
)


def do_authentication(
    hass: HomeAssistant,
    hass_config: ConfigType,
    config: ConfigType,
    storage: Storage,
) -> bool:
    """Notify user of actions and authenticate.

    Notify user of user_code and verification_url then poll
    until we have an access token.
    """
    oauth = OAuth2WebServerFlow(
        client_id=config[CONF_CLIENT_ID],
        client_secret=config[CONF_CLIENT_SECRET],
        scope=config[CONF_CALENDAR_ACCESS].scope,
        redirect_uri="Home-Assistant.io",
    )
    try:
        dev_flow = oauth.step1_get_device_and_user_codes()
    except OAuth2DeviceCodeError as err:
        persistent_notification.create(
            hass,
            f"Error: {err}<br />You will need to restart hass after fixing." "",
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )
        return False

    persistent_notification.create(
        hass,
        (
            f"In order to authorize Home-Assistant to view your calendars "
            f'you must visit: <a href="{dev_flow.verification_url}" target="_blank">{dev_flow.verification_url}</a> and enter '
            f"code: {dev_flow.user_code}"
        ),
        title=NOTIFICATION_TITLE,
        notification_id=NOTIFICATION_ID,
    )

    listener: CALLBACK_TYPE | None = None

    def step2_exchange(now: datetime) -> None:
        """Keep trying to validate the user_code until it expires."""
        _LOGGER.debug("Attempting to validate user code")

        # For some reason, oauth.step1_get_device_and_user_codes() returns a datetime
        # object without tzinfo. For the comparison below to work, it needs one.
        user_code_expiry = dev_flow.user_code_expiry.replace(tzinfo=timezone.utc)

        if now >= user_code_expiry:
            persistent_notification.create(
                hass,
                "Authentication code expired, please restart "
                "Home-Assistant and try again",
                title=NOTIFICATION_TITLE,
                notification_id=NOTIFICATION_ID,
            )
            assert listener
            listener()
            return

        try:
            credentials = oauth.step2_exchange(device_flow_info=dev_flow)
        except FlowExchangeError:
            # not ready yet, call again
            return

        storage.put(credentials)
        do_setup(hass, hass_config, config)
        assert listener
        listener()
        persistent_notification.create(
            hass,
            (
                f"We are all setup now. Check {YAML_DEVICES} for calendars that have "
                f"been found"
            ),
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )

    listener = track_utc_time_change(
        hass, step2_exchange, second=range(1, 60, dev_flow.interval)
    )

    return True


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Google platform."""

    if not (conf := config.get(DOMAIN, {})):
        # component is set up by tts platform
        return True

    storage = Storage(hass.config.path(TOKEN_FILE))
    hass.data[DOMAIN] = {
        DATA_SERVICE: GoogleCalendarService(hass, storage),
    }
    creds = storage.get()
    if (
        not creds
        or not creds.scopes
        or conf[CONF_CALENDAR_ACCESS].scope not in creds.scopes
    ):
        do_authentication(hass, config, conf, storage)
    else:
        do_setup(hass, config, conf)

    return True


def setup_services(
    hass: HomeAssistant,
    hass_config: ConfigType,
    config: ConfigType,
    calendar_service: GoogleCalendarService,
) -> None:
    """Set up the service listeners."""

    created_calendars = set()
    calendars = load_config(hass.config.path(YAML_DEVICES))

    def _found_calendar(call: ServiceCall) -> None:
        """Check if we know about a calendar and generate PLATFORM_DISCOVER."""
        calendar = get_calendar_info(hass, call.data)
        calendar_id = calendar[CONF_CAL_ID]

        if calendar_id in created_calendars:
            return
        created_calendars.add(calendar_id)

        # Populate the yaml file with all discovered calendars
        if calendar_id not in calendars:
            calendars[calendar_id] = calendar
            update_config(hass.config.path(YAML_DEVICES), calendar)
        else:
            # Prefer entity/name information from yaml, overriding api
            calendar = calendars[calendar_id]

        discovery.load_platform(
            hass,
            Platform.CALENDAR,
            DOMAIN,
            calendar,
            hass_config,
        )

    hass.services.register(DOMAIN, SERVICE_FOUND_CALENDARS, _found_calendar)

    def _scan_for_calendars(call: ServiceCall) -> None:
        """Scan for new calendars."""
        calendars = calendar_service.list_calendars()
        for calendar in calendars:
            calendar[CONF_TRACK] = config[CONF_TRACK_NEW]
            hass.services.call(DOMAIN, SERVICE_FOUND_CALENDARS, calendar)

    hass.services.register(DOMAIN, SERVICE_SCAN_CALENDARS, _scan_for_calendars)

    def _add_event(call: ServiceCall) -> None:
        """Add a new event to calendar."""
        start = {}
        end = {}

        if EVENT_IN in call.data:
            if EVENT_IN_DAYS in call.data[EVENT_IN]:
                now = datetime.now()

                start_in = now + timedelta(days=call.data[EVENT_IN][EVENT_IN_DAYS])
                end_in = start_in + timedelta(days=1)

                start = {"date": start_in.strftime("%Y-%m-%d")}
                end = {"date": end_in.strftime("%Y-%m-%d")}

            elif EVENT_IN_WEEKS in call.data[EVENT_IN]:
                now = datetime.now()

                start_in = now + timedelta(weeks=call.data[EVENT_IN][EVENT_IN_WEEKS])
                end_in = start_in + timedelta(days=1)

                start = {"date": start_in.strftime("%Y-%m-%d")}
                end = {"date": end_in.strftime("%Y-%m-%d")}

        elif EVENT_START_DATE in call.data:
            start = {"date": str(call.data[EVENT_START_DATE])}
            end = {"date": str(call.data[EVENT_END_DATE])}

        elif EVENT_START_DATETIME in call.data:
            start_dt = str(
                call.data[EVENT_START_DATETIME].strftime("%Y-%m-%dT%H:%M:%S")
            )
            end_dt = str(call.data[EVENT_END_DATETIME].strftime("%Y-%m-%dT%H:%M:%S"))
            start = {"dateTime": start_dt, "timeZone": str(hass.config.time_zone)}
            end = {"dateTime": end_dt, "timeZone": str(hass.config.time_zone)}

        calendar_service.create_event(
            call.data[EVENT_CALENDAR_ID],
            {
                "summary": call.data[EVENT_SUMMARY],
                "description": call.data[EVENT_DESCRIPTION],
                "start": start,
                "end": end,
            },
        )

    # Only expose the add event service if we have the correct permissions
    if config.get(CONF_CALENDAR_ACCESS) is FeatureAccess.read_write:
        hass.services.register(
            DOMAIN, SERVICE_ADD_EVENT, _add_event, schema=ADD_EVENT_SERVICE_SCHEMA
        )


def do_setup(hass: HomeAssistant, hass_config: ConfigType, config: ConfigType) -> None:
    """Run the setup after we have everything configured."""
    calendar_service = hass.data[DOMAIN][DATA_SERVICE]
    setup_services(hass, hass_config, config, calendar_service)

    # Fetch calendars from the API
    hass.services.call(DOMAIN, SERVICE_SCAN_CALENDARS, None)


def get_calendar_info(
    hass: HomeAssistant, calendar: Mapping[str, Any]
) -> dict[str, Any]:
    """Convert data from Google into DEVICE_SCHEMA."""
    calendar_info: dict[str, Any] = DEVICE_SCHEMA(
        {
            CONF_CAL_ID: calendar["id"],
            CONF_ENTITIES: [
                {
                    CONF_TRACK: calendar["track"],
                    CONF_NAME: calendar["summary"],
                    CONF_DEVICE_ID: generate_entity_id(
                        "{}", calendar["summary"], hass=hass
                    ),
                }
            ],
        }
    )
    return calendar_info


def load_config(path: str) -> dict[str, Any]:
    """Load the google_calendar_devices.yaml."""
    calendars = {}
    try:
        with open(path, encoding="utf8") as file:
            data = yaml.safe_load(file)
            for calendar in data:
                try:
                    calendars.update({calendar[CONF_CAL_ID]: DEVICE_SCHEMA(calendar)})
                except VoluptuousError as exception:
                    # keep going
                    _LOGGER.warning("Calendar Invalid Data: %s", exception)
    except FileNotFoundError as err:
        _LOGGER.debug("Error reading calendar configuration: %s", err)
        # When YAML file could not be loaded/did not contain a dict
        return {}

    return calendars


def update_config(path: str, calendar: dict[str, Any]) -> None:
    """Write the google_calendar_devices.yaml."""
    try:
        with open(path, "a", encoding="utf8") as out:
            out.write("\n")
            yaml.dump([calendar], out, default_flow_style=False)
    except FileNotFoundError as err:
        _LOGGER.debug("Error persisting calendar configuration: %s", err)
