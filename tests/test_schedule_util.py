from datetime import datetime, time
from unittest.mock import Mock

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from bot_utils.bot_enums import EndUrlDistribution, SurveyType
from bot_utils.config import (
    Config,
    DayCalculationSettings,
    Help,
    LinkDeletionSettings,
    RandomTimeShiftSettings,
    Texts,
    TimeCalculationSettings,
    Urls,
)
from bot_utils.schedule_util import BotScheduleError, ScheduleUtil

@pytest.fixture
def scheduler():
    scheduler = BackgroundScheduler()
    yield scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)


@pytest.fixture
def db_handler():
    db = Mock()
    db.get_time_offset.return_value = 0
    db.get_used_conditions.return_value = []
    db.get_used_condition.return_value = 0
    return db


@pytest.fixture
def schedule_util(scheduler, db_handler, config_dict):
    return ScheduleUtil(
        scheduler=scheduler,
        config=Config(**config_dict()),
        db_handler=db_handler,
    )


def dummy_job(*args, **kwargs):
    pass


def test_schedule_delete_messages_adds_date_job(schedule_util):
    run_date = datetime(2026, 5, 15, 12, 0)

    schedule_util.schedule_delete_messages(
        dummy_job,
        run_date,
        123,
        456,
    )

    jobs = schedule_util.scheduler.get_jobs()

    assert len(jobs) == 1
    assert jobs[0].func == dummy_job
    assert jobs[0].args == (123, 456)


def test_schedule_end_survey_reminder_adds_job_and_db_entries(schedule_util, db_handler):
    subscriber_information = [
        (111, 0, 5),
        (222, 1, 6),
    ]

    schedule_util.schedule_end_survey_reminder(
        dummy_job,
        subscriber_information,
    )

    jobs = schedule_util.scheduler.get_jobs()

    assert len(jobs) == 1
    assert jobs[0].func == dummy_job
    assert jobs[0].args[0] == [111, 222]

    db_handler.insert_end_reminder_entries_from_list.assert_called_once()
    args = db_handler.insert_end_reminder_entries_from_list.call_args.args

    assert args[0] == SurveyType.END
    assert args[1] == subscriber_information
    assert isinstance(args[2], str)


def test_add_job_adds_cron_job(schedule_util):
    run_date = datetime(2026, 5, 15, 9, 30)

    schedule_util.add_job(run_date, dummy_job, SurveyType.DAILY)

    job_id = "2026-05-15-09:30DAILY"
    job = schedule_util.scheduler.get_job(job_id)

    assert job is not None
    assert job.func == dummy_job
    assert job.args == (
        SurveyType.DAILY,
        job_id,
        "2026-05-15-09:30",
    )


def test_add_jobs_from_list_does_not_duplicate_existing_job(schedule_util):
    run_date = datetime(2026, 5, 15, 9, 30)

    schedule_util.add_jobs_from_list([run_date], dummy_job, SurveyType.DAILY)
    schedule_util.add_jobs_from_list([run_date], dummy_job, SurveyType.DAILY)

    assert len(schedule_util.scheduler.get_jobs()) == 1


def test_add_new_subscriber_inserts_daily_and_end_entries_and_adds_jobs(schedule_util, db_handler):
    schedule_util.add_new_subscriber(
        chat_id=123,
        condition=1,
        exec_function=dummy_job,
    )

    assert db_handler.insert_new_subscriber_entries.call_count == 2

    first_call = db_handler.insert_new_subscriber_entries.call_args_list[0].args
    second_call = db_handler.insert_new_subscriber_entries.call_args_list[1].args

    assert first_call[0] == 123
    assert first_call[2] == SurveyType.DAILY
    assert first_call[3] == 1

    assert second_call[0] == 123
    assert second_call[2] == SurveyType.END
    assert second_call[3] == 1

    assert len(schedule_util.scheduler.get_jobs()) == 2


def test_add_new_subscriber_uses_stored_condition_if_unique_conditions_enabled(scheduler, db_handler, config_dict):
    db_handler.get_used_condition.return_value = 7

    schedule_util = ScheduleUtil(
        scheduler=scheduler,
        config=Config(**config_dict(uniqueConditions=True)),
        db_handler=db_handler,
    )

    schedule_util.add_new_subscriber(
        chat_id=123,
        condition=1,
        exec_function=dummy_job,
    )

    first_call = db_handler.insert_new_subscriber_entries.call_args_list[0].args
    assert first_call[3] == 7


def test_add_new_subscriber_requires_wakeup_time_when_time_calculation_enabled(scheduler, db_handler, config_dict):
    schedule_util = ScheduleUtil(
        scheduler=scheduler,
        config=Config(**config_dict(useTimeCalculation=True)),
        db_handler=db_handler,
    )

    with pytest.raises(BotScheduleError):
        schedule_util.add_new_subscriber(
            chat_id=123,
            condition=1,
            exec_function=dummy_job,
            wakeup_time=None,
        )


def test_add_new_subscriber_with_time_calculation(scheduler, db_handler, config_dict):
    schedule_util = ScheduleUtil(
        scheduler=scheduler,
        config=Config(**config_dict(
            useTimeCalculation=True,
            daily_dates=["2026-05-16"],
            end_dates=["2026-05-18"],
            timeCalculationSettings={
                "daily_DelayMinutesAfterWakeup": 30,
                "daily_SurveysPerDay": 2,
                "daily_DelayMinutesBetweenSurveys": 60,
                "end_DelayMinutesAfterWakeup": 30,
                "end_SurveysPerDay": 1,
                "end_DelayMinutesBetweenSurveys": 60,
            },
        )),
        db_handler=db_handler,
    )

    schedule_util.add_new_subscriber(
        chat_id=123,
        condition=1,
        exec_function=dummy_job,
        wakeup_time=time(6, 30),
    )

    assert db_handler.insert_new_subscriber_entries.call_count == 2

    daily_call = db_handler.insert_new_subscriber_entries.call_args_list[0].args
    daily_datetimes = daily_call[1]

    assert daily_datetimes == [
        datetime(2026, 5, 16, 7, 0),
        datetime(2026, 5, 16, 8, 0),
    ]


@pytest.mark.parametrize(
    "distribution, end_list, expected",
    [
        (
            EndUrlDistribution.NONE,
            [
                datetime(2026, 5, 15, 9, 0),
                datetime(2026, 5, 15, 12, 0),
            ],
            [0, 0],
        ),
        (
            EndUrlDistribution.DAY,
            [
                datetime(2026, 5, 15, 9, 0),
                datetime(2026, 5, 15, 12, 0),
                datetime(2026, 5, 16, 9, 0),
            ],
            [0, 0, 1],
        ),
        (
            EndUrlDistribution.TIME,
            [
                datetime(2026, 5, 15, 9, 0),
                datetime(2026, 5, 15, 12, 0),
                datetime(2026, 5, 16, 9, 0),
                datetime(2026, 5, 16, 12, 0),
            ],
            [0, 1, 0, 1],
        ),
        (
            EndUrlDistribution.MIXED,
            [
                datetime(2026, 5, 15, 9, 0),
                datetime(2026, 5, 15, 12, 0),
                datetime(2026, 5, 16, 9, 0),
            ],
            [0, 1, 2],
        ),
    ],
)
def test_calculate_end_distribution(distribution, end_list, expected, scheduler, db_handler, config_dict):
    config = Config(**config_dict(
        urls={
            "start_url": ["https://example.com/start"],
            "daily_url": ["https://example.com/daily"],
            "end_url": [["https://example.com/end-1", "https://example.com/end-2"]],
            "end_url_distribution": distribution.name,
        },
    ))
    schedule_util = ScheduleUtil(scheduler, config, db_handler)

    assert schedule_util.calculate_end_distribution(end_list) == expected


def test_calculate_end_distribution_empty_list(schedule_util):
    assert schedule_util.calculate_end_distribution([]) == []


def test_calculate_end_distribution_random_returns_valid_indices(scheduler, db_handler, config_dict):
    config = Config(**config_dict(
        urls={
            "start_url": ["https://example.com/start"],
            "daily_url": ["https://example.com/daily"],
            "end_url": [["https://example.com/end-1", "https://example.com/end-2"]],
            "end_url_distribution": "RANDOM",
        },
    ))
    schedule_util = ScheduleUtil(scheduler, config, db_handler)

    result = schedule_util.calculate_end_distribution(
        [
            datetime(2026, 5, 15, 9, 0),
            datetime(2026, 5, 15, 12, 0),
            datetime(2026, 5, 16, 9, 0),
        ]
    )

    assert len(result) == 3
    assert all(0 <= index <= 2 for index in result)


def test_assign_condition_returns_false_when_all_conditions_are_used(schedule_util, db_handler):
    db_handler.get_used_conditions.return_value = [0, 1]

    result = schedule_util.assign_condition(chat_id=123)

    assert result is False
    db_handler.set_condition.assert_not_called()


def test_assign_condition_sets_free_condition(schedule_util, db_handler):
    db_handler.get_used_conditions.return_value = [0]

    result = schedule_util.assign_condition(chat_id=123)

    assert result is True
    db_handler.set_condition.assert_called_once()
    chat_id, condition = db_handler.set_condition.call_args.args

    assert chat_id == 123
    assert condition == 1