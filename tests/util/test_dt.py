"""Test Home Assistant date util methods."""
from datetime import datetime, timedelta

import pytest

import homeassistant.util.dt as dt_util

DEFAULT_TIME_ZONE = dt_util.DEFAULT_TIME_ZONE
TEST_TIME_ZONE = "America/Los_Angeles"


@pytest.fixture(autouse=True)
def teardown():
    """Stop everything that was started."""
    yield

    dt_util.set_default_time_zone(DEFAULT_TIME_ZONE)


def test_get_time_zone_retrieves_valid_time_zone():
    """Test getting a time zone."""
    assert dt_util.get_time_zone(TEST_TIME_ZONE) is not None


def test_get_time_zone_returns_none_for_garbage_time_zone():
    """Test getting a non existing time zone."""
    assert dt_util.get_time_zone("Non existing time zone") is None


def test_set_default_time_zone():
    """Test setting default time zone."""
    time_zone = dt_util.get_time_zone(TEST_TIME_ZONE)

    dt_util.set_default_time_zone(time_zone)

    assert dt_util.now().tzinfo is time_zone


def test_utcnow():
    """Test the UTC now method."""
    assert abs(dt_util.utcnow().replace(tzinfo=None) - datetime.utcnow()) < timedelta(
        seconds=1
    )


def test_now():
    """Test the now method."""
    dt_util.set_default_time_zone(dt_util.get_time_zone(TEST_TIME_ZONE))

    assert abs(
        dt_util.as_utc(dt_util.now()).replace(tzinfo=None) - datetime.utcnow()
    ) < timedelta(seconds=1)


def test_as_utc_with_naive_object():
    """Test the now method."""
    utcnow = datetime.utcnow()

    assert utcnow == dt_util.as_utc(utcnow).replace(tzinfo=None)


def test_as_utc_with_utc_object():
    """Test UTC time with UTC object."""
    utcnow = dt_util.utcnow()

    assert utcnow == dt_util.as_utc(utcnow)


def test_as_utc_with_local_object():
    """Test the UTC time with local object."""
    dt_util.set_default_time_zone(dt_util.get_time_zone(TEST_TIME_ZONE))
    localnow = dt_util.now()
    utcnow = dt_util.as_utc(localnow)

    assert localnow == utcnow
    assert localnow.tzinfo != utcnow.tzinfo


def test_as_local_with_naive_object():
    """Test local time with native object."""
    now = dt_util.now()
    assert abs(now - dt_util.as_local(datetime.utcnow())) < timedelta(seconds=1)


def test_as_local_with_local_object():
    """Test local with local object."""
    now = dt_util.now()
    assert now == now


def test_as_local_with_utc_object():
    """Test local time with UTC object."""
    dt_util.set_default_time_zone(dt_util.get_time_zone(TEST_TIME_ZONE))

    utcnow = dt_util.utcnow()
    localnow = dt_util.as_local(utcnow)

    assert localnow == utcnow
    assert localnow.tzinfo != utcnow.tzinfo


def test_utc_from_timestamp():
    """Test utc_from_timestamp method."""
    assert datetime(1986, 7, 9, tzinfo=dt_util.UTC) == dt_util.utc_from_timestamp(
        521251200
    )


def test_as_timestamp():
    """Test as_timestamp method."""
    ts = 1462401234
    utc_dt = dt_util.utc_from_timestamp(ts)
    assert ts == dt_util.as_timestamp(utc_dt)
    utc_iso = utc_dt.isoformat()
    assert ts == dt_util.as_timestamp(utc_iso)

    # confirm the ability to handle a string passed in
    delta = dt_util.as_timestamp("2016-01-01 12:12:12")
    delta -= dt_util.as_timestamp("2016-01-01 12:12:11")
    assert delta == 1


def test_parse_datetime_converts_correctly():
    """Test parse_datetime converts strings."""
    assert datetime(1986, 7, 9, 12, 0, 0, tzinfo=dt_util.UTC) == dt_util.parse_datetime(
        "1986-07-09T12:00:00Z"
    )

    utcnow = dt_util.utcnow()

    assert utcnow == dt_util.parse_datetime(utcnow.isoformat())


def test_parse_datetime_returns_none_for_incorrect_format():
    """Test parse_datetime returns None if incorrect format."""
    assert dt_util.parse_datetime("not a datetime string") is None


def test_get_age():
    """Test get_age."""
    diff = dt_util.now() - timedelta(seconds=0)
    assert dt_util.get_age(diff) == "0 seconds"

    diff = dt_util.now() - timedelta(seconds=1)
    assert dt_util.get_age(diff) == "1 second"

    diff = dt_util.now() - timedelta(seconds=30)
    assert dt_util.get_age(diff) == "30 seconds"

    diff = dt_util.now() - timedelta(minutes=5)
    assert dt_util.get_age(diff) == "5 minutes"

    diff = dt_util.now() - timedelta(minutes=1)
    assert dt_util.get_age(diff) == "1 minute"

    diff = dt_util.now() - timedelta(minutes=300)
    assert dt_util.get_age(diff) == "5 hours"

    diff = dt_util.now() - timedelta(minutes=320)
    assert dt_util.get_age(diff) == "5 hours"

    diff = dt_util.now() - timedelta(minutes=1.6 * 60 * 24)
    assert dt_util.get_age(diff) == "2 days"

    diff = dt_util.now() - timedelta(minutes=2 * 60 * 24)
    assert dt_util.get_age(diff) == "2 days"

    diff = dt_util.now() - timedelta(minutes=32 * 60 * 24)
    assert dt_util.get_age(diff) == "1 month"

    diff = dt_util.now() - timedelta(minutes=365 * 60 * 24)
    assert dt_util.get_age(diff) == "1 year"


def test_parse_time_expression():
    """Test parse_time_expression."""
    assert list(range(60)) == dt_util.parse_time_expression("*", 0, 59)
    assert list(range(60)) == dt_util.parse_time_expression(None, 0, 59)

    assert list(range(0, 60, 5)) == dt_util.parse_time_expression("/5", 0, 59)

    assert [1, 2, 3] == dt_util.parse_time_expression([2, 1, 3], 0, 59)

    assert list(range(24)) == dt_util.parse_time_expression("*", 0, 23)

    assert [42] == dt_util.parse_time_expression(42, 0, 59)
    assert [42] == dt_util.parse_time_expression("42", 0, 59)

    with pytest.raises(ValueError):
        dt_util.parse_time_expression(61, 0, 60)


def test_find_next_time_expression_time_basic():
    """Test basic stuff for find_next_time_expression_time."""

    def find(dt, hour, minute, second):
        """Call test_find_next_time_expression_time."""
        seconds = dt_util.parse_time_expression(second, 0, 59)
        minutes = dt_util.parse_time_expression(minute, 0, 59)
        hours = dt_util.parse_time_expression(hour, 0, 23)

        return dt_util.find_next_time_expression_time(dt, seconds, minutes, hours)

    assert datetime(2018, 10, 7, 10, 30, 0) == find(
        datetime(2018, 10, 7, 10, 20, 0), "*", "/30", 0
    )

    assert datetime(2018, 10, 7, 10, 30, 0) == find(
        datetime(2018, 10, 7, 10, 30, 0), "*", "/30", 0
    )

    assert datetime(2018, 10, 7, 12, 0, 30) == find(
        datetime(2018, 10, 7, 10, 30, 0), "/3", "/30", [30, 45]
    )

    assert datetime(2018, 10, 8, 5, 0, 0) == find(
        datetime(2018, 10, 7, 10, 30, 0), 5, 0, 0
    )

    assert find(datetime(2018, 10, 7, 10, 30, 0, 999999), "*", "/30", 0) == datetime(
        2018, 10, 7, 10, 30, 0
    )


def test_find_next_time_expression_time_dst():
    """Test daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("Europe/Vienna")
    dt_util.set_default_time_zone(tz)

    def find(dt, hour, minute, second) -> datetime:
        """Call test_find_next_time_expression_time."""
        seconds = dt_util.parse_time_expression(second, 0, 59)
        minutes = dt_util.parse_time_expression(minute, 0, 59)
        hours = dt_util.parse_time_expression(hour, 0, 23)

        local = dt_util.find_next_time_expression_time(dt, seconds, minutes, hours)
        return dt_util.as_utc(local)

    # Entering DST, clocks are rolled forward
    assert dt_util.as_utc(datetime(2018, 3, 26, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2018, 3, 25, 1, 50, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 3, 26, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2018, 3, 25, 3, 50, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 3, 26, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2018, 3, 26, 1, 50, 0, tzinfo=tz), 2, 30, 0
    )

    # Leaving DST, clocks are rolled back
    assert dt_util.as_utc(datetime(2018, 10, 28, 2, 30, 0, tzinfo=tz, fold=0)) == find(
        datetime(2018, 10, 28, 2, 5, 0, tzinfo=tz, fold=0), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 10, 28, 2, 30, 0, tzinfo=tz, fold=0)) == find(
        datetime(2018, 10, 28, 2, 5, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 10, 28, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2018, 10, 28, 2, 55, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 10, 28, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2018, 10, 28, 2, 55, 0, tzinfo=tz, fold=0), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 10, 28, 4, 30, 0, tzinfo=tz, fold=0)) == find(
        datetime(2018, 10, 28, 2, 55, 0, tzinfo=tz, fold=1), 4, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 10, 28, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2018, 10, 28, 2, 5, 0, tzinfo=tz, fold=1), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2018, 10, 28, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2018, 10, 28, 2, 55, 0, tzinfo=tz, fold=0), 2, 30, 0
    )


# DST begins on 2021.03.28 2:00, clocks were turned forward 1h; 2:00-3:00 time does not exist
@pytest.mark.parametrize(
    "now_dt, expected_dt",
    [
        # 00:00 -> 2:30
        (
            datetime(2021, 3, 28, 0, 0, 0),
            datetime(2021, 3, 29, 2, 30, 0),
        ),
    ],
)
def test_find_next_time_expression_entering_dst(now_dt, expected_dt):
    """Test entering daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("Europe/Vienna")
    dt_util.set_default_time_zone(tz)
    # match on 02:30:00 every day
    pattern_seconds = dt_util.parse_time_expression(0, 0, 59)
    pattern_minutes = dt_util.parse_time_expression(30, 0, 59)
    pattern_hours = dt_util.parse_time_expression(2, 0, 59)

    now_dt = now_dt.replace(tzinfo=tz)
    expected_dt = expected_dt.replace(tzinfo=tz)

    res_dt = dt_util.find_next_time_expression_time(
        now_dt, pattern_seconds, pattern_minutes, pattern_hours
    )
    assert dt_util.as_utc(res_dt) == dt_util.as_utc(expected_dt)


# DST ends on 2021.10.31 2:00, clocks were turned backward 1h; 2:00-3:00 time is ambiguous
@pytest.mark.parametrize(
    "now_dt, expected_dt",
    [
        # 00:00 -> 2:30
        (
            datetime(2021, 10, 31, 0, 0, 0),
            datetime(2021, 10, 31, 2, 30, 0, fold=0),
        ),
        # 02:00(0) -> 2:30(0)
        (
            datetime(2021, 10, 31, 2, 0, 0, fold=0),
            datetime(2021, 10, 31, 2, 30, 0, fold=0),
        ),
        # 02:15(0) -> 2:30(0)
        (
            datetime(2021, 10, 31, 2, 15, 0, fold=0),
            datetime(2021, 10, 31, 2, 30, 0, fold=0),
        ),
        # 02:30:00(0) -> 2:30(1)
        (
            datetime(2021, 10, 31, 2, 30, 0, fold=0),
            datetime(2021, 10, 31, 2, 30, 0, fold=0),
        ),
        # 02:30:01(0) -> 2:30(1)
        (
            datetime(2021, 10, 31, 2, 30, 1, fold=0),
            datetime(2021, 10, 31, 2, 30, 0, fold=1),
        ),
        # 02:45(0) -> 2:30(1)
        (
            datetime(2021, 10, 31, 2, 45, 0, fold=0),
            datetime(2021, 10, 31, 2, 30, 0, fold=1),
        ),
        # 02:00(1) -> 2:30(1)
        (
            datetime(2021, 10, 31, 2, 0, 0, fold=1),
            datetime(2021, 10, 31, 2, 30, 0, fold=1),
        ),
        # 02:15(1) -> 2:30(1)
        (
            datetime(2021, 10, 31, 2, 15, 0, fold=1),
            datetime(2021, 10, 31, 2, 30, 0, fold=1),
        ),
        # 02:30:00(1) -> 2:30(1)
        (
            datetime(2021, 10, 31, 2, 30, 0, fold=1),
            datetime(2021, 10, 31, 2, 30, 0, fold=1),
        ),
        # 02:30:01(1) -> 2:30 next day
        (
            datetime(2021, 10, 31, 2, 30, 1, fold=1),
            datetime(2021, 11, 1, 2, 30, 0),
        ),
        # 02:45(1) -> 2:30 next day
        (
            datetime(2021, 10, 31, 2, 45, 0, fold=1),
            datetime(2021, 11, 1, 2, 30, 0),
        ),
        # 08:00(1) -> 2:30 next day
        (
            datetime(2021, 10, 31, 8, 0, 1),
            datetime(2021, 11, 1, 2, 30, 0),
        ),
    ],
)
def test_find_next_time_expression_exiting_dst(now_dt, expected_dt):
    """Test exiting daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("Europe/Vienna")
    dt_util.set_default_time_zone(tz)
    # match on 02:30:00 every day
    pattern_seconds = dt_util.parse_time_expression(0, 0, 59)
    pattern_minutes = dt_util.parse_time_expression(30, 0, 59)
    pattern_hours = dt_util.parse_time_expression(2, 0, 59)

    now_dt = now_dt.replace(tzinfo=tz)
    expected_dt = expected_dt.replace(tzinfo=tz)

    res_dt = dt_util.find_next_time_expression_time(
        now_dt, pattern_seconds, pattern_minutes, pattern_hours
    )
    assert dt_util.as_utc(res_dt) == dt_util.as_utc(expected_dt)


def test_find_next_time_expression_time_dst_chicago():
    """Test daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    def find(dt, hour, minute, second) -> datetime:
        """Call test_find_next_time_expression_time."""
        seconds = dt_util.parse_time_expression(second, 0, 59)
        minutes = dt_util.parse_time_expression(minute, 0, 59)
        hours = dt_util.parse_time_expression(hour, 0, 23)

        local = dt_util.find_next_time_expression_time(dt, seconds, minutes, hours)
        return dt_util.as_utc(local)

    # Entering DST, clocks are rolled forward
    assert dt_util.as_utc(datetime(2021, 3, 15, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2021, 3, 14, 1, 50, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 3, 15, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2021, 3, 14, 3, 50, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 3, 15, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2021, 3, 14, 1, 50, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 3, 14, 3, 30, 0, tzinfo=tz)) == find(
        datetime(2021, 3, 14, 1, 50, 0, tzinfo=tz), 3, 30, 0
    )

    # Leaving DST, clocks are rolled back
    assert dt_util.as_utc(datetime(2021, 11, 7, 2, 30, 0, tzinfo=tz, fold=0)) == find(
        datetime(2021, 11, 7, 2, 5, 0, tzinfo=tz, fold=0), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 7, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2021, 11, 7, 2, 5, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 7, 2, 30, 0, tzinfo=tz, fold=0)) == find(
        datetime(2021, 11, 7, 2, 5, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 7, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2021, 11, 7, 2, 10, 0, tzinfo=tz), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 7, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2021, 11, 7, 2, 30, 0, tzinfo=tz, fold=0), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 8, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2021, 11, 7, 2, 55, 0, tzinfo=tz, fold=0), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 7, 4, 30, 0, tzinfo=tz, fold=0)) == find(
        datetime(2021, 11, 7, 2, 55, 0, tzinfo=tz, fold=1), 4, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 7, 2, 30, 0, tzinfo=tz, fold=1)) == find(
        datetime(2021, 11, 7, 2, 5, 0, tzinfo=tz, fold=1), 2, 30, 0
    )

    assert dt_util.as_utc(datetime(2021, 11, 8, 2, 30, 0, tzinfo=tz)) == find(
        datetime(2021, 11, 7, 2, 55, 0, tzinfo=tz, fold=0), 2, 30, 0
    )


def _get_matches(hours, minutes, seconds):
    matching_hours = dt_util.parse_time_expression(hours, 0, 23)
    matching_minutes = dt_util.parse_time_expression(minutes, 0, 59)
    matching_seconds = dt_util.parse_time_expression(seconds, 0, 59)
    return matching_hours, matching_minutes, matching_seconds


def test_find_next_time_expression_day_before_dst_change_the_same_time():
    """Test the day before DST to establish behavior without DST."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    # Not in DST yet
    hour_minute_second = (12, 30, 1)
    test_time = datetime(2021, 10, 7, *hour_minute_second, tzinfo=tz, fold=0)
    matching_hours, matching_minutes, matching_seconds = _get_matches(
        *hour_minute_second
    )
    next_time = dt_util.find_next_time_expression_time(
        test_time, matching_seconds, matching_minutes, matching_hours
    )
    assert next_time == datetime(2021, 10, 7, *hour_minute_second, tzinfo=tz, fold=0)
    assert next_time.fold == 0
    assert dt_util.as_utc(next_time) == datetime(
        2021, 10, 7, 17, 30, 1, tzinfo=dt_util.UTC
    )


def test_find_next_time_expression_time_leave_dst_chicago_before_the_fold_30_s():
    """Test leaving daylight saving time for find_next_time_expression_time 30s into the future."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    # Leaving DST, clocks are rolled back

    # Move ahead 30 seconds not folded yet
    hour_minute_second = (1, 30, 31)
    test_time = datetime(2021, 11, 7, 1, 30, 1, tzinfo=tz, fold=0)
    matching_hours, matching_minutes, matching_seconds = _get_matches(
        *hour_minute_second
    )
    next_time = dt_util.find_next_time_expression_time(
        test_time, matching_seconds, matching_minutes, matching_hours
    )
    assert next_time == datetime(2021, 11, 7, 1, 30, 31, tzinfo=tz, fold=0)
    assert dt_util.as_utc(next_time) == datetime(
        2021, 11, 7, 6, 30, 31, tzinfo=dt_util.UTC
    )
    assert next_time.fold == 0


def test_find_next_time_expression_time_leave_dst_chicago_before_the_fold_same_time():
    """Test leaving daylight saving time for find_next_time_expression_time with the same time."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    # Leaving DST, clocks are rolled back

    # Move to the same time not folded yet
    hour_minute_second = (0, 30, 1)
    test_time = datetime(2021, 11, 7, *hour_minute_second, tzinfo=tz, fold=0)
    matching_hours, matching_minutes, matching_seconds = _get_matches(
        *hour_minute_second
    )
    next_time = dt_util.find_next_time_expression_time(
        test_time, matching_seconds, matching_minutes, matching_hours
    )
    assert next_time == datetime(2021, 11, 7, *hour_minute_second, tzinfo=tz, fold=0)
    assert dt_util.as_utc(next_time) == datetime(
        2021, 11, 7, 5, 30, 1, tzinfo=dt_util.UTC
    )
    assert next_time.fold == 0


def test_find_next_time_expression_time_leave_dst_chicago_into_the_fold_same_time():
    """Test leaving daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    # Leaving DST, clocks are rolled back

    # Find the same time inside the fold
    hour_minute_second = (1, 30, 1)
    test_time = datetime(2021, 11, 7, *hour_minute_second, tzinfo=tz, fold=0)
    matching_hours, matching_minutes, matching_seconds = _get_matches(
        *hour_minute_second
    )

    next_time = dt_util.find_next_time_expression_time(
        test_time, matching_seconds, matching_minutes, matching_hours
    )
    assert next_time == datetime(2021, 11, 7, *hour_minute_second, tzinfo=tz, fold=1)
    assert next_time.fold == 0
    assert dt_util.as_utc(next_time) == datetime(
        2021, 11, 7, 6, 30, 1, tzinfo=dt_util.UTC
    )


def test_find_next_time_expression_time_leave_dst_chicago_into_the_fold_ahead_1_hour_10_min():
    """Test leaving daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    # Leaving DST, clocks are rolled back

    # Find 1h 10m after into the fold
    # Start at 01:30:01 fold=0
    # Reach to 01:20:01 fold=1
    hour_minute_second = (1, 20, 1)
    test_time = datetime(2021, 11, 7, 1, 30, 1, tzinfo=tz, fold=0)
    matching_hours, matching_minutes, matching_seconds = _get_matches(
        *hour_minute_second
    )

    next_time = dt_util.find_next_time_expression_time(
        test_time, matching_seconds, matching_minutes, matching_hours
    )
    assert next_time == datetime(2021, 11, 7, *hour_minute_second, tzinfo=tz, fold=1)
    assert next_time.fold == 1  # time is ambiguous
    assert dt_util.as_utc(next_time) == datetime(
        2021, 11, 7, 7, 20, 1, tzinfo=dt_util.UTC
    )


def test_find_next_time_expression_time_leave_dst_chicago_inside_the_fold_ahead_10_min():
    """Test leaving daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    # Leaving DST, clocks are rolled back

    # Find 10m later while we are in the fold
    # Start at 01:30:01 fold=0
    # Reach to 01:40:01 fold=1
    hour_minute_second = (1, 40, 1)
    test_time = datetime(2021, 11, 7, 1, 30, 1, tzinfo=tz, fold=1)
    matching_hours, matching_minutes, matching_seconds = _get_matches(
        *hour_minute_second
    )

    next_time = dt_util.find_next_time_expression_time(
        test_time, matching_seconds, matching_minutes, matching_hours
    )
    assert next_time == datetime(2021, 11, 7, *hour_minute_second, tzinfo=tz, fold=1)
    assert next_time.fold == 1  # time is ambiguous
    assert dt_util.as_utc(next_time) == datetime(
        2021, 11, 7, 7, 40, 1, tzinfo=dt_util.UTC
    )


def test_find_next_time_expression_time_leave_dst_chicago_past_the_fold_ahead_2_hour_10_min():
    """Test leaving daylight saving time for find_next_time_expression_time."""
    tz = dt_util.get_time_zone("America/Chicago")
    dt_util.set_default_time_zone(tz)

    # Leaving DST, clocks are rolled back

    # Find 1h 10m after into the fold
    # Start at 01:30:01 fold=0
    # Reach to 02:20:01 past the fold
    hour_minute_second = (2, 20, 1)
    test_time = datetime(2021, 11, 7, 1, 30, 1, tzinfo=tz, fold=0)
    matching_hours, matching_minutes, matching_seconds = _get_matches(
        *hour_minute_second
    )

    next_time = dt_util.find_next_time_expression_time(
        test_time, matching_seconds, matching_minutes, matching_hours
    )
    assert next_time == datetime(2021, 11, 7, *hour_minute_second, tzinfo=tz, fold=1)
    assert next_time.fold == 0  # Time is no longer ambiguous
    assert dt_util.as_utc(next_time) == datetime(
        2021, 11, 7, 8, 20, 1, tzinfo=dt_util.UTC
    )
