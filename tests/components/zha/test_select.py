"""Test ZHA select entities."""
from unittest.mock import call, patch

import pytest
from zhaquirks import (
    DEVICE_TYPE,
    ENDPOINTS,
    INPUT_CLUSTERS,
    OUTPUT_CLUSTERS,
    PROFILE_ID,
)
from zigpy.const import SIG_EP_PROFILE
import zigpy.profiles.zha as zha
from zigpy.quirks import CustomCluster, CustomDevice
import zigpy.types as t
import zigpy.zcl.clusters.general as general
from zigpy.zcl.clusters.manufacturer_specific import ManufacturerSpecificCluster
import zigpy.zcl.clusters.security as security

from homeassistant.components.zha.select import AqaraMotionSensitivities
from homeassistant.const import STATE_UNKNOWN, EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, restore_state
from homeassistant.util import dt as dt_util

from .common import async_enable_traffic, find_entity_id, send_attributes_report
from .conftest import SIG_EP_INPUT, SIG_EP_OUTPUT, SIG_EP_TYPE


@pytest.fixture(autouse=True)
def select_select_only():
    """Only set up the select and required base platforms to speed up tests."""
    with patch(
        "homeassistant.components.zha.PLATFORMS",
        (
            Platform.BUTTON,
            Platform.DEVICE_TRACKER,
            Platform.SIREN,
            Platform.LIGHT,
            Platform.NUMBER,
            Platform.SELECT,
            Platform.SENSOR,
            Platform.SWITCH,
        ),
    ):
        yield


@pytest.fixture
async def siren(hass, zigpy_device_mock, zha_device_joined_restored):
    """Siren fixture."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [general.Basic.cluster_id, security.IasWd.cluster_id],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.IAS_WARNING_DEVICE,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            }
        },
    )

    zha_device = await zha_device_joined_restored(zigpy_device)
    return zha_device, zigpy_device.endpoints[1].ias_wd


@pytest.fixture
async def light(hass, zigpy_device_mock):
    """Siren fixture."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_PROFILE: zha.PROFILE_ID,
                SIG_EP_TYPE: zha.DeviceType.ON_OFF_LIGHT,
                SIG_EP_INPUT: [
                    general.Basic.cluster_id,
                    general.Identify.cluster_id,
                    general.OnOff.cluster_id,
                ],
                SIG_EP_OUTPUT: [general.Ota.cluster_id],
            }
        },
        node_descriptor=b"\x02@\x84_\x11\x7fd\x00\x00,d\x00\x00",
    )

    return zigpy_device


@pytest.fixture
def core_rs(hass_storage):
    """Core.restore_state fixture."""

    def _storage(entity_id, state):
        now = dt_util.utcnow().isoformat()

        hass_storage[restore_state.STORAGE_KEY] = {
            "version": restore_state.STORAGE_VERSION,
            "key": restore_state.STORAGE_KEY,
            "data": [
                {
                    "state": {
                        "entity_id": entity_id,
                        "state": str(state),
                        "last_changed": now,
                        "last_updated": now,
                        "context": {
                            "id": "3c2243ff5f30447eb12e7348cfd5b8ff",
                            "user_id": None,
                        },
                    },
                    "last_seen": now,
                }
            ],
        }
        return

    return _storage


async def test_select(hass: HomeAssistant, siren) -> None:
    """Test ZHA select platform."""

    entity_registry = er.async_get(hass)
    zha_device, cluster = siren
    assert cluster is not None
    entity_id = await find_entity_id(
        Platform.SELECT,
        zha_device,
        hass,
        qualifier="tone",
    )
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_UNKNOWN
    assert state.attributes["options"] == [
        "Stop",
        "Burglar",
        "Fire",
        "Emergency",
        "Police Panic",
        "Fire Panic",
        "Emergency Panic",
    ]

    entity_entry = entity_registry.async_get(entity_id)
    assert entity_entry
    assert entity_entry.entity_category == EntityCategory.CONFIG

    # Test select option with string value
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": entity_id,
            "option": security.IasWd.Warning.WarningMode.Burglar.name,
        },
        blocking=True,
    )

    state = hass.states.get(entity_id)
    assert state
    assert state.state == security.IasWd.Warning.WarningMode.Burglar.name


async def test_select_restore_state(
    hass: HomeAssistant,
    zigpy_device_mock,
    core_rs,
    zha_device_restored,
) -> None:
    """Test ZHA select entity restore state."""

    entity_id = "select.fakemanufacturer_fakemodel_default_siren_tone"
    core_rs(entity_id, state="Burglar")

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [general.Basic.cluster_id, security.IasWd.cluster_id],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.IAS_WARNING_DEVICE,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            }
        },
    )

    zha_device = await zha_device_restored(zigpy_device)
    cluster = zigpy_device.endpoints[1].ias_wd
    assert cluster is not None
    entity_id = await find_entity_id(
        Platform.SELECT,
        zha_device,
        hass,
        qualifier="tone",
    )

    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state
    assert state.state == security.IasWd.Warning.WarningMode.Burglar.name


async def test_on_off_select_new_join(
    hass: HomeAssistant, light, zha_device_joined
) -> None:
    """Test ZHA on off select - new join."""

    entity_registry = er.async_get(hass)
    on_off_cluster = light.endpoints[1].on_off
    on_off_cluster.PLUGGED_ATTR_READS = {
        "start_up_on_off": general.OnOff.StartUpOnOff.On
    }
    zha_device = await zha_device_joined(light)
    select_name = "start_up_behavior"
    entity_id = await find_entity_id(
        Platform.SELECT,
        zha_device,
        hass,
        qualifier=select_name,
    )
    assert entity_id is not None

    assert on_off_cluster.read_attributes.call_count == 2
    assert (
        call(["start_up_on_off"], allow_cache=True, only_cache=False, manufacturer=None)
        in on_off_cluster.read_attributes.call_args_list
    )
    assert (
        call(["on_off"], allow_cache=False, only_cache=False, manufacturer=None)
        in on_off_cluster.read_attributes.call_args_list
    )

    state = hass.states.get(entity_id)
    assert state
    assert state.state == general.OnOff.StartUpOnOff.On.name

    assert state.attributes["options"] == ["Off", "On", "Toggle", "PreviousValue"]

    entity_entry = entity_registry.async_get(entity_id)
    assert entity_entry
    assert entity_entry.entity_category == EntityCategory.CONFIG

    # Test select option with string value
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": entity_id,
            "option": general.OnOff.StartUpOnOff.Off.name,
        },
        blocking=True,
    )

    assert on_off_cluster.write_attributes.call_count == 1
    assert on_off_cluster.write_attributes.call_args[0][0] == {
        "start_up_on_off": general.OnOff.StartUpOnOff.Off
    }

    state = hass.states.get(entity_id)
    assert state
    assert state.state == general.OnOff.StartUpOnOff.Off.name


async def test_on_off_select_restored(
    hass: HomeAssistant, light, zha_device_restored
) -> None:
    """Test ZHA on off select - restored."""

    entity_registry = er.async_get(hass)
    on_off_cluster = light.endpoints[1].on_off
    on_off_cluster.PLUGGED_ATTR_READS = {
        "start_up_on_off": general.OnOff.StartUpOnOff.On
    }
    zha_device = await zha_device_restored(light)

    assert zha_device.is_mains_powered

    assert on_off_cluster.read_attributes.call_count == 4
    # first 2 calls hit cache only
    assert (
        call(["start_up_on_off"], allow_cache=True, only_cache=True, manufacturer=None)
        in on_off_cluster.read_attributes.call_args_list
    )
    assert (
        call(["on_off"], allow_cache=True, only_cache=True, manufacturer=None)
        in on_off_cluster.read_attributes.call_args_list
    )

    # 2nd set of calls can actually read from the device
    assert (
        call(["start_up_on_off"], allow_cache=True, only_cache=False, manufacturer=None)
        in on_off_cluster.read_attributes.call_args_list
    )
    assert (
        call(["on_off"], allow_cache=False, only_cache=False, manufacturer=None)
        in on_off_cluster.read_attributes.call_args_list
    )

    select_name = "start_up_behavior"
    entity_id = await find_entity_id(
        Platform.SELECT,
        zha_device,
        hass,
        qualifier=select_name,
    )
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state
    assert state.state == general.OnOff.StartUpOnOff.On.name
    assert state.attributes["options"] == ["Off", "On", "Toggle", "PreviousValue"]

    entity_entry = entity_registry.async_get(entity_id)
    assert entity_entry
    assert entity_entry.entity_category == EntityCategory.CONFIG


async def test_on_off_select_unsupported(
    hass: HomeAssistant, light, zha_device_joined_restored
) -> None:
    """Test ZHA on off select unsupported."""

    on_off_cluster = light.endpoints[1].on_off
    on_off_cluster.add_unsupported_attribute("start_up_on_off")
    zha_device = await zha_device_joined_restored(light)
    select_name = general.OnOff.StartUpOnOff.__name__
    entity_id = await find_entity_id(
        Platform.SELECT,
        zha_device,
        hass,
        qualifier=select_name.lower(),
    )
    assert entity_id is None


class MotionSensitivityQuirk(CustomDevice):
    """Quirk with motion sensitivity attribute."""

    class OppleCluster(CustomCluster, ManufacturerSpecificCluster):
        """Aqara manufacturer specific cluster."""

        cluster_id = 0xFCC0
        ep_attribute = "opple_cluster"
        attributes = {
            0x010C: ("motion_sensitivity", t.uint8_t, True),
        }

        def __init__(self, *args, **kwargs):
            """Initialize."""
            super().__init__(*args, **kwargs)
            # populate cache to create config entity
            self._attr_cache.update({0x010C: AqaraMotionSensitivities.Medium})

    replacement = {
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.OCCUPANCY_SENSOR,
                INPUT_CLUSTERS: [general.Basic.cluster_id, OppleCluster],
                OUTPUT_CLUSTERS: [],
            },
        }
    }


@pytest.fixture
async def zigpy_device_aqara_sensor(hass, zigpy_device_mock, zha_device_joined):
    """Device tracker zigpy Aqara motion sensor device."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [general.Basic.cluster_id],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.OCCUPANCY_SENSOR,
            }
        },
        manufacturer="LUMI",
        model="lumi.motion.ac02",
        quirk=MotionSensitivityQuirk,
    )

    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    await hass.async_block_till_done()
    return zigpy_device


async def test_on_off_select_attribute_report(
    hass: HomeAssistant, light, zha_device_restored, zigpy_device_aqara_sensor
) -> None:
    """Test ZHA attribute report parsing for select platform."""

    zha_device = await zha_device_restored(zigpy_device_aqara_sensor)
    cluster = zigpy_device_aqara_sensor.endpoints.get(1).opple_cluster
    entity_id = await find_entity_id(Platform.SELECT, zha_device, hass)
    assert entity_id is not None

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [zha_device])

    # test that the state is in default medium state
    assert hass.states.get(entity_id).state == AqaraMotionSensitivities.Medium.name

    # send attribute report from device
    await send_attributes_report(
        hass, cluster, {"motion_sensitivity": AqaraMotionSensitivities.Low}
    )
    assert hass.states.get(entity_id).state == AqaraMotionSensitivities.Low.name
