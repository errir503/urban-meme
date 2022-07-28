"""Test the Xiaomi config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.components.xiaomi_ble.const import DOMAIN
from homeassistant.data_entry_flow import FlowResultType

from . import (
    JTYJGD03MI_SERVICE_INFO,
    LYWSDCGQ_SERVICE_INFO,
    MMC_T201_1_SERVICE_INFO,
    NOT_SENSOR_PUSH_SERVICE_INFO,
    YLKG07YL_SERVICE_INFO,
)

from tests.common import MockConfigEntry


async def test_async_step_bluetooth_valid_device(hass):
    """Test discovery via bluetooth with a valid device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=MMC_T201_1_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "MMC_T201_1"
    assert result2["data"] == {}
    assert result2["result"].unique_id == "00:81:F9:DD:6F:C1"


async def test_async_step_bluetooth_during_onboarding(hass):
    """Test discovery via bluetooth during onboarding."""
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ) as mock_setup_entry, patch(
        "homeassistant.components.onboarding.async_is_onboarded",
        return_value=False,
    ) as mock_onboarding:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=MMC_T201_1_SERVICE_INFO,
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "MMC_T201_1"
    assert result["data"] == {}
    assert result["result"].unique_id == "00:81:F9:DD:6F:C1"
    assert len(mock_setup_entry.mock_calls) == 1
    assert len(mock_onboarding.mock_calls) == 1


async def test_async_step_bluetooth_valid_device_legacy_encryption(hass):
    """Test discovery via bluetooth with a valid device, with legacy encryption."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=YLKG07YL_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "get_encryption_key_legacy"

    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "b853075158487ca39a5b5ea9"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "YLKG07YL"
    assert result2["data"] == {"bindkey": "b853075158487ca39a5b5ea9"}
    assert result2["result"].unique_id == "F8:24:41:C5:98:8B"


async def test_async_step_bluetooth_valid_device_legacy_encryption_wrong_key(hass):
    """Test discovery via bluetooth with a valid device, with legacy encryption and invalid key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=YLKG07YL_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "get_encryption_key_legacy"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "aaaaaaaaaaaaaaaaaaaaaaaa"},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_legacy"
    assert result2["errors"]["bindkey"] == "decryption_failed"

    # Test can finish flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "b853075158487ca39a5b5ea9"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "YLKG07YL"
    assert result2["data"] == {"bindkey": "b853075158487ca39a5b5ea9"}
    assert result2["result"].unique_id == "F8:24:41:C5:98:8B"


async def test_async_step_bluetooth_valid_device_legacy_encryption_wrong_key_length(
    hass,
):
    """Test discovery via bluetooth with a valid device, with legacy encryption and wrong key length."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=YLKG07YL_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "get_encryption_key_legacy"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "aaaaaaaaaaaaaaaaaaaaaaa"},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_legacy"
    assert result2["errors"]["bindkey"] == "expected_24_characters"

    # Test can finish flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "b853075158487ca39a5b5ea9"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "YLKG07YL"
    assert result2["data"] == {"bindkey": "b853075158487ca39a5b5ea9"}
    assert result2["result"].unique_id == "F8:24:41:C5:98:8B"


async def test_async_step_bluetooth_valid_device_v4_encryption(hass):
    """Test discovery via bluetooth with a valid device, with v4 encryption."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=JTYJGD03MI_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "get_encryption_key_4_5"

    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "JTYJGD03MI"
    assert result2["data"] == {"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"}
    assert result2["result"].unique_id == "54:EF:44:E3:9C:BC"


async def test_async_step_bluetooth_valid_device_v4_encryption_wrong_key(hass):
    """Test discovery via bluetooth with a valid device, with v4 encryption and wrong key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=JTYJGD03MI_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "get_encryption_key_4_5"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_4_5"
    assert result2["errors"]["bindkey"] == "decryption_failed"

    # Test can finish flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "JTYJGD03MI"
    assert result2["data"] == {"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"}
    assert result2["result"].unique_id == "54:EF:44:E3:9C:BC"


async def test_async_step_bluetooth_valid_device_v4_encryption_wrong_key_length(hass):
    """Test discovery via bluetooth with a valid device, with v4 encryption and wrong key length."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=JTYJGD03MI_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "get_encryption_key_4_5"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "5b51a7c91cde6707c9ef18fda143a58"},
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_4_5"
    assert result2["errors"]["bindkey"] == "expected_32_characters"

    # Test can finish flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "JTYJGD03MI"
    assert result2["data"] == {"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"}
    assert result2["result"].unique_id == "54:EF:44:E3:9C:BC"


async def test_async_step_bluetooth_not_xiaomi(hass):
    """Test discovery via bluetooth not xiaomi."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=NOT_SENSOR_PUSH_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_async_step_user_no_devices_found(hass):
    """Test setup from service info cache with no devices found."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_async_step_user_with_found_devices(hass):
    """Test setup from service info cache with devices found."""
    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[LYWSDCGQ_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"address": "58:2D:34:35:93:21"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "LYWSDCGQ"
    assert result2["data"] == {}
    assert result2["result"].unique_id == "58:2D:34:35:93:21"


async def test_async_step_user_with_found_devices_v4_encryption(hass):
    """Test setup from service info cache with devices found, with v4 encryption."""
    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[JTYJGD03MI_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result1 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"address": "54:EF:44:E3:9C:BC"},
    )
    assert result1["type"] == FlowResultType.FORM
    assert result1["step_id"] == "get_encryption_key_4_5"

    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "JTYJGD03MI"
    assert result2["data"] == {"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"}
    assert result2["result"].unique_id == "54:EF:44:E3:9C:BC"


async def test_async_step_user_with_found_devices_v4_encryption_wrong_key(hass):
    """Test setup from service info cache with devices found, with v4 encryption and wrong key."""
    # Get a list of devices
    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[JTYJGD03MI_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Pick a device
    result1 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"address": "54:EF:44:E3:9C:BC"},
    )
    assert result1["type"] == FlowResultType.FORM
    assert result1["step_id"] == "get_encryption_key_4_5"

    # Try an incorrect key
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_4_5"
    assert result2["errors"]["bindkey"] == "decryption_failed"

    # Check can still finish flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "JTYJGD03MI"
    assert result2["data"] == {"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"}
    assert result2["result"].unique_id == "54:EF:44:E3:9C:BC"


async def test_async_step_user_with_found_devices_v4_encryption_wrong_key_length(hass):
    """Test setup from service info cache with devices found, with v4 encryption and wrong key length."""
    # Get a list of devices
    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[JTYJGD03MI_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Select a single device
    result1 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"address": "54:EF:44:E3:9C:BC"},
    )
    assert result1["type"] == FlowResultType.FORM
    assert result1["step_id"] == "get_encryption_key_4_5"

    # Try an incorrect key
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "5b51a7c91cde6707c9ef1dfda143a58"},
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_4_5"
    assert result2["errors"]["bindkey"] == "expected_32_characters"

    # Check can still finish flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "JTYJGD03MI"
    assert result2["data"] == {"bindkey": "5b51a7c91cde6707c9ef18dfda143a58"}
    assert result2["result"].unique_id == "54:EF:44:E3:9C:BC"


async def test_async_step_user_with_found_devices_legacy_encryption(hass):
    """Test setup from service info cache with devices found, with legacy encryption."""
    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[YLKG07YL_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result1 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"address": "F8:24:41:C5:98:8B"},
    )
    assert result1["type"] == FlowResultType.FORM
    assert result1["step_id"] == "get_encryption_key_legacy"

    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "b853075158487ca39a5b5ea9"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "YLKG07YL"
    assert result2["data"] == {"bindkey": "b853075158487ca39a5b5ea9"}
    assert result2["result"].unique_id == "F8:24:41:C5:98:8B"


async def test_async_step_user_with_found_devices_legacy_encryption_wrong_key(
    hass,
):
    """Test setup from service info cache with devices found, with legacy encryption and wrong key."""
    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[YLKG07YL_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result1 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"address": "F8:24:41:C5:98:8B"},
    )
    assert result1["type"] == FlowResultType.FORM
    assert result1["step_id"] == "get_encryption_key_legacy"

    # Enter an incorrect code
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "aaaaaaaaaaaaaaaaaaaaaaaa"},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_legacy"
    assert result2["errors"]["bindkey"] == "decryption_failed"

    # Check you can finish the flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "b853075158487ca39a5b5ea9"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "YLKG07YL"
    assert result2["data"] == {"bindkey": "b853075158487ca39a5b5ea9"}
    assert result2["result"].unique_id == "F8:24:41:C5:98:8B"


async def test_async_step_user_with_found_devices_legacy_encryption_wrong_key_length(
    hass,
):
    """Test setup from service info cache with devices found, with legacy encryption and wrong key length."""
    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[YLKG07YL_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result1 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"address": "F8:24:41:C5:98:8B"},
    )
    assert result1["type"] == FlowResultType.FORM
    assert result1["step_id"] == "get_encryption_key_legacy"

    # Enter an incorrect code
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"bindkey": "b85307518487ca39a5b5ea9"},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "get_encryption_key_legacy"
    assert result2["errors"]["bindkey"] == "expected_24_characters"

    # Check you can finish the flow
    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bindkey": "b853075158487ca39a5b5ea9"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "YLKG07YL"
    assert result2["data"] == {"bindkey": "b853075158487ca39a5b5ea9"}
    assert result2["result"].unique_id == "F8:24:41:C5:98:8B"


async def test_async_step_user_with_found_devices_already_setup(hass):
    """Test setup from service info cache with devices found."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="58:2D:34:35:93:21",
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[LYWSDCGQ_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_async_step_bluetooth_devices_already_setup(hass):
    """Test we can't start a flow if there is already a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="00:81:F9:DD:6F:C1",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=MMC_T201_1_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_async_step_bluetooth_already_in_progress(hass):
    """Test we can't start a flow for the same device twice."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=MMC_T201_1_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=MMC_T201_1_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


async def test_async_step_user_takes_precedence_over_discovery(hass):
    """Test manual setup takes precedence over discovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=MMC_T201_1_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    with patch(
        "homeassistant.components.xiaomi_ble.config_flow.async_discovered_service_info",
        return_value=[MMC_T201_1_SERVICE_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        assert result["type"] == FlowResultType.FORM

    with patch(
        "homeassistant.components.xiaomi_ble.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"address": "00:81:F9:DD:6F:C1"},
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "MMC_T201_1"
    assert result2["data"] == {}
    assert result2["result"].unique_id == "00:81:F9:DD:6F:C1"

    # Verify the original one was aborted
    assert not hass.config_entries.flow.async_progress(DOMAIN)
