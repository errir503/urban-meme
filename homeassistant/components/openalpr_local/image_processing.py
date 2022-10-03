"""Component that will help set the OpenALPR local for ALPR processing."""
from __future__ import annotations

import asyncio
import io
import logging
import re

import voluptuous as vol

from homeassistant.components.image_processing import (
    ATTR_CONFIDENCE,
    CONF_CONFIDENCE,
    PLATFORM_SCHEMA,
    ImageProcessingDeviceClass,
    ImageProcessingEntity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REGION,
    CONF_SOURCE,
)
from homeassistant.core import HomeAssistant, callback, split_entity_id
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.issue_registry import IssueSeverity, create_issue
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.async_ import run_callback_threadsafe

_LOGGER = logging.getLogger(__name__)

RE_ALPR_PLATE = re.compile(r"^plate\d*:")
RE_ALPR_RESULT = re.compile(r"- (\w*)\s*confidence: (\d*.\d*)")

EVENT_FOUND_PLATE = "image_processing.found_plate"

ATTR_PLATE = "plate"
ATTR_PLATES = "plates"
ATTR_VEHICLES = "vehicles"

OPENALPR_REGIONS = [
    "au",
    "auwide",
    "br",
    "eu",
    "fr",
    "gb",
    "kr",
    "kr2",
    "mx",
    "sg",
    "us",
    "vn2",
]

CONF_ALPR_BIN = "alpr_bin"

DEFAULT_BINARY = "alpr"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_REGION): vol.All(vol.Lower, vol.In(OPENALPR_REGIONS)),
        vol.Optional(CONF_ALPR_BIN, default=DEFAULT_BINARY): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the OpenALPR local platform."""
    create_issue(
        hass,
        "openalpr_local",
        "pending_removal",
        breaks_in_ha_version="2022.10.0",
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="pending_removal",
    )
    _LOGGER.warning(
        "The OpenALPR Local is deprecated and will be removed in Home Assistant 2022.10"
    )
    command = [config[CONF_ALPR_BIN], "-c", config[CONF_REGION], "-"]
    confidence = config[CONF_CONFIDENCE]

    entities = []
    for camera in config[CONF_SOURCE]:
        entities.append(
            OpenAlprLocalEntity(
                camera[CONF_ENTITY_ID], command, confidence, camera.get(CONF_NAME)
            )
        )

    async_add_entities(entities)


class ImageProcessingAlprEntity(ImageProcessingEntity):
    """Base entity class for ALPR image processing."""

    _attr_device_class = ImageProcessingDeviceClass.ALPR

    def __init__(self) -> None:
        """Initialize base ALPR entity."""
        self.plates: dict[str, float] = {}
        self.vehicles = 0

    @property
    def state(self):
        """Return the state of the entity."""
        confidence = 0
        plate = None

        # search high plate
        for i_pl, i_co in self.plates.items():
            if i_co > confidence:
                confidence = i_co
                plate = i_pl
        return plate

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        return {ATTR_PLATES: self.plates, ATTR_VEHICLES: self.vehicles}

    def process_plates(self, plates: dict[str, float], vehicles: int) -> None:
        """Send event with new plates and store data."""
        run_callback_threadsafe(
            self.hass.loop, self.async_process_plates, plates, vehicles
        ).result()

    @callback
    def async_process_plates(self, plates: dict[str, float], vehicles: int) -> None:
        """Send event with new plates and store data.

        plates are a dict in follow format:
          { '<plate>': confidence }

        This method must be run in the event loop.
        """
        plates = {
            plate: confidence
            for plate, confidence in plates.items()
            if self.confidence is None or confidence >= self.confidence
        }
        new_plates = set(plates) - set(self.plates)

        # Send events
        for i_plate in new_plates:
            self.hass.async_add_job(
                self.hass.bus.async_fire,
                EVENT_FOUND_PLATE,
                {
                    ATTR_PLATE: i_plate,
                    ATTR_ENTITY_ID: self.entity_id,
                    ATTR_CONFIDENCE: plates.get(i_plate),
                },
            )

        # Update entity store
        self.plates = plates
        self.vehicles = vehicles


class OpenAlprLocalEntity(ImageProcessingAlprEntity):
    """OpenALPR local api entity."""

    def __init__(self, camera_entity, command, confidence, name=None):
        """Initialize OpenALPR local API."""
        super().__init__()

        self._cmd = command
        self._camera = camera_entity
        self._confidence = confidence

        if name:
            self._name = name
        else:
            self._name = f"OpenAlpr {split_entity_id(camera_entity)[1]}"

    @property
    def confidence(self):
        """Return minimum confidence for send events."""
        return self._confidence

    @property
    def camera_entity(self):
        """Return camera entity id from process pictures."""
        return self._camera

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    async def async_process_image(self, image):
        """Process image.

        This method is a coroutine.
        """
        result = {}
        vehicles = 0

        alpr = await asyncio.create_subprocess_exec(
            *self._cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # Send image
        stdout, _ = await alpr.communicate(input=image)
        stdout = io.StringIO(str(stdout, "utf-8"))

        while True:
            line = stdout.readline()
            if not line:
                break

            new_plates = RE_ALPR_PLATE.search(line)
            new_result = RE_ALPR_RESULT.search(line)

            # Found new vehicle
            if new_plates:
                vehicles += 1
                continue

            # Found plate result
            if new_result:
                try:
                    result.update({new_result.group(1): float(new_result.group(2))})
                except ValueError:
                    continue

        self.async_process_plates(result, vehicles)
