"""Test for the alarm control panel const module."""

from types import ModuleType

import pytest

from homeassistant.components import alarm_control_panel

from tests.common import import_and_test_deprecated_constant_enum


@pytest.mark.parametrize(
    "code_format",
    list(alarm_control_panel.CodeFormat),
)
@pytest.mark.parametrize(
    "module",
    [alarm_control_panel, alarm_control_panel.const],
)
def test_deprecated_constant_code_format(
    caplog: pytest.LogCaptureFixture,
    code_format: alarm_control_panel.CodeFormat,
    module: ModuleType,
) -> None:
    """Test deprecated format constants."""
    import_and_test_deprecated_constant_enum(
        caplog, module, code_format, "FORMAT_", "2025.1"
    )


@pytest.mark.parametrize(
    "entity_feature",
    list(alarm_control_panel.AlarmControlPanelEntityFeature),
)
@pytest.mark.parametrize(
    "module",
    [alarm_control_panel, alarm_control_panel.const],
)
def test_deprecated_support_alarm_constants(
    caplog: pytest.LogCaptureFixture,
    entity_feature: alarm_control_panel.AlarmControlPanelEntityFeature,
    module: ModuleType,
) -> None:
    """Test deprecated support alarm constants."""
    import_and_test_deprecated_constant_enum(
        caplog, module, entity_feature, "SUPPORT_ALARM_", "2025.1"
    )
