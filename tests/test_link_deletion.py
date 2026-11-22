"""
End-to-end tests for deleting survey links: the deletion times are stored in the database,
so links are also deleted after a restart or crash, within Telegram's 48-hour limit.

The real bot handlers run against a real config file and database (see Study); only Telegram
and the clock are replaced.
"""
import logging
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest, Forbidden, TimedOut

import bot
from bot_utils.bot_enums import SurveyType
from bot_utils.db_handler import DbHandler
from test_participant_number_flow import Study


LINK_DELETION = {
    "deleteSubscriptionSetupMessages": False,
    "start_DeleteLinkAtSubscriptionDeadline": False,
    "start_DeleteLinkTimer": False,
    "start_DeleteDelayMinutes": 240,
    "daily_DeleteLinkAtNewLink": False,
    "daily_DeleteLinkTimer": True,
    "daily_DeleteDelayMinutes": 60,
    "end_DeleteLinkAtNewLink": False,
    "end_DeleteLinkTimer": True,
    "end_DeleteDelayMinutes": 30,
}


class Clock:
    """
    Replaces datetime in bot.py, so tests can move time forward.
    """

    def __init__(self, monkeypatch):
        self.offset = timedelta()
        clock = self

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + clock.offset

        monkeypatch.setattr(bot, "datetime", FrozenDatetime)

    def advance(self, **kwargs):
        self.offset += timedelta(**kwargs)


def make_study(tmp_path, config_dict, monkeypatch, **settings):
    deletion = dict(LINK_DELETION, **settings)
    return Study(tmp_path, config_dict, monkeypatch, linkDeletionSettings=deletion)


def deleted(study):
    return [(call.kwargs["chat_id"], call.kwargs["message_id"]) for call in study.telegram.delete_message.call_args_list]


def sent_link_ids(study, chat_id):
    """Message ids of the messages with a link, in sending order (message ids count from 1)."""
    return [index + 1 for index, message in enumerate(study.telegram.sent) if message.chat_id == chat_id and message.url]


async def restart(study, monkeypatch):
    """Simulate a crash: new database handler, nothing kept in memory."""
    monkeypatch.setattr(bot, "db_handler", DbHandler())
    study.db_handler = bot.db_handler


@pytest.fixture
def clock(monkeypatch):
    return Clock(monkeypatch)


@pytest.mark.asyncio
async def test_daily_link_is_deleted_after_its_delay_even_after_a_crash(tmp_path, config_dict, monkeypatch, clock):
    study = make_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    await study.send_daily()
    daily_link = sent_link_ids(study, 101)[-1]

    await restart(study, monkeypatch)
    clock.advance(minutes=59)
    await bot.delete_due_messages_async()
    assert deleted(study) == []

    clock.advance(minutes=2)
    await bot.delete_due_messages_async()
    assert deleted(study) == [(101, daily_link)]

    # deleted once only
    await bot.delete_due_messages_async()
    assert deleted(study) == [(101, daily_link)]


@pytest.mark.asyncio
async def test_links_that_became_due_while_the_bot_was_down_are_deleted_at_startup(
    tmp_path, config_dict, monkeypatch, clock
):
    study = make_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    await study.send_daily()
    await study.send_end()
    daily_link, end_link = sent_link_ids(study, 101)[1:]

    await restart(study, monkeypatch)
    clock.advance(hours=5)  # bot was down for 5 hours
    await bot.delete_due_messages_async()

    assert sorted(deleted(study)) == sorted([(101, daily_link), (101, end_link)])


@pytest.mark.asyncio
async def test_links_older_than_48_hours_are_not_deleted_but_reported(
    tmp_path, config_dict, monkeypatch, clock, caplog
):
    study = make_study(tmp_path, config_dict, monkeypatch)
    for chat_id in (101, 102):
        await study.subscribe(chat_id)
    await study.send_daily()

    await restart(study, monkeypatch)
    clock.advance(hours=49)
    caplog.set_level(logging.WARNING)
    await bot.delete_due_messages_async()

    assert deleted(study) == []
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].startswith("2 message(s) could not be deleted because they were sent more than 48 hours ago")
    # not reported again at the next check
    caplog.clear()
    await bot.delete_due_messages_async()
    assert caplog.records == []


@pytest.mark.asyncio
async def test_network_error_keeps_the_deletion_for_the_next_check(tmp_path, config_dict, monkeypatch, clock):
    study = make_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    await study.send_daily()
    daily_link = sent_link_ids(study, 101)[-1]
    clock.advance(minutes=61)

    study.telegram.delete_message.side_effect = [TimedOut(), None]
    await bot.delete_due_messages_async()
    await bot.delete_due_messages_async()

    assert deleted(study) == [(101, daily_link), (101, daily_link)]
    study.telegram.delete_message.side_effect = None
    await bot.delete_due_messages_async()
    assert len(deleted(study)) == 2  # succeeded on the second try, nothing left


@pytest.mark.parametrize("error", [BadRequest("Message to delete not found"), Forbidden("bot was blocked by the user")])
@pytest.mark.asyncio
async def test_messages_that_are_gone_or_blocked_are_not_retried(tmp_path, config_dict, monkeypatch, clock, error):
    study = make_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    await study.send_daily()
    clock.advance(minutes=61)

    study.telegram.delete_message.side_effect = error
    await bot.delete_due_messages_async()
    await bot.delete_due_messages_async()

    assert len(deleted(study)) == 1


@pytest.mark.asyncio
async def test_old_entry_without_send_time_that_telegram_refuses_is_reported(
    tmp_path, config_dict, monkeypatch, clock, caplog
):
    study = make_study(tmp_path, config_dict, monkeypatch)
    with study.db_handler.create_connection() as connection:  # entry from an older version
        connection.execute("INSERT INTO messages (chat_id, message_id, type, delete_at) "
                           "VALUES (5, 50, 'SUBSCRIBE', '2000-01-01 00:00:00')")
    study.telegram.delete_message.side_effect = BadRequest("Message can't be deleted for everyone")
    caplog.set_level(logging.WARNING)

    await bot.delete_due_messages_async()

    assert deleted(study) == [(5, 50)]
    assert any("1 message(s) could not be deleted" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_start_link_is_deleted_by_timer_or_at_the_deadline_whichever_comes_first(
    tmp_path, config_dict, monkeypatch, clock
):
    study = make_study(
        tmp_path, config_dict, monkeypatch,
        start_DeleteLinkTimer=True, start_DeleteDelayMinutes=240, start_DeleteLinkAtSubscriptionDeadline=True,
    )
    # the deadline of the study fixture is one day ahead, so the 4-hour timer comes first
    await study.subscribe(101)
    start_link = sent_link_ids(study, 101)[0]

    await restart(study, monkeypatch)
    clock.advance(hours=3, minutes=59)
    await bot.delete_due_messages_async()
    assert deleted(study) == []
    clock.advance(minutes=2)
    await bot.delete_due_messages_async()
    assert deleted(study) == [(101, start_link)]


@pytest.mark.asyncio
async def test_start_link_and_questions_are_deleted_at_the_deadline_after_downtime(
    tmp_path, config_dict, monkeypatch, clock
):
    study = make_study(tmp_path, config_dict, monkeypatch, start_DeleteLinkAtSubscriptionDeadline=True)
    context = study.context()
    monkeypatch.setattr(study.config_handler.config, "useTimeCalculation", True)
    monkeypatch.setattr(study.config_handler.config, "timeCalculationSettings", SimpleNamespace(
        daily_DelayMinutesAfterWakeup=1, daily_SurveysPerDay=1, daily_DelayMinutesBetweenSurveys=1,
        end_DelayMinutesAfterWakeup=1, end_SurveysPerDay=1, end_DelayMinutesBetweenSurveys=1))
    await bot.subscribe(study.update(101), context)  # asks for the wake-up time
    question = len(study.telegram.sent)
    await bot.subscribe_wakeup_time(study.update(101, "07:00"), context)
    start_link = len(study.telegram.sent)

    await restart(study, monkeypatch)
    deadline = study.config_handler.config.subscription_deadline
    clock.advance(seconds=(deadline - datetime.now()).total_seconds() + 3600)  # deadline passed while down
    await bot.delete_due_messages_async()

    assert sorted(deleted(study)) == [(101, question), (101, start_link)]


@pytest.mark.asyncio
async def test_new_link_only_deletes_previous_links_of_its_own_type(tmp_path, config_dict, monkeypatch, clock):
    study = make_study(
        tmp_path, config_dict, monkeypatch,
        daily_DeleteLinkTimer=False, end_DeleteLinkTimer=False, end_DeleteLinkAtNewLink=True,
    )
    await study.subscribe(101)
    await bot.send_survey(study.update(101, "/survey"), study.context())  # an earlier daily link
    await study.send_daily()

    assert deleted(study) == []  # daily links are not deleted: only end links are set to "at new link"

    await study.send_end()
    first_end = sent_link_ids(study, 101)[-1]
    await bot.send_notification_broadcast_async(SurveyType.END, "end-2", study.end_date_str)
    assert deleted(study) == [(101, first_end)]


@pytest.mark.asyncio
async def test_rejection_notice_is_deleted_after_a_minute_also_after_a_restart(
    tmp_path, config_dict, monkeypatch, clock
):
    study = make_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    await study.subscribe(101)  # "already subscribed"
    notice = len(study.telegram.sent)

    await restart(study, monkeypatch)
    clock.advance(minutes=2)
    await bot.delete_due_messages_async()

    assert deleted(study) == [(101, notice)]


@pytest.mark.asyncio
async def test_planned_deletion_still_happens_after_unsubscribing(tmp_path, config_dict, monkeypatch, clock):
    study = make_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    await study.send_daily()
    daily_link = sent_link_ids(study, 101)[-1]
    await bot.unsubscribe(study.update(101, "/unsubscribe"), study.context())

    clock.advance(minutes=61)
    await bot.delete_due_messages_async()

    assert deleted(study) == [(101, daily_link)]


@pytest.mark.asyncio
async def test_end_reminder_answer_works_when_the_question_can_no_longer_be_deleted(
    tmp_path, config_dict, monkeypatch, clock
):
    study = make_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    study.telegram.clear()
    study.telegram.delete_message.side_effect = BadRequest("Message can't be deleted for everyone")

    query = SimpleNamespace(answer=AsyncMock(), data=bot.ER_NO + "+" + study.end_date_str,
                            message=SimpleNamespace(message_id=77))
    await bot.handle_end_survey_reminder_callback(
        SimpleNamespace(effective_chat=SimpleNamespace(id=101), callback_query=query), study.context())

    assert len(study.telegram.urls_for(101)) == 1  # the end link was still sent


def test_startup_schedules_the_regular_check_and_plans_old_question_deletions(
    tmp_path, config_dict, monkeypatch, clock
):
    study = make_study(tmp_path, config_dict, monkeypatch, start_DeleteLinkAtSubscriptionDeadline=True)
    study.db_handler.insert_message_id(5, 50, SurveyType.SUBSCRIBE)  # remembered by an older version
    scheduler = Mock()
    monkeypatch.setattr(bot, "scheduler", scheduler)

    bot.schedule_notifications()

    job = scheduler.add_job.call_args
    assert job.args[0] is bot.delete_due_messages
    assert job.kwargs["seconds"] == bot.DELETION_CHECK_SECONDS
    assert job.kwargs["next_run_time"] <= bot.datetime.now()  # first check right at startup
    deadline = study.config_handler.config.subscription_deadline
    assert study.db_handler.get_due_message_deletions(deadline) == [(5, 50, study.db_handler.get_tracked_messages(
        [5], SurveyType.SUBSCRIBE)[0][2])]


@pytest.mark.parametrize("settings, expected", [
    ({"daily_DeleteDelayMinutes": 2880}, "daily_DeleteDelayMinutes' is 2880 minutes"),
    ({"end_DeleteDelayMinutes": 5000}, "end_DeleteDelayMinutes' is 2880 minutes"),
    ({"start_DeleteLinkTimer": True, "start_DeleteDelayMinutes": 3000}, "start_DeleteDelayMinutes"),
])
def test_startup_warns_about_delays_beyond_telegrams_limit(
    tmp_path, config_dict, monkeypatch, caplog, settings, expected
):
    make_study(tmp_path, config_dict, monkeypatch, **settings)
    monkeypatch.setattr(bot, "scheduler", Mock())
    caplog.set_level(logging.WARNING)

    bot.schedule_notifications()

    assert any(expected in r.getMessage() for r in caplog.records)


def test_startup_warns_when_the_deadline_is_more_than_48_hours_away(tmp_path, config_dict, monkeypatch, caplog):
    study = make_study(tmp_path, config_dict, monkeypatch, start_DeleteLinkAtSubscriptionDeadline=True)
    monkeypatch.setattr(study.config_handler.config, "subscription_deadline", datetime.now() + timedelta(days=5))
    monkeypatch.setattr(bot, "scheduler", Mock())
    caplog.set_level(logging.WARNING)

    bot.schedule_notifications()

    assert any("more than 48 hours before the subscription deadline" in r.getMessage() for r in caplog.records)


def test_no_warnings_for_settings_within_the_limit(tmp_path, config_dict, monkeypatch, caplog):
    make_study(tmp_path, config_dict, monkeypatch)
    monkeypatch.setattr(bot, "scheduler", Mock())
    caplog.set_level(logging.WARNING)

    bot.schedule_notifications()

    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
