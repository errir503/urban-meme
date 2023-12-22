"""The tests for the humidifier component."""
from enum import Enum
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from homeassistant.components import humidifier
from homeassistant.components.humidifier import HumidifierEntity
from homeassistant.core import HomeAssistant

from tests.common import import_and_test_deprecated_constant_enum


class MockHumidifierEntity(HumidifierEntity):
    """Mock Humidifier device to use in tests."""

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return 0


async def test_sync_turn_on(hass: HomeAssistant) -> None:
    """Test if async turn_on calls sync turn_on."""
    humidifier = MockHumidifierEntity()
    humidifier.hass = hass

    humidifier.turn_on = MagicMock()
    await humidifier.async_turn_on()

    assert humidifier.turn_on.called


async def test_sync_turn_off(hass: HomeAssistant) -> None:
    """Test if async turn_off calls sync turn_off."""
    humidifier = MockHumidifierEntity()
    humidifier.hass = hass

    humidifier.turn_off = MagicMock()
    await humidifier.async_turn_off()

    assert humidifier.turn_off.called


def _create_tuples(enum: Enum, constant_prefix: str) -> list[tuple[Enum, str]]:
    result = []
    for enum in enum:
        result.append((enum, constant_prefix))
    return result


@pytest.mark.parametrize(
    ("enum", "constant_prefix"),
    _create_tuples(humidifier.HumidifierEntityFeature, "SUPPORT_")
    + _create_tuples(humidifier.HumidifierDeviceClass, "DEVICE_CLASS_"),
)
@pytest.mark.parametrize(("module"), [humidifier, humidifier.const])
def test_deprecated_constants(
    caplog: pytest.LogCaptureFixture,
    enum: Enum,
    constant_prefix: str,
    module: ModuleType,
) -> None:
    """Test deprecated constants."""
    import_and_test_deprecated_constant_enum(
        caplog, module, enum, constant_prefix, "2025.1"
    )
