"""Test zha light."""
from datetime import timedelta
from unittest.mock import AsyncMock, call, patch, sentinel

import pytest
import zigpy.profiles.zha as zha
import zigpy.zcl.clusters.general as general
import zigpy.zcl.clusters.lighting as lighting
import zigpy.zcl.foundation as zcl_f

from homeassistant.components.light import (
    DOMAIN as LIGHT_DOMAIN,
    FLASH_LONG,
    FLASH_SHORT,
)
from homeassistant.components.zha.core.group import GroupMember
from homeassistant.components.zha.light import FLASH_EFFECTS
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, Platform
import homeassistant.util.dt as dt_util

from .common import (
    async_enable_traffic,
    async_find_group_entity_id,
    async_test_rejoin,
    find_entity_id,
    get_zha_gateway,
    send_attributes_report,
)
from .conftest import SIG_EP_INPUT, SIG_EP_OUTPUT, SIG_EP_PROFILE, SIG_EP_TYPE

from tests.common import async_fire_time_changed
from tests.components.zha.common import async_wait_for_updates

ON = 1
OFF = 0
IEEE_GROUPABLE_DEVICE = "01:2d:6f:00:0a:90:69:e8"
IEEE_GROUPABLE_DEVICE2 = "02:2d:6f:00:0a:90:69:e9"
IEEE_GROUPABLE_DEVICE3 = "03:2d:6f:00:0a:90:69:e7"

LIGHT_ON_OFF = {
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
}

LIGHT_LEVEL = {
    1: {
        SIG_EP_PROFILE: zha.PROFILE_ID,
        SIG_EP_TYPE: zha.DeviceType.DIMMABLE_LIGHT,
        SIG_EP_INPUT: [
            general.Basic.cluster_id,
            general.LevelControl.cluster_id,
            general.OnOff.cluster_id,
        ],
        SIG_EP_OUTPUT: [general.Ota.cluster_id],
    }
}

LIGHT_COLOR = {
    1: {
        SIG_EP_PROFILE: zha.PROFILE_ID,
        SIG_EP_TYPE: zha.DeviceType.COLOR_DIMMABLE_LIGHT,
        SIG_EP_INPUT: [
            general.Basic.cluster_id,
            general.Identify.cluster_id,
            general.LevelControl.cluster_id,
            general.OnOff.cluster_id,
            lighting.Color.cluster_id,
        ],
        SIG_EP_OUTPUT: [general.Ota.cluster_id],
    }
}


@pytest.fixture
async def coordinator(hass, zigpy_device_mock, zha_device_joined):
    """Test zha light platform."""

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
async def device_light_1(hass, zigpy_device_mock, zha_device_joined):
    """Test zha light platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [
                    general.OnOff.cluster_id,
                    general.LevelControl.cluster_id,
                    lighting.Color.cluster_id,
                    general.Groups.cluster_id,
                    general.Identify.cluster_id,
                ],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.COLOR_DIMMABLE_LIGHT,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            }
        },
        ieee=IEEE_GROUPABLE_DEVICE,
        nwk=0xB79D,
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    return zha_device


@pytest.fixture
async def device_light_2(hass, zigpy_device_mock, zha_device_joined):
    """Test zha light platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [
                    general.OnOff.cluster_id,
                    general.LevelControl.cluster_id,
                    lighting.Color.cluster_id,
                    general.Groups.cluster_id,
                    general.Identify.cluster_id,
                ],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.COLOR_DIMMABLE_LIGHT,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            }
        },
        ieee=IEEE_GROUPABLE_DEVICE2,
        nwk=0xC79E,
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    return zha_device


@pytest.fixture
async def device_light_3(hass, zigpy_device_mock, zha_device_joined):
    """Test zha light platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [
                    general.OnOff.cluster_id,
                    general.LevelControl.cluster_id,
                    lighting.Color.cluster_id,
                    general.Groups.cluster_id,
                    general.Identify.cluster_id,
                ],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.COLOR_DIMMABLE_LIGHT,
                SIG_EP_PROFILE: zha.PROFILE_ID,
            }
        },
        ieee=IEEE_GROUPABLE_DEVICE3,
        nwk=0xB89F,
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    return zha_device


async def test_light_refresh(hass, zigpy_device_mock, zha_device_joined_restored):
    """Test zha light platform refresh."""

    # create zigpy devices
    zigpy_device = zigpy_device_mock(LIGHT_ON_OFF)
    on_off_cluster = zigpy_device.endpoints[1].on_off
    on_off_cluster.PLUGGED_ATTR_READS = {"on_off": 0}
    zha_device = await zha_device_joined_restored(zigpy_device)
    entity_id = await find_entity_id(Platform.LIGHT, zha_device, hass)

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [zha_device])
    on_off_cluster.read_attributes.reset_mock()

    # not enough time passed
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=20))
    await hass.async_block_till_done()
    assert on_off_cluster.read_attributes.call_count == 0
    assert on_off_cluster.read_attributes.await_count == 0
    assert hass.states.get(entity_id).state == STATE_OFF

    # 1 interval - 1 call
    on_off_cluster.PLUGGED_ATTR_READS = {"on_off": 1}
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=80))
    await hass.async_block_till_done()
    assert on_off_cluster.read_attributes.call_count == 1
    assert on_off_cluster.read_attributes.await_count == 1
    assert hass.states.get(entity_id).state == STATE_ON

    # 2 intervals - 2 calls
    on_off_cluster.PLUGGED_ATTR_READS = {"on_off": 0}
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=80))
    await hass.async_block_till_done()
    assert on_off_cluster.read_attributes.call_count == 2
    assert on_off_cluster.read_attributes.await_count == 2
    assert hass.states.get(entity_id).state == STATE_OFF


@patch(
    "zigpy.zcl.clusters.lighting.Color.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@patch(
    "zigpy.zcl.clusters.general.Identify.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@patch(
    "zigpy.zcl.clusters.general.LevelControl.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@patch(
    "zigpy.zcl.clusters.general.OnOff.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@pytest.mark.parametrize(
    "device, reporting",
    [(LIGHT_ON_OFF, (1, 0, 0)), (LIGHT_LEVEL, (1, 1, 0)), (LIGHT_COLOR, (1, 1, 3))],
)
async def test_light(
    hass, zigpy_device_mock, zha_device_joined_restored, device, reporting
):
    """Test zha light platform."""

    # create zigpy devices
    zigpy_device = zigpy_device_mock(device)
    zha_device = await zha_device_joined_restored(zigpy_device)
    entity_id = await find_entity_id(Platform.LIGHT, zha_device, hass)

    assert entity_id is not None

    cluster_on_off = zigpy_device.endpoints[1].on_off
    cluster_level = getattr(zigpy_device.endpoints[1], "level", None)
    cluster_color = getattr(zigpy_device.endpoints[1], "light_color", None)
    cluster_identify = getattr(zigpy_device.endpoints[1], "identify", None)

    assert hass.states.get(entity_id).state == STATE_OFF
    await async_enable_traffic(hass, [zha_device], enabled=False)
    # test that the lights were created and that they are unavailable
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [zha_device])

    # test that the lights were created and are off
    assert hass.states.get(entity_id).state == STATE_OFF

    # test turning the lights on and off from the light
    await async_test_on_off_from_light(hass, cluster_on_off, entity_id)

    # test turning the lights on and off from the HA
    await async_test_on_off_from_hass(hass, cluster_on_off, entity_id)

    # test short flashing the lights from the HA
    if cluster_identify:
        await async_test_flash_from_hass(hass, cluster_identify, entity_id, FLASH_SHORT)

    # test turning the lights on and off from the HA
    if cluster_level:
        await async_test_level_on_off_from_hass(
            hass, cluster_on_off, cluster_level, entity_id
        )

        # test getting a brightness change from the network
        await async_test_on_from_light(hass, cluster_on_off, entity_id)
        await async_test_dimmer_from_light(
            hass, cluster_level, entity_id, 150, STATE_ON
        )

    # test rejoin
    await async_test_off_from_hass(hass, cluster_on_off, entity_id)
    clusters = [cluster_on_off]
    if cluster_level:
        clusters.append(cluster_level)
    if cluster_color:
        clusters.append(cluster_color)
    await async_test_rejoin(hass, zigpy_device, clusters, reporting)

    # test long flashing the lights from the HA
    if cluster_identify:
        await async_test_flash_from_hass(hass, cluster_identify, entity_id, FLASH_LONG)


async def async_test_on_off_from_light(hass, cluster, entity_id):
    """Test on off functionality from the light."""
    # turn on at light
    await send_attributes_report(hass, cluster, {1: 0, 0: 1, 2: 3})
    await async_wait_for_updates(hass)
    assert hass.states.get(entity_id).state == STATE_ON

    # turn off at light
    await send_attributes_report(hass, cluster, {1: 1, 0: 0, 2: 3})
    await async_wait_for_updates(hass)
    assert hass.states.get(entity_id).state == STATE_OFF


async def async_test_on_from_light(hass, cluster, entity_id):
    """Test on off functionality from the light."""
    # turn on at light
    await send_attributes_report(hass, cluster, {1: -1, 0: 1, 2: 2})
    await async_wait_for_updates(hass)
    assert hass.states.get(entity_id).state == STATE_ON


async def async_test_on_off_from_hass(hass, cluster, entity_id):
    """Test on off functionality from hass."""
    # turn on via UI
    cluster.request.reset_mock()
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_on", {"entity_id": entity_id}, blocking=True
    )
    assert cluster.request.call_count == 1
    assert cluster.request.await_count == 1
    assert cluster.request.call_args == call(
        False,
        ON,
        cluster.commands_by_name["on"].schema,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=None,
    )

    await async_test_off_from_hass(hass, cluster, entity_id)


async def async_test_off_from_hass(hass, cluster, entity_id):
    """Test turning off the light from Home Assistant."""

    # turn off via UI
    cluster.request.reset_mock()
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {"entity_id": entity_id}, blocking=True
    )
    assert cluster.request.call_count == 1
    assert cluster.request.await_count == 1
    assert cluster.request.call_args == call(
        False,
        OFF,
        cluster.commands_by_name["off"].schema,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=None,
    )


async def async_test_level_on_off_from_hass(
    hass, on_off_cluster, level_cluster, entity_id
):
    """Test on off functionality from hass."""

    on_off_cluster.request.reset_mock()
    level_cluster.request.reset_mock()
    # turn on via UI
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_on", {"entity_id": entity_id}, blocking=True
    )
    assert on_off_cluster.request.call_count == 1
    assert on_off_cluster.request.await_count == 1
    assert level_cluster.request.call_count == 0
    assert level_cluster.request.await_count == 0
    assert on_off_cluster.request.call_args == call(
        False,
        ON,
        on_off_cluster.commands_by_name["on"].schema,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=None,
    )
    on_off_cluster.request.reset_mock()
    level_cluster.request.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {"entity_id": entity_id, "transition": 10},
        blocking=True,
    )
    assert on_off_cluster.request.call_count == 1
    assert on_off_cluster.request.await_count == 1
    assert level_cluster.request.call_count == 1
    assert level_cluster.request.await_count == 1
    assert on_off_cluster.request.call_args == call(
        False,
        ON,
        on_off_cluster.commands_by_name["on"].schema,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=None,
    )
    assert level_cluster.request.call_args == call(
        False,
        4,
        level_cluster.commands_by_name["move_to_level_with_on_off"].schema,
        254,
        100.0,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=None,
    )
    on_off_cluster.request.reset_mock()
    level_cluster.request.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {"entity_id": entity_id, "brightness": 10},
        blocking=True,
    )
    # the onoff cluster is now not used when brightness is present by default
    assert on_off_cluster.request.call_count == 0
    assert on_off_cluster.request.await_count == 0
    assert level_cluster.request.call_count == 1
    assert level_cluster.request.await_count == 1
    assert level_cluster.request.call_args == call(
        False,
        4,
        level_cluster.commands_by_name["move_to_level_with_on_off"].schema,
        10,
        1,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=None,
    )
    on_off_cluster.request.reset_mock()
    level_cluster.request.reset_mock()

    await async_test_off_from_hass(hass, on_off_cluster, entity_id)


async def async_test_dimmer_from_light(hass, cluster, entity_id, level, expected_state):
    """Test dimmer functionality from the light."""

    await send_attributes_report(
        hass, cluster, {1: level + 10, 0: level, 2: level - 10 or 22}
    )
    await async_wait_for_updates(hass)
    assert hass.states.get(entity_id).state == expected_state
    # hass uses None for brightness of 0 in state attributes
    if level == 0:
        level = None
    assert hass.states.get(entity_id).attributes.get("brightness") == level


async def async_test_flash_from_hass(hass, cluster, entity_id, flash):
    """Test flash functionality from hass."""
    # turn on via UI
    cluster.request.reset_mock()
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {"entity_id": entity_id, "flash": flash},
        blocking=True,
    )
    assert cluster.request.call_count == 1
    assert cluster.request.await_count == 1
    assert cluster.request.call_args == call(
        False,
        64,
        cluster.commands_by_name["trigger_effect"].schema,
        FLASH_EFFECTS[flash],
        0,
        expect_reply=True,
        manufacturer=None,
        tries=1,
        tsn=None,
    )


@patch(
    "zigpy.zcl.clusters.lighting.Color.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@patch(
    "zigpy.zcl.clusters.general.Identify.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@patch(
    "zigpy.zcl.clusters.general.LevelControl.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@patch(
    "zigpy.zcl.clusters.general.OnOff.request",
    new=AsyncMock(return_value=[sentinel.data, zcl_f.Status.SUCCESS]),
)
@patch(
    "homeassistant.components.zha.entity.UPDATE_GROUP_FROM_CHILD_DELAY",
    new=0,
)
async def test_zha_group_light_entity(
    hass, device_light_1, device_light_2, device_light_3, coordinator
):
    """Test the light entity for a ZHA group."""
    zha_gateway = get_zha_gateway(hass)
    assert zha_gateway is not None
    zha_gateway.coordinator_zha_device = coordinator
    coordinator._zha_gateway = zha_gateway
    device_light_1._zha_gateway = zha_gateway
    device_light_2._zha_gateway = zha_gateway
    member_ieee_addresses = [device_light_1.ieee, device_light_2.ieee]
    members = [GroupMember(device_light_1.ieee, 1), GroupMember(device_light_2.ieee, 1)]

    assert coordinator.is_coordinator

    # test creating a group with 2 members
    zha_group = await zha_gateway.async_create_zigpy_group("Test Group", members)
    await hass.async_block_till_done()

    assert zha_group is not None
    assert len(zha_group.members) == 2
    for member in zha_group.members:
        assert member.device.ieee in member_ieee_addresses
        assert member.group == zha_group
        assert member.endpoint is not None

    device_1_entity_id = await find_entity_id(Platform.LIGHT, device_light_1, hass)
    device_2_entity_id = await find_entity_id(Platform.LIGHT, device_light_2, hass)
    device_3_entity_id = await find_entity_id(Platform.LIGHT, device_light_3, hass)

    assert (
        device_1_entity_id != device_2_entity_id
        and device_1_entity_id != device_3_entity_id
    )
    assert device_2_entity_id != device_3_entity_id

    group_entity_id = async_find_group_entity_id(hass, Platform.LIGHT, zha_group)
    assert hass.states.get(group_entity_id) is not None

    assert device_1_entity_id in zha_group.member_entity_ids
    assert device_2_entity_id in zha_group.member_entity_ids
    assert device_3_entity_id not in zha_group.member_entity_ids

    group_cluster_on_off = zha_group.endpoint[general.OnOff.cluster_id]
    group_cluster_level = zha_group.endpoint[general.LevelControl.cluster_id]
    group_cluster_identify = zha_group.endpoint[general.Identify.cluster_id]

    dev1_cluster_on_off = device_light_1.device.endpoints[1].on_off
    dev2_cluster_on_off = device_light_2.device.endpoints[1].on_off
    dev3_cluster_on_off = device_light_3.device.endpoints[1].on_off

    dev1_cluster_level = device_light_1.device.endpoints[1].level

    await async_enable_traffic(
        hass, [device_light_1, device_light_2, device_light_3], enabled=False
    )
    await async_wait_for_updates(hass)
    # test that the lights were created and that they are unavailable
    assert hass.states.get(group_entity_id).state == STATE_UNAVAILABLE

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [device_light_1, device_light_2, device_light_3])
    await async_wait_for_updates(hass)

    # test that the lights were created and are off
    assert hass.states.get(group_entity_id).state == STATE_OFF

    # test turning the lights on and off from the HA
    await async_test_on_off_from_hass(hass, group_cluster_on_off, group_entity_id)

    # test short flashing the lights from the HA
    await async_test_flash_from_hass(
        hass, group_cluster_identify, group_entity_id, FLASH_SHORT
    )

    # test turning the lights on and off from the light
    await async_test_on_off_from_light(hass, dev1_cluster_on_off, group_entity_id)

    # test turning the lights on and off from the HA
    await async_test_level_on_off_from_hass(
        hass, group_cluster_on_off, group_cluster_level, group_entity_id
    )

    # test getting a brightness change from the network
    await async_test_on_from_light(hass, dev1_cluster_on_off, group_entity_id)
    await async_test_dimmer_from_light(
        hass, dev1_cluster_level, group_entity_id, 150, STATE_ON
    )

    # test long flashing the lights from the HA
    await async_test_flash_from_hass(
        hass, group_cluster_identify, group_entity_id, FLASH_LONG
    )

    assert len(zha_group.members) == 2
    # test some of the group logic to make sure we key off states correctly
    await send_attributes_report(hass, dev1_cluster_on_off, {0: 1})
    await send_attributes_report(hass, dev2_cluster_on_off, {0: 1})
    await hass.async_block_till_done()

    # test that group light is on
    assert hass.states.get(device_1_entity_id).state == STATE_ON
    assert hass.states.get(device_2_entity_id).state == STATE_ON
    assert hass.states.get(group_entity_id).state == STATE_ON

    await send_attributes_report(hass, dev1_cluster_on_off, {0: 0})
    await hass.async_block_till_done()

    # test that group light is still on
    assert hass.states.get(device_1_entity_id).state == STATE_OFF
    assert hass.states.get(device_2_entity_id).state == STATE_ON
    assert hass.states.get(group_entity_id).state == STATE_ON

    await send_attributes_report(hass, dev2_cluster_on_off, {0: 0})
    await async_wait_for_updates(hass)

    # test that group light is now off
    assert hass.states.get(device_1_entity_id).state == STATE_OFF
    assert hass.states.get(device_2_entity_id).state == STATE_OFF
    assert hass.states.get(group_entity_id).state == STATE_OFF

    await send_attributes_report(hass, dev1_cluster_on_off, {0: 1})
    await async_wait_for_updates(hass)

    # test that group light is now back on
    assert hass.states.get(device_1_entity_id).state == STATE_ON
    assert hass.states.get(device_2_entity_id).state == STATE_OFF
    assert hass.states.get(group_entity_id).state == STATE_ON

    # turn it off to test a new member add being tracked
    await send_attributes_report(hass, dev1_cluster_on_off, {0: 0})
    await async_wait_for_updates(hass)
    assert hass.states.get(device_1_entity_id).state == STATE_OFF
    assert hass.states.get(device_2_entity_id).state == STATE_OFF
    assert hass.states.get(group_entity_id).state == STATE_OFF

    # add a new member and test that his state is also tracked
    await zha_group.async_add_members([GroupMember(device_light_3.ieee, 1)])
    await send_attributes_report(hass, dev3_cluster_on_off, {0: 1})
    await async_wait_for_updates(hass)
    assert device_3_entity_id in zha_group.member_entity_ids
    assert len(zha_group.members) == 3

    assert hass.states.get(device_1_entity_id).state == STATE_OFF
    assert hass.states.get(device_2_entity_id).state == STATE_OFF
    assert hass.states.get(device_3_entity_id).state == STATE_ON
    assert hass.states.get(group_entity_id).state == STATE_ON

    # make the group have only 1 member and now there should be no entity
    await zha_group.async_remove_members(
        [GroupMember(device_light_2.ieee, 1), GroupMember(device_light_3.ieee, 1)]
    )
    assert len(zha_group.members) == 1
    assert hass.states.get(group_entity_id) is None
    assert device_2_entity_id not in zha_group.member_entity_ids
    assert device_3_entity_id not in zha_group.member_entity_ids

    # make sure the entity registry entry is still there
    assert zha_gateway.ha_entity_registry.async_get(group_entity_id) is not None

    # add a member back and ensure that the group entity was created again
    await zha_group.async_add_members([GroupMember(device_light_3.ieee, 1)])
    await send_attributes_report(hass, dev3_cluster_on_off, {0: 1})
    await async_wait_for_updates(hass)
    assert len(zha_group.members) == 2
    assert hass.states.get(group_entity_id).state == STATE_ON

    # add a 3rd member and ensure we still have an entity and we track the new one
    await send_attributes_report(hass, dev1_cluster_on_off, {0: 0})
    await send_attributes_report(hass, dev3_cluster_on_off, {0: 0})
    await async_wait_for_updates(hass)
    assert hass.states.get(group_entity_id).state == STATE_OFF

    # this will test that _reprobe_group is used correctly
    await zha_group.async_add_members(
        [GroupMember(device_light_2.ieee, 1), GroupMember(coordinator.ieee, 1)]
    )
    await send_attributes_report(hass, dev2_cluster_on_off, {0: 1})
    await async_wait_for_updates(hass)
    assert len(zha_group.members) == 4
    assert hass.states.get(group_entity_id).state == STATE_ON

    await zha_group.async_remove_members([GroupMember(coordinator.ieee, 1)])
    await hass.async_block_till_done()
    assert hass.states.get(group_entity_id).state == STATE_ON
    assert len(zha_group.members) == 3

    # remove the group and ensure that there is no entity and that the entity registry is cleaned up
    assert zha_gateway.ha_entity_registry.async_get(group_entity_id) is not None
    await zha_gateway.async_remove_zigpy_group(zha_group.group_id)
    assert hass.states.get(group_entity_id) is None
    assert zha_gateway.ha_entity_registry.async_get(group_entity_id) is None
