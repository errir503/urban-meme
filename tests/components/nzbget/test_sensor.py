"""Test the NZBGet sensors."""
from datetime import timedelta
from unittest.mock import patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    DATA_MEGABYTES,
    DATA_RATE_MEGABYTES_PER_SECOND,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import init_integration


async def test_sensors(hass, nzbget_api) -> None:
    """Test the creation and values of the sensors."""
    now = dt_util.utcnow().replace(microsecond=0)
    with patch("homeassistant.components.nzbget.sensor.utcnow", return_value=now):
        entry = await init_integration(hass)

    registry = er.async_get(hass)

    uptime = now - timedelta(seconds=600)

    sensors = {
        "article_cache": ("ArticleCacheMB", "64", DATA_MEGABYTES, None),
        "average_speed": (
            "AverageDownloadRate",
            "1.19",
            DATA_RATE_MEGABYTES_PER_SECOND,
            None,
        ),
        "download_paused": ("DownloadPaused", "False", None, None),
        "speed": ("DownloadRate", "2.38", DATA_RATE_MEGABYTES_PER_SECOND, None),
        "size": ("DownloadedSizeMB", "256", DATA_MEGABYTES, None),
        "disk_free": ("FreeDiskSpaceMB", "1024", DATA_MEGABYTES, None),
        "post_processing_jobs": ("PostJobCount", "2", "Jobs", None),
        "post_processing_paused": ("PostPaused", "False", None, None),
        "queue_size": ("RemainingSizeMB", "512", DATA_MEGABYTES, None),
        "uptime": ("UpTimeSec", uptime.isoformat(), None, SensorDeviceClass.TIMESTAMP),
        "speed_limit": (
            "DownloadLimit",
            "0.95",
            DATA_RATE_MEGABYTES_PER_SECOND,
            None,
        ),
    }

    for (sensor_id, data) in sensors.items():
        entity_entry = registry.async_get(f"sensor.nzbgettest_{sensor_id}")
        assert entity_entry
        assert entity_entry.original_device_class == data[3]
        assert entity_entry.unique_id == f"{entry.entry_id}_{data[0]}"

        state = hass.states.get(f"sensor.nzbgettest_{sensor_id}")
        assert state
        assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == data[2]
        assert state.state == data[1]
