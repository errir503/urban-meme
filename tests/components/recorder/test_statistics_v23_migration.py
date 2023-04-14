"""The tests for sensor recorder platform migrating statistics from v23.

The v23 schema used for these tests has been slightly modified to add the
EventData table to allow the recorder to startup successfully.
"""
from functools import partial

# pylint: disable=invalid-name
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from homeassistant.components import recorder
from homeassistant.components.recorder import SQLITE_URL_PREFIX
from homeassistant.components.recorder.util import session_scope
from homeassistant.helpers import recorder as recorder_helper
from homeassistant.setup import setup_component
import homeassistant.util.dt as dt_util

from .common import (
    CREATE_ENGINE_TARGET,
    create_engine_test_for_schema_version_postfix,
    get_schema_module_path,
    wait_recording_done,
)

from tests.common import get_test_home_assistant

ORIG_TZ = dt_util.DEFAULT_TIME_ZONE

SCHEMA_VERSION_POSTFIX = "23_with_newer_columns"
SCHEMA_MODULE = get_schema_module_path(SCHEMA_VERSION_POSTFIX)


def test_delete_duplicates(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    """Test removal of duplicated statistics."""
    test_dir = tmp_path.joinpath("sqlite")
    test_dir.mkdir()
    test_db_file = test_dir.joinpath("test_run_info.db")
    dburl = f"{SQLITE_URL_PREFIX}//{test_db_file}"

    importlib.import_module(SCHEMA_MODULE)
    old_db_schema = sys.modules[SCHEMA_MODULE]

    period1 = dt_util.as_utc(dt_util.parse_datetime("2021-09-01 00:00:00"))
    period2 = dt_util.as_utc(dt_util.parse_datetime("2021-09-30 23:00:00"))
    period3 = dt_util.as_utc(dt_util.parse_datetime("2021-10-01 00:00:00"))
    period4 = dt_util.as_utc(dt_util.parse_datetime("2021-10-31 23:00:00"))

    external_energy_statistics_1 = (
        {
            "start": period1,
            "last_reset": None,
            "state": 0,
            "sum": 2,
        },
        {
            "start": period2,
            "last_reset": None,
            "state": 1,
            "sum": 3,
        },
        {
            "start": period3,
            "last_reset": None,
            "state": 2,
            "sum": 4,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 5,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 5,
        },
    )
    external_energy_metadata_1 = {
        "has_mean": False,
        "has_sum": True,
        "name": "Total imported energy",
        "source": "test",
        "statistic_id": "test:total_energy_import_tariff_1",
        "unit_of_measurement": "kWh",
    }
    external_energy_statistics_2 = (
        {
            "start": period1,
            "last_reset": None,
            "state": 0,
            "sum": 20,
        },
        {
            "start": period2,
            "last_reset": None,
            "state": 1,
            "sum": 30,
        },
        {
            "start": period3,
            "last_reset": None,
            "state": 2,
            "sum": 40,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 50,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 50,
        },
    )
    external_energy_metadata_2 = {
        "has_mean": False,
        "has_sum": True,
        "name": "Total imported energy",
        "source": "test",
        "statistic_id": "test:total_energy_import_tariff_2",
        "unit_of_measurement": "kWh",
    }
    external_co2_statistics = (
        {
            "start": period1,
            "last_reset": None,
            "mean": 10,
        },
        {
            "start": period2,
            "last_reset": None,
            "mean": 30,
        },
        {
            "start": period3,
            "last_reset": None,
            "mean": 60,
        },
        {
            "start": period4,
            "last_reset": None,
            "mean": 90,
        },
    )
    external_co2_metadata = {
        "has_mean": True,
        "has_sum": False,
        "name": "Fossil percentage",
        "source": "test",
        "statistic_id": "test:fossil_percentage",
        "unit_of_measurement": "%",
    }

    # Create some duplicated statistics with schema version 23
    with patch.object(recorder, "db_schema", old_db_schema), patch.object(
        recorder.migration, "SCHEMA_VERSION", old_db_schema.SCHEMA_VERSION
    ), patch(
        CREATE_ENGINE_TARGET,
        new=partial(
            create_engine_test_for_schema_version_postfix,
            schema_version_postfix=SCHEMA_VERSION_POSTFIX,
        ),
    ):
        hass = get_test_home_assistant()
        recorder_helper.async_initialize_recorder(hass)
        setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
        wait_recording_done(hass)
        wait_recording_done(hass)

        with session_scope(hass=hass) as session:
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_energy_metadata_1)
            )
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_energy_metadata_2)
            )
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_co2_metadata)
            )
        with session_scope(hass=hass) as session:
            for stat in external_energy_statistics_1:
                session.add(recorder.db_schema.Statistics.from_stats(1, stat))
            for stat in external_energy_statistics_2:
                session.add(recorder.db_schema.Statistics.from_stats(2, stat))
            for stat in external_co2_statistics:
                session.add(recorder.db_schema.Statistics.from_stats(3, stat))

        hass.stop()
        dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    # Test that the duplicates are removed during migration from schema 23
    hass = get_test_home_assistant()
    recorder_helper.async_initialize_recorder(hass)
    setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
    hass.start()
    wait_recording_done(hass)
    wait_recording_done(hass)
    hass.stop()
    dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    assert "Deleted 2 duplicated statistics rows" in caplog.text
    assert "Found non identical" not in caplog.text
    assert "Found duplicated" not in caplog.text


def test_delete_duplicates_many(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Test removal of duplicated statistics."""
    test_dir = tmp_path.joinpath("sqlite")
    test_dir.mkdir()
    test_db_file = test_dir.joinpath("test_run_info.db")
    dburl = f"{SQLITE_URL_PREFIX}//{test_db_file}"

    importlib.import_module(SCHEMA_MODULE)
    old_db_schema = sys.modules[SCHEMA_MODULE]

    period1 = dt_util.as_utc(dt_util.parse_datetime("2021-09-01 00:00:00"))
    period2 = dt_util.as_utc(dt_util.parse_datetime("2021-09-30 23:00:00"))
    period3 = dt_util.as_utc(dt_util.parse_datetime("2021-10-01 00:00:00"))
    period4 = dt_util.as_utc(dt_util.parse_datetime("2021-10-31 23:00:00"))

    external_energy_statistics_1 = (
        {
            "start": period1,
            "last_reset": None,
            "state": 0,
            "sum": 2,
        },
        {
            "start": period2,
            "last_reset": None,
            "state": 1,
            "sum": 3,
        },
        {
            "start": period3,
            "last_reset": None,
            "state": 2,
            "sum": 4,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 5,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 5,
        },
    )
    external_energy_metadata_1 = {
        "has_mean": False,
        "has_sum": True,
        "name": "Total imported energy",
        "source": "test",
        "statistic_id": "test:total_energy_import_tariff_1",
        "unit_of_measurement": "kWh",
    }
    external_energy_statistics_2 = (
        {
            "start": period1,
            "last_reset": None,
            "state": 0,
            "sum": 20,
        },
        {
            "start": period2,
            "last_reset": None,
            "state": 1,
            "sum": 30,
        },
        {
            "start": period3,
            "last_reset": None,
            "state": 2,
            "sum": 40,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 50,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 50,
        },
    )
    external_energy_metadata_2 = {
        "has_mean": False,
        "has_sum": True,
        "name": "Total imported energy",
        "source": "test",
        "statistic_id": "test:total_energy_import_tariff_2",
        "unit_of_measurement": "kWh",
    }
    external_co2_statistics = (
        {
            "start": period1,
            "last_reset": None,
            "mean": 10,
        },
        {
            "start": period2,
            "last_reset": None,
            "mean": 30,
        },
        {
            "start": period3,
            "last_reset": None,
            "mean": 60,
        },
        {
            "start": period4,
            "last_reset": None,
            "mean": 90,
        },
    )
    external_co2_metadata = {
        "has_mean": True,
        "has_sum": False,
        "name": "Fossil percentage",
        "source": "test",
        "statistic_id": "test:fossil_percentage",
        "unit_of_measurement": "%",
    }

    # Create some duplicated statistics with schema version 23
    with patch.object(recorder, "db_schema", old_db_schema), patch.object(
        recorder.migration, "SCHEMA_VERSION", old_db_schema.SCHEMA_VERSION
    ), patch(
        CREATE_ENGINE_TARGET,
        new=partial(
            create_engine_test_for_schema_version_postfix,
            schema_version_postfix=SCHEMA_VERSION_POSTFIX,
        ),
    ):
        hass = get_test_home_assistant()
        recorder_helper.async_initialize_recorder(hass)
        setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
        wait_recording_done(hass)
        wait_recording_done(hass)

        with session_scope(hass=hass) as session:
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_energy_metadata_1)
            )
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_energy_metadata_2)
            )
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_co2_metadata)
            )
        with session_scope(hass=hass) as session:
            for stat in external_energy_statistics_1:
                session.add(recorder.db_schema.Statistics.from_stats(1, stat))
            for _ in range(3000):
                session.add(
                    recorder.db_schema.Statistics.from_stats(
                        1, external_energy_statistics_1[-1]
                    )
                )
            for stat in external_energy_statistics_2:
                session.add(recorder.db_schema.Statistics.from_stats(2, stat))
            for stat in external_co2_statistics:
                session.add(recorder.db_schema.Statistics.from_stats(3, stat))

        hass.stop()
        dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    # Test that the duplicates are removed during migration from schema 23
    hass = get_test_home_assistant()
    recorder_helper.async_initialize_recorder(hass)
    setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
    hass.start()
    wait_recording_done(hass)
    wait_recording_done(hass)
    hass.stop()
    dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    assert "Deleted 3002 duplicated statistics rows" in caplog.text
    assert "Found non identical" not in caplog.text
    assert "Found duplicated" not in caplog.text


@pytest.mark.freeze_time("2021-08-01 00:00:00+00:00")
def test_delete_duplicates_non_identical(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Test removal of duplicated statistics."""
    test_dir = tmp_path.joinpath("sqlite")
    test_dir.mkdir()
    test_db_file = test_dir.joinpath("test_run_info.db")
    dburl = f"{SQLITE_URL_PREFIX}//{test_db_file}"

    importlib.import_module(SCHEMA_MODULE)
    old_db_schema = sys.modules[SCHEMA_MODULE]

    period1 = dt_util.as_utc(dt_util.parse_datetime("2021-09-01 00:00:00"))
    period2 = dt_util.as_utc(dt_util.parse_datetime("2021-09-30 23:00:00"))
    period3 = dt_util.as_utc(dt_util.parse_datetime("2021-10-01 00:00:00"))
    period4 = dt_util.as_utc(dt_util.parse_datetime("2021-10-31 23:00:00"))

    external_energy_statistics_1 = (
        {
            "start": period1,
            "last_reset": None,
            "state": 0,
            "sum": 2,
        },
        {
            "start": period2,
            "last_reset": None,
            "state": 1,
            "sum": 3,
        },
        {
            "start": period3,
            "last_reset": None,
            "state": 2,
            "sum": 4,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 5,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 6,
        },
    )
    external_energy_metadata_1 = {
        "has_mean": False,
        "has_sum": True,
        "name": "Total imported energy",
        "source": "test",
        "statistic_id": "test:total_energy_import_tariff_1",
        "unit_of_measurement": "kWh",
    }
    external_energy_statistics_2 = (
        {
            "start": period1,
            "last_reset": None,
            "state": 0,
            "sum": 20,
        },
        {
            "start": period2,
            "last_reset": None,
            "state": 1,
            "sum": 30,
        },
        {
            "start": period3,
            "last_reset": None,
            "state": 2,
            "sum": 40,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 50,
        },
        {
            "start": period4,
            "last_reset": None,
            "state": 3,
            "sum": 50,
        },
    )
    external_energy_metadata_2 = {
        "has_mean": False,
        "has_sum": True,
        "name": "Total imported energy",
        "source": "test",
        "statistic_id": "test:total_energy_import_tariff_2",
        "unit_of_measurement": "kWh",
    }

    # Create some duplicated statistics with schema version 23
    with patch.object(recorder, "db_schema", old_db_schema), patch.object(
        recorder.migration, "SCHEMA_VERSION", old_db_schema.SCHEMA_VERSION
    ), patch(
        CREATE_ENGINE_TARGET,
        new=partial(
            create_engine_test_for_schema_version_postfix,
            schema_version_postfix=SCHEMA_VERSION_POSTFIX,
        ),
    ):
        hass = get_test_home_assistant()
        recorder_helper.async_initialize_recorder(hass)
        setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
        wait_recording_done(hass)
        wait_recording_done(hass)

        with session_scope(hass=hass) as session:
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_energy_metadata_1)
            )
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_energy_metadata_2)
            )
        with session_scope(hass=hass) as session:
            for stat in external_energy_statistics_1:
                session.add(recorder.db_schema.Statistics.from_stats(1, stat))
            for stat in external_energy_statistics_2:
                session.add(recorder.db_schema.Statistics.from_stats(2, stat))

        hass.stop()
        dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    # Test that the duplicates are removed during migration from schema 23
    hass = get_test_home_assistant()
    hass.config.config_dir = tmp_path
    recorder_helper.async_initialize_recorder(hass)
    setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
    hass.start()
    wait_recording_done(hass)
    wait_recording_done(hass)
    hass.stop()
    dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    assert "Deleted 2 duplicated statistics rows" in caplog.text
    assert "Deleted 1 non identical" in caplog.text
    assert "Found duplicated" not in caplog.text

    isotime = dt_util.utcnow().isoformat()
    backup_file_name = f".storage/deleted_statistics.{isotime}.json"

    with open(hass.config.path(backup_file_name)) as backup_file:
        backup = json.load(backup_file)

    assert backup == [
        {
            "duplicate": {
                "created": "2021-08-01T00:00:00",
                "id": 4,
                "last_reset": None,
                "max": None,
                "mean": None,
                "metadata_id": 1,
                "min": None,
                "start": "2021-10-31T23:00:00",
                "state": 3.0,
                "sum": 5.0,
            },
            "original": {
                "created": "2021-08-01T00:00:00",
                "id": 5,
                "last_reset": None,
                "max": None,
                "mean": None,
                "metadata_id": 1,
                "min": None,
                "start": "2021-10-31T23:00:00",
                "state": 3.0,
                "sum": 6.0,
            },
        }
    ]


def test_delete_duplicates_short_term(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Test removal of duplicated statistics."""
    test_dir = tmp_path.joinpath("sqlite")
    test_dir.mkdir()
    test_db_file = test_dir.joinpath("test_run_info.db")
    dburl = f"{SQLITE_URL_PREFIX}//{test_db_file}"

    importlib.import_module(SCHEMA_MODULE)
    old_db_schema = sys.modules[SCHEMA_MODULE]

    period4 = dt_util.as_utc(dt_util.parse_datetime("2021-10-31 23:00:00"))

    external_energy_metadata_1 = {
        "has_mean": False,
        "has_sum": True,
        "name": "Total imported energy",
        "source": "test",
        "statistic_id": "test:total_energy_import_tariff_1",
        "unit_of_measurement": "kWh",
    }
    statistic_row = {
        "start": period4,
        "last_reset": None,
        "state": 3,
        "sum": 5,
    }

    # Create some duplicated statistics with schema version 23
    with patch.object(recorder, "db_schema", old_db_schema), patch.object(
        recorder.migration, "SCHEMA_VERSION", old_db_schema.SCHEMA_VERSION
    ), patch(
        CREATE_ENGINE_TARGET,
        new=partial(
            create_engine_test_for_schema_version_postfix,
            schema_version_postfix=SCHEMA_VERSION_POSTFIX,
        ),
    ):
        hass = get_test_home_assistant()
        recorder_helper.async_initialize_recorder(hass)
        setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
        wait_recording_done(hass)
        wait_recording_done(hass)

        with session_scope(hass=hass) as session:
            session.add(
                recorder.db_schema.StatisticsMeta.from_meta(external_energy_metadata_1)
            )
        with session_scope(hass=hass) as session:
            session.add(
                recorder.db_schema.StatisticsShortTerm.from_stats(1, statistic_row)
            )
            session.add(
                recorder.db_schema.StatisticsShortTerm.from_stats(1, statistic_row)
            )

        hass.stop()
        dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    # Test that the duplicates are removed during migration from schema 23
    hass = get_test_home_assistant()
    hass.config.config_dir = tmp_path
    recorder_helper.async_initialize_recorder(hass)
    setup_component(hass, "recorder", {"recorder": {"db_url": dburl}})
    hass.start()
    wait_recording_done(hass)
    wait_recording_done(hass)
    hass.stop()
    dt_util.DEFAULT_TIME_ZONE = ORIG_TZ

    assert "duplicated statistics rows" not in caplog.text
    assert "Found non identical" not in caplog.text
    assert "Deleted duplicated short term statistic" in caplog.text
