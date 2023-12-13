"""Tests for the Sun WEG server config flow."""
from copy import deepcopy
from unittest.mock import patch

from sunweg.api import APIHelper

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.sunweg.const import CONF_PLANT_ID, DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .common import FIXTURE_USER_INPUT, SUNWEG_LOGIN_RESPONSE, SUNWEG_PLANT_RESPONSE

from tests.common import MockConfigEntry


async def test_show_authenticate_form(hass: HomeAssistant) -> None:
    """Test that the setup form is served."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_incorrect_login(hass: HomeAssistant) -> None:
    """Test that it shows the appropriate error when an incorrect username/password/server is entered."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch.object(APIHelper, "authenticate", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], FIXTURE_USER_INPUT
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_no_plants_on_account(hass: HomeAssistant) -> None:
    """Test registering an integration and finishing flow with an entered plant_id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = FIXTURE_USER_INPUT.copy()

    with patch.object(
        APIHelper, "authenticate", return_value=SUNWEG_LOGIN_RESPONSE
    ), patch.object(APIHelper, "listPlants", return_value=[]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] == "abort"
    assert result["reason"] == "no_plants"


async def test_multiple_plant_ids(hass: HomeAssistant) -> None:
    """Test registering an integration and finishing flow with an entered plant_id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = FIXTURE_USER_INPUT.copy()
    plant_list = [deepcopy(SUNWEG_PLANT_RESPONSE), deepcopy(SUNWEG_PLANT_RESPONSE)]

    with patch.object(
        APIHelper, "authenticate", return_value=SUNWEG_LOGIN_RESPONSE
    ), patch.object(APIHelper, "listPlants", return_value=plant_list):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "plant"

        user_input = {CONF_PLANT_ID: 123456}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == FIXTURE_USER_INPUT[CONF_USERNAME]
    assert result["data"][CONF_PASSWORD] == FIXTURE_USER_INPUT[CONF_PASSWORD]
    assert result["data"][CONF_PLANT_ID] == 123456


async def test_one_plant_on_account(hass: HomeAssistant) -> None:
    """Test registering an integration and finishing flow with an entered plant_id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = FIXTURE_USER_INPUT.copy()

    with patch.object(
        APIHelper, "authenticate", return_value=SUNWEG_LOGIN_RESPONSE
    ), patch.object(
        APIHelper,
        "listPlants",
        return_value=[deepcopy(SUNWEG_PLANT_RESPONSE)],
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == FIXTURE_USER_INPUT[CONF_USERNAME]
    assert result["data"][CONF_PASSWORD] == FIXTURE_USER_INPUT[CONF_PASSWORD]
    assert result["data"][CONF_PLANT_ID] == 123456


async def test_existing_plant_configured(hass: HomeAssistant) -> None:
    """Test entering an existing plant_id."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=123456)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = FIXTURE_USER_INPUT.copy()

    with patch.object(
        APIHelper, "authenticate", return_value=SUNWEG_LOGIN_RESPONSE
    ), patch.object(
        APIHelper,
        "listPlants",
        return_value=[deepcopy(SUNWEG_PLANT_RESPONSE)],
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
