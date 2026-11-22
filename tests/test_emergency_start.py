from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

import bot_utils.db_handler as db_module
from bot_utils.bot_enums import SurveyType
from bot_utils.db_handler import DbHandler
from bot_utils.emergency_start import EmergencyStart


def broadcast(*args):
    pass


def reminder(*args):
    pass


@pytest.fixture
def db_handler(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "restart.db")
    return DbHandler()


@pytest.fixture
def answers(monkeypatch):
    """
    Answers typed in the terminal, in order. Records the questions that were asked.
    """
    given = []
    asked = []

    def fake_input(prompt=""):
        asked.append(prompt)
        return given.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    return SimpleAnswers(given, asked)


class SimpleAnswers:
    def __init__(self, given, asked):
        self.given = given
        self.asked = asked

    def set(self, *values):
        self.given.extend(values)


def minutes(delta):
    """A future time without seconds, like the dates stored in the database."""
    return (datetime.now() + timedelta(minutes=delta)).replace(second=0, microsecond=0)


def add_survey(db_handler, chat_id, date, survey_type=SurveyType.DAILY):
    db_handler.insert_new_subscriber_entries(chat_id, [date], survey_type, 0)


def add_reminder(db_handler, chat_ids, date):
    db_handler.insert_end_reminder_entries([(chat_id, 0, 0) for chat_id in chat_ids], date.strftime("%Y-%m-%d-%H:%M"))


def test_yes_reschedules_surveys_and_reminders_as_reminders(db_handler, answers):
    end_date, reminder_date = minutes(30), minutes(90)
    add_survey(db_handler, 1, end_date, SurveyType.END)
    add_survey(db_handler, 2, end_date, SurveyType.END)
    add_reminder(db_handler, [1, 2], reminder_date)
    schedule_util = Mock()
    answers.set("y")

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    schedule_util.add_job.assert_called_once_with(end_date, broadcast, SurveyType.END)
    schedule_util.schedule_end_survey_reminder_at.assert_called_once_with(reminder, reminder_date, [1, 2])


def test_reminder_is_never_rescheduled_as_an_end_survey(db_handler, answers):
    add_reminder(db_handler, [1], minutes(90))
    schedule_util = Mock()
    answers.set("y")

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    schedule_util.add_job.assert_not_called()


def test_only_pending_reminders_still_ask_and_get_rescheduled(db_handler, answers):
    add_reminder(db_handler, [1], minutes(90))
    schedule_util = Mock()
    answers.set("y")

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    assert len(answers.asked) == 1
    schedule_util.schedule_end_survey_reminder_at.assert_called_once()


def test_past_dates_and_reminders_are_ignored_without_asking(db_handler, answers):
    add_survey(db_handler, 1, minutes(-30))
    add_reminder(db_handler, [1], minutes(-5))
    schedule_util = Mock()

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    assert answers.asked == []
    schedule_util.add_job.assert_not_called()
    schedule_util.schedule_end_survey_reminder_at.assert_not_called()


def test_reminders_are_skipped_when_reminders_are_disabled(db_handler, answers):
    add_survey(db_handler, 1, minutes(30))
    add_reminder(db_handler, [1], minutes(90))
    schedule_util = Mock()
    answers.set("y")

    EmergencyStart(schedule_util, db_handler, broadcast, None)

    schedule_util.add_job.assert_called_once()
    schedule_util.schedule_end_survey_reminder_at.assert_not_called()


def test_no_then_yes_unsubscribes_everyone_including_reminders(db_handler, answers):
    add_survey(db_handler, 1, minutes(30))
    add_reminder(db_handler, [2], minutes(90))
    schedule_util = Mock()
    answers.set("n", "y")

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    assert len(answers.asked) == 2
    assert not db_handler.is_already_subscribed(1)
    assert not db_handler.is_already_subscribed(2)
    schedule_util.add_job.assert_not_called()


def test_no_then_no_keeps_entries_but_schedules_nothing(db_handler, answers):
    add_survey(db_handler, 1, minutes(30))
    add_reminder(db_handler, [1], minutes(90))
    schedule_util = Mock()
    answers.set("n", "n")

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    assert db_handler.is_already_subscribed(1)
    schedule_util.add_job.assert_not_called()
    schedule_util.schedule_end_survey_reminder_at.assert_not_called()


def test_invalid_answer_is_asked_again(db_handler, answers):
    add_survey(db_handler, 1, minutes(30))
    schedule_util = Mock()
    answers.set("maybe", "yes")

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    assert len(answers.asked) == 2
    schedule_util.add_job.assert_called_once()


@pytest.mark.parametrize("reminder_enabled", [True, False])
@pytest.mark.asyncio
async def test_bot_start_passes_reminder_function_only_when_reminders_are_enabled(monkeypatch, reminder_enabled):
    from types import SimpleNamespace

    import bot
    from bot_utils.console_dashboard import ConsoleDashboard

    config = SimpleNamespace(endSurveyReminderEnabled=reminder_enabled, useParticipantNumbers=False)
    monkeypatch.setattr(bot, "config_handler", SimpleNamespace(config=config), raising=False)
    monkeypatch.setattr(bot, "db_handler", Mock(), raising=False)
    monkeypatch.setattr(bot, "schedule_util", Mock(), raising=False)
    monkeypatch.setattr(bot, "scheduler", Mock(), raising=False)
    monkeypatch.setattr(bot, "schedule_notifications", Mock())
    monkeypatch.setattr(ConsoleDashboard, "is_available", staticmethod(lambda console: False))
    emergency_start = Mock()
    monkeypatch.setattr(bot, "EmergencyStart", emergency_start)

    await bot.post_init(Mock())

    args = emergency_start.call_args.args
    assert args[2] is bot.send_notification_broadcast
    assert args[3] is (bot.send_end_survey_reminder if reminder_enabled else None)


def test_without_a_terminal_open_dates_are_rescheduled_instead_of_crashing(db_handler, monkeypatch):
    add_survey(db_handler, 1, minutes(30))
    add_reminder(db_handler, [1], minutes(90))
    schedule_util = Mock()

    def no_terminal(prompt=""):
        raise EOFError  # what input() does when the bot runs as a background service

    monkeypatch.setattr("builtins.input", no_terminal)

    EmergencyStart(schedule_util, db_handler, broadcast, reminder)

    schedule_util.add_job.assert_called_once()
    schedule_util.schedule_end_survey_reminder_at.assert_called_once()
    assert db_handler.is_already_subscribed(1)


def test_database_cleanup_is_never_answered_automatically(db_handler, monkeypatch):
    add_survey(db_handler, 1, minutes(30))
    answers = iter(["n"])

    def answer_then_no_terminal(prompt=""):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", answer_then_no_terminal)

    EmergencyStart(Mock(), db_handler, broadcast, reminder)

    assert db_handler.is_already_subscribed(1)  # nothing deleted without an explicit "y"
