"""Test zha fan."""
from unittest.mock import AsyncMock, call, patch

import pytest
from zigpy.exceptions import ZigbeeException
import zigpy.profiles.zha as zha
import zigpy.zcl.clusters.general as general
import zigpy.zcl.clusters.hvac as hvac
import zigpy.zcl.foundation as zcl_f

from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    ATTR_PRESET_MODE,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PERCENTAGE,
    SERVICE_SET_PRESET_MODE,
    NotValidPresetModeError,
)
from homeassistant.components.zha.core.discovery import GROUP_PROBE
from homeassistant.components.zha.core.group import GroupMember
from homeassistant.components.zha.fan import (
    PRESET_MODE_AUTO,
    PRESET_MODE_ON,
    PRESET_MODE_SMART,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    Platform,
)
from homeassistant.setup import async_setup_component

from .common import (
    async_enable_traffic,
    async_find_group_entity_id,
    async_test_rejoin,
    find_entity_id,
    get_zha_gateway,
    send_attributes_report,
)
from .conftest import SIG_EP_INPUT, SIG_EP_OUTPUT, SIG_EP_PROFILE, SIG_EP_TYPE

from tests.components.zha.common import async_wait_for_updates

IEEE_GROUPABLE_DEVICE = "01:2d:6f:00:0a:90:69:e8"
IEEE_GROUPABLE_DEVICE2 = "02:2d:6f:00:0a:90:69:e8"


@pytest.fixture
def zigpy_device(zigpy_device_mock):
    """Device tracker zigpy device."""
    endpoints = {
        1: {
            SIG_EP_INPUT: [hvac.Fan.cluster_id],
            SIG_EP_OUTPUT: [],
            SIG_EP_TYPE: zha.DeviceType.ON_OFF_SWITCH,
            SIG_EP_PROFILE: zha.PROFILE_ID,
        }
    }
    return zigpy_device_mock(
        endpoints, node_descriptor=b"\x02@\x8c\x02\x10RR\x00\x00\x00R\x00\x00"
    )


@pytest.fixture
async def coordinator(hass, zigpy_device_mock, zha_device_joined):
    """Test zha fan platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [general.Groups.cluster_id],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.COLOR_DIMMABLE_LIGHT,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            }
        },
        ieee="00:15:8d:00:02:32:4f:32",
        nwk=0x0000,
        node_descriptor=b"\xf8\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff",
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    return zha_device


@pytest.fixture
async def device_fan_1(hass, zigpy_device_mock, zha_device_joined):
    """Test zha fan platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [
                    general.Groups.cluster_id,
                    general.OnOff.cluster_id,
                    hvac.Fan.cluster_id,
                ],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.ON_OFF_LIGHT,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            },
        },
        ieee=IEEE_GROUPABLE_DEVICE,
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    await hass.async_block_till_done()
    return zha_device


@pytest.fixture
async def device_fan_2(hass, zigpy_device_mock, zha_device_joined):
    """Test zha fan platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [
                    general.Groups.cluster_id,
                    general.OnOff.cluster_id,
                    hvac.Fan.cluster_id,
                    general.LevelControl.cluster_id,
                ],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.ON_OFF_LIGHT,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            },
        },
        ieee=IEEE_GROUPABLE_DEVICE2,
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    await hass.async_block_till_done()
    return zha_device


async def test_fan(hass, zha_device_joined_restored, zigpy_device):
    """Test zha fan platform."""

    zha_device = await zha_device_joined_restored(zigpy_device)
    cluster = zigpy_device.endpoints.get(1).fan
    entity_id = await find_entity_id(Platform.FAN, zha_device, hass)
    assert entity_id is not None

    assert hass.states.get(entity_id).state == STATE_OFF
    await async_enable_traffic(hass, [zha_device], enabled=False)
    # test that the fan was created and that it is unavailable
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [zha_device])

    # test that the state has changed from unavailable to off
    assert hass.states.get(entity_id).state == STATE_OFF

    # turn on at fan
    await send_attributes_report(hass, cluster, {1: 2, 0: 1, 2: 3})
    assert hass.states.get(entity_id).state == STATE_ON

    # turn off at fan
    await send_attributes_report(hass, cluster, {1: 1, 0: 0, 2: 2})
    assert hass.states.get(entity_id).state == STATE_OFF

    # turn on from HA
    cluster.write_attributes.reset_mock()
    await async_turn_on(hass, entity_id)
    assert len(cluster.write_attributes.mock_calls) == 1
    assert cluster.write_attributes.call_args == call({"fan_mode": 2})

    # turn off from HA
    cluster.write_attributes.reset_mock()
    await async_turn_off(hass, entity_id)
    assert len(cluster.write_attributes.mock_calls) == 1
    assert cluster.write_attributes.call_args == call({"fan_mode": 0})

    # change speed from HA
    cluster.write_attributes.reset_mock()
    await async_set_percentage(hass, entity_id, percentage=100)
    assert len(cluster.write_attributes.mock_calls) == 1
    assert cluster.write_attributes.call_args == call({"fan_mode": 3})

    # change preset_mode from HA
    cluster.write_attributes.reset_mock()
    await async_set_preset_mode(hass, entity_id, preset_mode=PRESET_MODE_ON)
    assert len(cluster.write_attributes.mock_calls) == 1
    assert cluster.write_attributes.call_args == call({"fan_mode": 4})

    # set invalid preset_mode from HA
    cluster.write_attributes.reset_mock()
    with pytest.raises(NotValidPresetModeError):
        await async_set_preset_mode(
            hass, entity_id, preset_mode="invalid does not exist"
        )
    assert len(cluster.write_attributes.mock_calls) == 0

    # test adding new fan to the network and HA
    await async_test_rejoin(hass, zigpy_device, [cluster], (1,))


async def async_turn_on(hass, entity_id, percentage=None):
    """Turn fan on."""
    data = {
        key: value
        for key, value in [(ATTR_ENTITY_ID, entity_id), (ATTR_PERCENTAGE, percentage)]
        if value is not None
    }

    await hass.services.async_call(Platform.FAN, SERVICE_TURN_ON, data, blocking=True)


async def async_turn_off(hass, entity_id):
    """Turn fan off."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}

    await hass.services.async_call(Platform.FAN, SERVICE_TURN_OFF, data, blocking=True)


async def async_set_percentage(hass, entity_id, percentage=None):
    """Set percentage for specified fan."""
    data = {
        key: value
        for key, value in [(ATTR_ENTITY_ID, entity_id), (ATTR_PERCENTAGE, percentage)]
        if value is not None
    }

    await hass.services.async_call(
        Platform.FAN, SERVICE_SET_PERCENTAGE, data, blocking=True
    )


async def async_set_preset_mode(hass, entity_id, preset_mode=None):
    """Set preset_mode for specified fan."""
    data = {
        key: value
        for key, value in [(ATTR_ENTITY_ID, entity_id), (ATTR_PRESET_MODE, preset_mode)]
        if value is not None
    }

    await hass.services.async_call(
        FAN_DOMAIN, SERVICE_SET_PRESET_MODE, data, blocking=True
    )


@patch(
    "zigpy.zcl.clusters.hvac.Fan.write_attributes",
    new=AsyncMock(return_value=zcl_f.WriteAttributesResponse.deserialize(b"\x00")[0]),
)
@patch(
    "homeassistant.components.zha.entity.UPDATE_GROUP_FROM_CHILD_DELAY",
    new=0,
)
async def test_zha_group_fan_entity(hass, device_fan_1, device_fan_2, coordinator):
    """Test the fan entity for a ZHA group."""
    zha_gateway = get_zha_gateway(hass)
    assert zha_gateway is not None
    zha_gateway.coordinator_zha_device = coordinator
    coordinator._zha_gateway = zha_gateway
    device_fan_1._zha_gateway = zha_gateway
    device_fan_2._zha_gateway = zha_gateway
    member_ieee_addresses = [device_fan_1.ieee, device_fan_2.ieee]
    members = [GroupMember(device_fan_1.ieee, 1), GroupMember(device_fan_2.ieee, 1)]

    # test creating a group with 2 members
    zha_group = await zha_gateway.async_create_zigpy_group("Test Group", members)
    await hass.async_block_till_done()

    assert zha_group is not None
    assert len(zha_group.members) == 2
    for member in zha_group.members:
        assert member.device.ieee in member_ieee_addresses
        assert member.group == zha_group
        assert member.endpoint is not None

    entity_domains = GROUP_PROBE.determine_entity_domains(hass, zha_group)
    assert len(entity_domains) == 2

    assert Platform.LIGHT in entity_domains
    assert Platform.FAN in entity_domains

    entity_id = async_find_group_entity_id(hass, Platform.FAN, zha_group)
    assert hass.states.get(entity_id) is not None

    group_fan_cluster = zha_group.endpoint[hvac.Fan.cluster_id]

    dev1_fan_cluster = device_fan_1.device.endpoints[1].fan
    dev2_fan_cluster = device_fan_2.device.endpoints[1].fan

    await async_enable_traffic(hass, [device_fan_1, device_fan_2], enabled=False)
    await async_wait_for_updates(hass)
    # test that the fans were created and that they are unavailable
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [device_fan_1, device_fan_2])
    await async_wait_for_updates(hass)
    # test that the fan group entity was created and is off
    assert hass.states.get(entity_id).state == STATE_OFF

    # turn on from HA
    group_fan_cluster.write_attributes.reset_mock()
    await async_turn_on(hass, entity_id)
    await hass.async_block_till_done()
    assert len(group_fan_cluster.write_attributes.mock_calls) == 1
    assert group_fan_cluster.write_attributes.call_args[0][0] == {"fan_mode": 2}

    # turn off from HA
    group_fan_cluster.write_attributes.reset_mock()
    await async_turn_off(hass, entity_id)
    assert len(group_fan_cluster.write_attributes.mock_calls) == 1
    assert group_fan_cluster.write_attributes.call_args[0][0] == {"fan_mode": 0}

    # change speed from HA
    group_fan_cluster.write_attributes.reset_mock()
    await async_set_percentage(hass, entity_id, percentage=100)
    assert len(group_fan_cluster.write_attributes.mock_calls) == 1
    assert group_fan_cluster.write_attributes.call_args[0][0] == {"fan_mode": 3}

    # change preset mode from HA
    group_fan_cluster.write_attributes.reset_mock()
    await async_set_preset_mode(hass, entity_id, preset_mode=PRESET_MODE_ON)
    assert len(group_fan_cluster.write_attributes.mock_calls) == 1
    assert group_fan_cluster.write_attributes.call_args[0][0] == {"fan_mode": 4}

    # change preset mode from HA
    group_fan_cluster.write_attributes.reset_mock()
    await async_set_preset_mode(hass, entity_id, preset_mode=PRESET_MODE_AUTO)
    assert len(group_fan_cluster.write_attributes.mock_calls) == 1
    assert group_fan_cluster.write_attributes.call_args[0][0] == {"fan_mode": 5}

    # change preset mode from HA
    group_fan_cluster.write_attributes.reset_mock()
    await async_set_preset_mode(hass, entity_id, preset_mode=PRESET_MODE_SMART)
    assert len(group_fan_cluster.write_attributes.mock_calls) == 1
    assert group_fan_cluster.write_attributes.call_args[0][0] == {"fan_mode": 6}

    # test some of the group logic to make sure we key off states correctly
    await send_attributes_report(hass, dev1_fan_cluster, {0: 0})
    await send_attributes_report(hass, dev2_fan_cluster, {0: 0})

    # test that group fan is off
    assert hass.states.get(entity_id).state == STATE_OFF

    await send_attributes_report(hass, dev2_fan_cluster, {0: 2})
    await async_wait_for_updates(hass)

    # test that group fan is speed medium
    assert hass.states.get(entity_id).state == STATE_ON

    await send_attributes_report(hass, dev2_fan_cluster, {0: 0})
    await async_wait_for_updates(hass)

    # test that group fan is now off
    assert hass.states.get(entity_id).state == STATE_OFF


@patch(
    "zigpy.zcl.clusters.hvac.Fan.write_attributes",
    new=AsyncMock(side_effect=ZigbeeException),
)
@patch(
    "homeassistant.components.zha.entity.UPDATE_GROUP_FROM_CHILD_DELAY",
    new=0,
)
async def test_zha_group_fan_entity_failure_state(
    hass, device_fan_1, device_fan_2, coordinator, caplog
):
    """Test the fan entity for a ZHA group when writing attributes generates an exception."""
    zha_gateway = get_zha_gateway(hass)
    assert zha_gateway is not None
    zha_gateway.coordinator_zha_device = coordinator
    coordinator._zha_gateway = zha_gateway
    device_fan_1._zha_gateway = zha_gateway
    device_fan_2._zha_gateway = zha_gateway
    member_ieee_addresses = [device_fan_1.ieee, device_fan_2.ieee]
    members = [GroupMember(device_fan_1.ieee, 1), GroupMember(device_fan_2.ieee, 1)]

    # test creating a group with 2 members
    zha_group = await zha_gateway.async_create_zigpy_group("Test Group", members)
    await hass.async_block_till_done()

    assert zha_group is not None
    assert len(zha_group.members) == 2
    for member in zha_group.members:
        assert member.device.ieee in member_ieee_addresses
        assert member.group == zha_group
        assert member.endpoint is not None

    entity_domains = GROUP_PROBE.determine_entity_domains(hass, zha_group)
    assert len(entity_domains) == 2

    assert Platform.LIGHT in entity_domains
    assert Platform.FAN in entity_domains

    entity_id = async_find_group_entity_id(hass, Platform.FAN, zha_group)
    assert hass.states.get(entity_id) is not None

    group_fan_cluster = zha_group.endpoint[hvac.Fan.cluster_id]

    await async_enable_traffic(hass, [device_fan_1, device_fan_2], enabled=False)
    await async_wait_for_updates(hass)
    # test that the fans were created and that they are unavailable
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [device_fan_1, device_fan_2])
    await async_wait_for_updates(hass)
    # test that the fan group entity was created and is off
    assert hass.states.get(entity_id).state == STATE_OFF

    # turn on from HA
    group_fan_cluster.write_attributes.reset_mock()
    await async_turn_on(hass, entity_id)
    await hass.async_block_till_done()
    assert len(group_fan_cluster.write_attributes.mock_calls) == 1
    assert group_fan_cluster.write_attributes.call_args[0][0] == {"fan_mode": 2}

    assert "Could not set fan mode" in caplog.text


@pytest.mark.parametrize(
    "plug_read, expected_state, expected_percentage",
    (
        (None, STATE_OFF, None),
        ({"fan_mode": 0}, STATE_OFF, 0),
        ({"fan_mode": 1}, STATE_ON, 33),
        ({"fan_mode": 2}, STATE_ON, 66),
        ({"fan_mode": 3}, STATE_ON, 100),
    ),
)
async def test_fan_init(
    hass,
    zha_device_joined_restored,
    zigpy_device,
    plug_read,
    expected_state,
    expected_percentage,
):
    """Test zha fan platform."""

    cluster = zigpy_device.endpoints.get(1).fan
    cluster.PLUGGED_ATTR_READS = plug_read

    zha_device = await zha_device_joined_restored(zigpy_device)
    entity_id = await find_entity_id(Platform.FAN, zha_device, hass)
    assert entity_id is not None
    assert hass.states.get(entity_id).state == expected_state
    assert hass.states.get(entity_id).attributes[ATTR_PERCENTAGE] == expected_percentage
    assert hass.states.get(entity_id).attributes[ATTR_PRESET_MODE] is None


async def test_fan_update_entity(
    hass,
    zha_device_joined_restored,
    zigpy_device,
):
    """Test zha fan platform."""

    cluster = zigpy_device.endpoints.get(1).fan
    cluster.PLUGGED_ATTR_READS = {"fan_mode": 0}

    zha_device = await zha_device_joined_restored(zigpy_device)
    entity_id = await find_entity_id(Platform.FAN, zha_device, hass)
    assert entity_id is not None
    assert hass.states.get(entity_id).state == STATE_OFF
    assert hass.states.get(entity_id).attributes[ATTR_PERCENTAGE] == 0
    assert hass.states.get(entity_id).attributes[ATTR_PRESET_MODE] is None
    assert hass.states.get(entity_id).attributes[ATTR_PERCENTAGE_STEP] == 100 / 3
    assert cluster.read_attributes.await_count == 2

    await async_setup_component(hass, "homeassistant", {})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": entity_id}, blocking=True
    )
    assert hass.states.get(entity_id).state == STATE_OFF
    assert cluster.read_attributes.await_count == 3

    cluster.PLUGGED_ATTR_READS = {"fan_mode": 1}
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": entity_id}, blocking=True
    )
    assert hass.states.get(entity_id).state == STATE_ON
    assert hass.states.get(entity_id).attributes[ATTR_PERCENTAGE] == 33
    assert hass.states.get(entity_id).attributes[ATTR_PRESET_MODE] is None
    assert hass.states.get(entity_id).attributes[ATTR_PERCENTAGE_STEP] == 100 / 3
    assert cluster.read_attributes.await_count == 4
