"""Test zha switch."""
from unittest.mock import call, patch

import pytest
import zigpy.profiles.zha as zha
import zigpy.zcl.clusters.general as general
import zigpy.zcl.foundation as zcl_f

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.zha.core.group import GroupMember
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, Platform

from .common import (
    async_enable_traffic,
    async_find_group_entity_id,
    async_test_rejoin,
    find_entity_id,
    get_zha_gateway,
    send_attributes_report,
)
from .conftest import SIG_EP_INPUT, SIG_EP_OUTPUT, SIG_EP_TYPE

from tests.common import mock_coro
from tests.components.zha.common import async_wait_for_updates

ON = 1
OFF = 0
IEEE_GROUPABLE_DEVICE = "01:2d:6f:00:0a:90:69:e8"
IEEE_GROUPABLE_DEVICE2 = "02:2d:6f:00:0a:90:69:e8"


@pytest.fixture
def zigpy_device(zigpy_device_mock):
    """Device tracker zigpy device."""
    endpoints = {
        1: {
            SIG_EP_INPUT: [general.Basic.cluster_id, general.OnOff.cluster_id],
            SIG_EP_OUTPUT: [],
            SIG_EP_TYPE: zha.DeviceType.ON_OFF_SWITCH,
        }
    }
    return zigpy_device_mock(endpoints)


@pytest.fixture
async def coordinator(hass, zigpy_device_mock, zha_device_joined):
    """Test zha light platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.COLOR_DIMMABLE_LIGHT,
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
async def device_switch_1(hass, zigpy_device_mock, zha_device_joined):
    """Test zha switch platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [general.OnOff.cluster_id, general.Groups.cluster_id],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.ON_OFF_SWITCH,
            }
        },
        ieee=IEEE_GROUPABLE_DEVICE,
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    await hass.async_block_till_done()
    return zha_device


@pytest.fixture
async def device_switch_2(hass, zigpy_device_mock, zha_device_joined):
    """Test zha switch platform."""

    zigpy_device = zigpy_device_mock(
        {
            1: {
                SIG_EP_INPUT: [general.OnOff.cluster_id, general.Groups.cluster_id],
                SIG_EP_OUTPUT: [],
                SIG_EP_TYPE: zha.DeviceType.ON_OFF_SWITCH,
            }
        },
        ieee=IEEE_GROUPABLE_DEVICE2,
    )
    zha_device = await zha_device_joined(zigpy_device)
    zha_device.available = True
    await hass.async_block_till_done()
    return zha_device


async def test_switch(hass, zha_device_joined_restored, zigpy_device):
    """Test zha switch platform."""

    zha_device = await zha_device_joined_restored(zigpy_device)
    cluster = zigpy_device.endpoints.get(1).on_off
    entity_id = await find_entity_id(Platform.SWITCH, zha_device, hass)
    assert entity_id is not None

    assert hass.states.get(entity_id).state == STATE_OFF
    await async_enable_traffic(hass, [zha_device], enabled=False)
    # test that the switch was created and that its state is unavailable
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [zha_device])

    # test that the state has changed from unavailable to off
    assert hass.states.get(entity_id).state == STATE_OFF

    # turn on at switch
    await send_attributes_report(hass, cluster, {1: 0, 0: 1, 2: 2})
    assert hass.states.get(entity_id).state == STATE_ON

    # turn off at switch
    await send_attributes_report(hass, cluster, {1: 1, 0: 0, 2: 2})
    assert hass.states.get(entity_id).state == STATE_OFF

    # turn on from HA
    with patch(
        "zigpy.zcl.Cluster.request",
        return_value=mock_coro([0x00, zcl_f.Status.SUCCESS]),
    ):
        # turn on via UI
        await hass.services.async_call(
            SWITCH_DOMAIN, "turn_on", {"entity_id": entity_id}, blocking=True
        )
        assert len(cluster.request.mock_calls) == 1
        assert cluster.request.call_args == call(
            False,
            ON,
            cluster.commands_by_name["on"].schema,
            expect_reply=True,
            manufacturer=None,
            tries=1,
            tsn=None,
        )

    # turn off from HA
    with patch(
        "zigpy.zcl.Cluster.request",
        return_value=mock_coro([0x01, zcl_f.Status.SUCCESS]),
    ):
        # turn off via UI
        await hass.services.async_call(
            SWITCH_DOMAIN, "turn_off", {"entity_id": entity_id}, blocking=True
        )
        assert len(cluster.request.mock_calls) == 1
        assert cluster.request.call_args == call(
            False,
            OFF,
            cluster.commands_by_name["off"].schema,
            expect_reply=True,
            manufacturer=None,
            tries=1,
            tsn=None,
        )

    # test joining a new switch to the network and HA
    await async_test_rejoin(hass, zigpy_device, [cluster], (1,))


@patch(
    "homeassistant.components.zha.entity.UPDATE_GROUP_FROM_CHILD_DELAY",
    new=0,
)
async def test_zha_group_switch_entity(
    hass, device_switch_1, device_switch_2, coordinator
):
    """Test the switch entity for a ZHA group."""
    zha_gateway = get_zha_gateway(hass)
    assert zha_gateway is not None
    zha_gateway.coordinator_zha_device = coordinator
    coordinator._zha_gateway = zha_gateway
    device_switch_1._zha_gateway = zha_gateway
    device_switch_2._zha_gateway = zha_gateway
    member_ieee_addresses = [device_switch_1.ieee, device_switch_2.ieee]
    members = [
        GroupMember(device_switch_1.ieee, 1),
        GroupMember(device_switch_2.ieee, 1),
    ]

    # test creating a group with 2 members
    zha_group = await zha_gateway.async_create_zigpy_group("Test Group", members)
    await hass.async_block_till_done()

    assert zha_group is not None
    assert len(zha_group.members) == 2
    for member in zha_group.members:
        assert member.device.ieee in member_ieee_addresses
        assert member.group == zha_group
        assert member.endpoint is not None

    entity_id = async_find_group_entity_id(hass, Platform.SWITCH, zha_group)
    assert hass.states.get(entity_id) is not None

    group_cluster_on_off = zha_group.endpoint[general.OnOff.cluster_id]
    dev1_cluster_on_off = device_switch_1.device.endpoints[1].on_off
    dev2_cluster_on_off = device_switch_2.device.endpoints[1].on_off

    await async_enable_traffic(hass, [device_switch_1, device_switch_2], enabled=False)
    await async_wait_for_updates(hass)

    # test that the lights were created and that they are off
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # allow traffic to flow through the gateway and device
    await async_enable_traffic(hass, [device_switch_1, device_switch_2])
    await async_wait_for_updates(hass)

    # test that the lights were created and are off
    assert hass.states.get(entity_id).state == STATE_OFF

    # turn on from HA
    with patch(
        "zigpy.zcl.Cluster.request",
        return_value=mock_coro([0x00, zcl_f.Status.SUCCESS]),
    ):
        # turn on via UI
        await hass.services.async_call(
            SWITCH_DOMAIN, "turn_on", {"entity_id": entity_id}, blocking=True
        )
        assert len(group_cluster_on_off.request.mock_calls) == 1
        assert group_cluster_on_off.request.call_args == call(
            False,
            ON,
            group_cluster_on_off.commands_by_name["on"].schema,
            expect_reply=True,
            manufacturer=None,
            tries=1,
            tsn=None,
        )
    assert hass.states.get(entity_id).state == STATE_ON

    # turn off from HA
    with patch(
        "zigpy.zcl.Cluster.request",
        return_value=mock_coro([0x01, zcl_f.Status.SUCCESS]),
    ):
        # turn off via UI
        await hass.services.async_call(
            SWITCH_DOMAIN, "turn_off", {"entity_id": entity_id}, blocking=True
        )
        assert len(group_cluster_on_off.request.mock_calls) == 1
        assert group_cluster_on_off.request.call_args == call(
            False,
            OFF,
            group_cluster_on_off.commands_by_name["off"].schema,
            expect_reply=True,
            manufacturer=None,
            tries=1,
            tsn=None,
        )
    assert hass.states.get(entity_id).state == STATE_OFF

    # test some of the group logic to make sure we key off states correctly
    await send_attributes_report(hass, dev1_cluster_on_off, {0: 1})
    await send_attributes_report(hass, dev2_cluster_on_off, {0: 1})
    await async_wait_for_updates(hass)

    # test that group light is on
    assert hass.states.get(entity_id).state == STATE_ON

    await send_attributes_report(hass, dev1_cluster_on_off, {0: 0})
    await async_wait_for_updates(hass)

    # test that group light is still on
    assert hass.states.get(entity_id).state == STATE_ON

    await send_attributes_report(hass, dev2_cluster_on_off, {0: 0})
    await async_wait_for_updates(hass)

    # test that group light is now off
    assert hass.states.get(entity_id).state == STATE_OFF

    await send_attributes_report(hass, dev1_cluster_on_off, {0: 1})
    await async_wait_for_updates(hass)

    # test that group light is now back on
    assert hass.states.get(entity_id).state == STATE_ON
