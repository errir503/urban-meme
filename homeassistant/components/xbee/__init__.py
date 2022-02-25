"""Support for XBee Zigbee devices."""
# pylint: disable=import-error
from binascii import hexlify, unhexlify
import logging

from serial import Serial, SerialException
import voluptuous as vol
from xbee_helper import ZigBee
import xbee_helper.const as xb_const
from xbee_helper.device import convert_adc
from xbee_helper.exceptions import ZigBeeException, ZigBeeTxFailure

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_DEVICE,
    CONF_NAME,
    CONF_PIN,
    EVENT_HOMEASSISTANT_STOP,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SIGNAL_XBEE_FRAME_RECEIVED = "xbee_frame_received"

CONF_BAUD = "baud"

DEFAULT_DEVICE = "/dev/ttyUSB0"
DEFAULT_BAUD = 9600
DEFAULT_ADC_MAX_VOLTS = 1.2

ATTR_FRAME = "frame"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_BAUD, default=DEFAULT_BAUD): cv.string,
                vol.Optional(CONF_DEVICE, default=DEFAULT_DEVICE): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_PIN): cv.positive_int,
        vol.Optional(CONF_ADDRESS): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the connection to the XBee Zigbee device."""
    usb_device = config[DOMAIN].get(CONF_DEVICE, DEFAULT_DEVICE)
    baud = int(config[DOMAIN].get(CONF_BAUD, DEFAULT_BAUD))
    try:
        ser = Serial(usb_device, baud)
    except SerialException as exc:
        _LOGGER.exception("Unable to open serial port for XBee: %s", exc)
        return False
    zigbee_device = ZigBee(ser)

    def close_serial_port(*args):
        """Close the serial port we're using to communicate with the XBee."""
        zigbee_device.zb.serial.close()

    def _frame_received(frame):
        """Run when a XBee Zigbee frame is received.

        Pickles the frame, then encodes it into base64 since it contains
        non JSON serializable binary.
        """
        dispatcher_send(hass, SIGNAL_XBEE_FRAME_RECEIVED, frame)

    hass.data[DOMAIN] = zigbee_device
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, close_serial_port)
    zigbee_device.add_frame_rx_handler(_frame_received)

    return True


def frame_is_relevant(entity, frame):
    """Test whether the frame is relevant to the entity."""
    if frame.get("source_addr_long") != entity.config.address:
        return False
    return "samples" in frame


class XBeeConfig:
    """Handle the fetching of configuration from the config file."""

    def __init__(self, config):
        """Initialize the configuration."""
        self._config = config
        self._should_poll = config.get("poll", True)

    @property
    def name(self):
        """Return the name given to the entity."""
        return self._config["name"]

    @property
    def address(self):
        """Return the address of the device.

        If an address has been provided, unhexlify it, otherwise return None
        as we're talking to our local XBee device.
        """
        if (address := self._config.get("address")) is not None:
            return unhexlify(address)
        return address

    @property
    def should_poll(self):
        """Return the polling state."""
        return self._should_poll


class XBeePinConfig(XBeeConfig):
    """Handle the fetching of configuration from the configuration file."""

    @property
    def pin(self):
        """Return the GPIO pin number."""
        return self._config["pin"]


class XBeeDigitalInConfig(XBeePinConfig):
    """A subclass of XBeePinConfig."""

    def __init__(self, config):
        """Initialise the XBee Zigbee Digital input config."""
        super().__init__(config)
        self._bool2state, self._state2bool = self.boolean_maps

    @property
    def boolean_maps(self):
        """Create mapping dictionaries for potential inversion of booleans.

        Create dicts to map the pin state (true/false) to potentially inverted
        values depending on the on_state config value which should be set to
        "low" or "high".
        """
        if self._config.get("on_state", "").lower() == "low":
            bool2state = {True: False, False: True}
        else:
            bool2state = {True: True, False: False}
        state2bool = {v: k for k, v in bool2state.items()}
        return bool2state, state2bool

    @property
    def bool2state(self):
        """Return a dictionary mapping the internal value to the Zigbee value.

        For the translation of on/off as being pin high or low.
        """
        return self._bool2state

    @property
    def state2bool(self):
        """Return a dictionary mapping the Zigbee value to the internal value.

        For the translation of pin high/low as being on or off.
        """
        return self._state2bool


class XBeeDigitalOutConfig(XBeePinConfig):
    """A subclass of XBeePinConfig.

    Set _should_poll to default as False instead of True. The value will
    still be overridden by the presence of a 'poll' config entry.
    """

    def __init__(self, config):
        """Initialize the XBee Zigbee Digital out."""
        super().__init__(config)
        self._bool2state, self._state2bool = self.boolean_maps
        self._should_poll = config.get("poll", False)

    @property
    def boolean_maps(self):
        """Create dicts to map booleans to pin high/low and vice versa.

        Depends on the config item "on_state" which should be set to "low"
        or "high".
        """
        if self._config.get("on_state", "").lower() == "low":
            bool2state = {
                True: xb_const.GPIO_DIGITAL_OUTPUT_LOW,
                False: xb_const.GPIO_DIGITAL_OUTPUT_HIGH,
            }
        else:
            bool2state = {
                True: xb_const.GPIO_DIGITAL_OUTPUT_HIGH,
                False: xb_const.GPIO_DIGITAL_OUTPUT_LOW,
            }
        state2bool = {v: k for k, v in bool2state.items()}
        return bool2state, state2bool

    @property
    def bool2state(self):
        """Return a dictionary mapping booleans to GPIOSetting objects.

        For the translation of on/off as being pin high or low.
        """
        return self._bool2state

    @property
    def state2bool(self):
        """Return a dictionary mapping GPIOSetting objects to booleans.

        For the translation of pin high/low as being on or off.
        """
        return self._state2bool


class XBeeAnalogInConfig(XBeePinConfig):
    """Representation of a XBee Zigbee GPIO pin set to analog in."""

    @property
    def max_voltage(self):
        """Return the voltage for ADC to report its highest value."""
        return float(self._config.get("max_volts", DEFAULT_ADC_MAX_VOLTS))


class XBeeDigitalIn(Entity):
    """Representation of a GPIO pin configured as a digital input."""

    def __init__(self, config, device):
        """Initialize the device."""
        self._config = config
        self._device = device
        self._state = False

    async def async_added_to_hass(self):
        """Register callbacks."""

        def handle_frame(frame):
            """Handle an incoming frame.

            Handle an incoming frame and update our status if it contains
            information relating to this device.
            """
            if not frame_is_relevant(self, frame):
                return
            sample = next(iter(frame["samples"]))
            pin_name = xb_const.DIGITAL_PINS[self._config.pin]
            if pin_name not in sample:
                # Doesn't contain information about our pin
                return
            # Set state to the value of sample, respecting any inversion
            # logic from the on_state config variable.
            self._state = self._config.state2bool[
                self._config.bool2state[sample[pin_name]]
            ]
            self.schedule_update_ha_state()

        async_dispatcher_connect(self.hass, SIGNAL_XBEE_FRAME_RECEIVED, handle_frame)

    @property
    def name(self):
        """Return the name of the input."""
        return self._config.name

    @property
    def config(self):
        """Return the entity's configuration."""
        return self._config

    @property
    def should_poll(self):
        """Return the state of the polling, if needed."""
        return self._config.should_poll

    @property
    def is_on(self):
        """Return True if the Entity is on, else False."""
        return self._state

    def update(self):
        """Ask the Zigbee device what state its input pin is in."""
        try:
            sample = self._device.get_sample(self._config.address)
        except ZigBeeTxFailure:
            _LOGGER.warning(
                "Transmission failure when attempting to get sample from "
                "Zigbee device at address: %s",
                hexlify(self._config.address),
            )
            return
        except ZigBeeException as exc:
            _LOGGER.exception("Unable to get sample from Zigbee device: %s", exc)
            return
        pin_name = xb_const.DIGITAL_PINS[self._config.pin]
        if pin_name not in sample:
            _LOGGER.warning(
                "Pin %s (%s) was not in the sample provided by Zigbee device %s",
                self._config.pin,
                pin_name,
                hexlify(self._config.address),
            )
            return
        self._state = self._config.state2bool[sample[pin_name]]


class XBeeDigitalOut(XBeeDigitalIn):
    """Representation of a GPIO pin configured as a digital input."""

    def _set_state(self, state):
        """Initialize the XBee Zigbee digital out device."""
        try:
            self._device.set_gpio_pin(
                self._config.pin, self._config.bool2state[state], self._config.address
            )
        except ZigBeeTxFailure:
            _LOGGER.warning(
                "Transmission failure when attempting to set output pin on "
                "Zigbee device at address: %s",
                hexlify(self._config.address),
            )
            return
        except ZigBeeException as exc:
            _LOGGER.exception("Unable to set digital pin on XBee device: %s", exc)
            return
        self._state = state
        if not self.should_poll:
            self.schedule_update_ha_state()

    def turn_on(self, **kwargs):
        """Set the digital output to its 'on' state."""
        self._set_state(True)

    def turn_off(self, **kwargs):
        """Set the digital output to its 'off' state."""
        self._set_state(False)

    def update(self):
        """Ask the XBee device what its output is set to."""
        try:
            pin_state = self._device.get_gpio_pin(
                self._config.pin, self._config.address
            )
        except ZigBeeTxFailure:
            _LOGGER.warning(
                "Transmission failure when attempting to get output pin status"
                " from Zigbee device at address: %s",
                hexlify(self._config.address),
            )
            return
        except ZigBeeException as exc:
            _LOGGER.exception(
                "Unable to get output pin status from XBee device: %s", exc
            )
            return
        self._state = self._config.state2bool[pin_state]


class XBeeAnalogIn(SensorEntity):
    """Representation of a GPIO pin configured as an analog input."""

    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, config, device):
        """Initialize the XBee analog in device."""
        self._config = config
        self._device = device
        self._value = None

    async def async_added_to_hass(self):
        """Register callbacks."""

        def handle_frame(frame):
            """Handle an incoming frame.

            Handle an incoming frame and update our status if it contains
            information relating to this device.
            """
            if not frame_is_relevant(self, frame):
                return
            sample = frame["samples"].pop()
            pin_name = xb_const.ANALOG_PINS[self._config.pin]
            if pin_name not in sample:
                # Doesn't contain information about our pin
                return
            self._value = convert_adc(
                sample[pin_name], xb_const.ADC_PERCENTAGE, self._config.max_voltage
            )
            self.schedule_update_ha_state()

        async_dispatcher_connect(self.hass, SIGNAL_XBEE_FRAME_RECEIVED, handle_frame)

    @property
    def name(self):
        """Return the name of the input."""
        return self._config.name

    @property
    def config(self):
        """Return the entity's configuration."""
        return self._config

    @property
    def should_poll(self):
        """Return the polling state, if needed."""
        return self._config.should_poll

    @property
    def sensor_state(self):
        """Return the state of the entity."""
        return self._value

    def update(self):
        """Get the latest reading from the ADC."""
        try:
            self._value = self._device.read_analog_pin(
                self._config.pin,
                self._config.max_voltage,
                self._config.address,
                xb_const.ADC_PERCENTAGE,
            )
        except ZigBeeTxFailure:
            _LOGGER.warning(
                "Transmission failure when attempting to get sample from "
                "Zigbee device at address: %s",
                hexlify(self._config.address),
            )
        except ZigBeeException as exc:
            _LOGGER.exception("Unable to get sample from Zigbee device: %s", exc)
