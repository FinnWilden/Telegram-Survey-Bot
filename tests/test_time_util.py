from datetime import datetime, time, timedelta

import pytest

from bot_utils.bot_utils import TimeSettings
from bot_utils.time_util import TimeUtil


def test_get_time_from_str():
    assert TimeUtil.get_time_from_str("06:30") == time(6, 30)


def test_get_date_time():
    date = datetime(2026, 5, 15, 12, 45)
    clock_time = time(6, 30)

    result = TimeUtil.get_date_time(date, clock_time)

    assert result == datetime(2026, 5, 15, 6, 30)


def test_apply_time_offset():
    date_time = datetime(2026, 5, 15, 12, 0)

    result = TimeUtil.apply_time_offset(date_time, 3600)

    assert result == datetime(2026, 5, 15, 13, 0)


def test_get_date_time_in_with_given_start_time():
    start = datetime(2026, 5, 15, 12, 0)

    result = TimeUtil.get_date_time_in(
        start_time=start,
        hours=1,
        minutes=30,
        seconds=10,
    )

    assert result == datetime(2026, 5, 15, 13, 30, 10)


def test_generate_date_time_list_with_explicit_times():
    dates = [
        datetime(2026, 5, 15),
        datetime(2026, 5, 16),
    ]
    times = [
        [time(9, 0), time(12, 0)],
        [time(10, 0), time(14, 30)],
    ]

    result = TimeUtil.generate_date_time_list(dates, times)

    assert result == [
        datetime(2026, 5, 15, 9, 0),
        datetime(2026, 5, 15, 12, 0),
        datetime(2026, 5, 16, 10, 0),
        datetime(2026, 5, 16, 14, 30),
    ]


def test_generate_date_time_list_with_offset():
    dates = [datetime(2026, 5, 15)]
    times = [[time(9, 0)]]

    result = TimeUtil.generate_date_time_list(
        dates,
        times,
        offset=3600,
    )

    assert result == [
        datetime(2026, 5, 15, 10, 0),
    ]


def test_generate_date_time_list_with_time_settings():
    dates = [datetime(2026, 5, 15)]
    settings = TimeSettings(
        wakeup_time=time(6, 30),
        delay_minutes_after_wakeup=60,
        survey_count=3,
        delay_minutes_between_surveys=120,
    )

    result = TimeUtil.generate_date_time_list(dates, settings)

    assert result == [
        datetime(2026, 5, 15, 7, 30),
        datetime(2026, 5, 15, 9, 30),
        datetime(2026, 5, 15, 11, 30),
    ]


def test_generate_date_time_list_raises_on_length_mismatch():
    dates = [
        datetime(2026, 5, 15),
        datetime(2026, 5, 16),
    ]
    times = [
        [time(9, 0)],
    ]

    with pytest.raises(ValueError):
        TimeUtil.generate_date_time_list(dates, times)


def test_add_dates():
    settings = TimeSettings(
        wakeup_time=time(6, 0),
        delay_minutes_after_wakeup=30,
        survey_count=2,
        delay_minutes_between_surveys=90,
    )

    result = TimeUtil.add_dates(datetime(2026, 5, 15), settings)

    assert result == [
        datetime(2026, 5, 15, 6, 30),
        datetime(2026, 5, 15, 8, 0),
    ]

def test_generate_date_list():
    result = TimeUtil.generate_date_list([0, 1, 2])

    assert len(result) == 3
    assert result[1].date() == (result[0] + timedelta(days=1)).date()
    assert result[2].date() == (result[0] + timedelta(days=2)).date()

def test_get_time_offset_returns_zero_for_same_time():
    participant_datetime = datetime.now().replace(second=0, microsecond=0)

    assert TimeUtil.get_time_offset(participant_datetime) == 0


def test_get_time_offset_for_future_time():
    participant_datetime = (
        datetime.now()
        .replace(second=0, microsecond=0)
        + timedelta(hours=1)
    )

    assert TimeUtil.get_time_offset(participant_datetime) == 3600


def test_get_time_offset_for_past_time():
    participant_datetime = (
        datetime.now()
        .replace(second=0, microsecond=0)
        - timedelta(hours=1)
    )

    assert TimeUtil.get_time_offset(participant_datetime) == -3600