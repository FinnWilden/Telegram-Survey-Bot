"""
End-to-end tests for participant-number links.

These run the real bot handlers against a real config file, a real SQLite
database and the real ScheduleUtil. Only Telegram and the APScheduler thread
are replaced by fakes, so every link a participant would receive is checked.
"""
import itertools
import re
import sqlite3
from datetime import datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from rich.console import Console
from telegram.ext import ConversationHandler

import bot
import bot_utils.db_handler as db_module
from bot_utils.bot_enums import SurveyType
from bot_utils.config_handler import ConfigHandler
from bot_utils.console_dashboard import ConsoleDashboard
from bot_utils.db_handler import DbHandler
from bot_utils.schedule_util import ScheduleUtil


START_URL = "https://survey.example/start?pid={participant}&src=bot"
DAILY_URL = "https://survey.example/daily/{participant}"
END_URL = "https://survey.example/end?pid={participant}"


def link(template, number):
    return template.replace("{participant}", number)


class FakeTelegramBot:
    """
    Records every message instead of sending it to Telegram.
    """

    def __init__(self):
        self._message_ids = itertools.count(1)
        self.sent = []
        self.send_message = AsyncMock(side_effect=self._send_message)
        self.delete_message = AsyncMock()

    async def _send_message(self, chat_id, text, reply_markup=None):
        url = reply_markup.inline_keyboard[0][0].url if reply_markup is not None else None
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, url=url))
        return SimpleNamespace(message_id=next(self._message_ids))

    def urls_for(self, chat_id):
        return [message.url for message in self.sent if message.chat_id == chat_id and message.url]

    def clear(self):
        self.sent.clear()


class Study:
    """
    A running bot instance with a fake Telegram connection.
    """

    def __init__(self, tmp_path, config_dict, monkeypatch, **overrides):
        now = datetime.now()
        self.daily_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        self.end_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
        self.daily_date_str = self.daily_date + "-09:00"
        self.end_date_str = self.end_date + "-18:00"

        data = config_dict(
            subscription_start_date=(now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
            subscription_deadline=(now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
            daily_dates=[self.daily_date],
            daily_times=[["09:00"]],
            end_dates=[self.end_date],
            end_times=[["18:00"]],
            useParticipantNumbers=True,
            participantNumberDigits=3,
            urls={
                "start_url": [START_URL],
                "daily_url": [DAILY_URL],
                "end_url": [END_URL],  # plain url, no brackets
                "end_url_distribution": "NONE",
            },
        )
        data.update(overrides)

        self.config_file = tmp_path / "study.yml"
        self.config_file.write_text(yaml.safe_dump(data), encoding="utf-8")
        monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "study.db")

        self.config_handler = ConfigHandler(config_file=self.config_file)
        self.db_handler = DbHandler()
        self.schedule_util = ScheduleUtil(Mock(), self.config_handler.config, self.db_handler)
        self.telegram = FakeTelegramBot()

        monkeypatch.setattr(bot, "config_handler", self.config_handler, raising=False)
        monkeypatch.setattr(bot, "db_handler", self.db_handler, raising=False)
        monkeypatch.setattr(bot, "schedule_util", self.schedule_util, raising=False)
        monkeypatch.setattr(bot, "scheduler", Mock(), raising=False)
        monkeypatch.setattr(bot, "application", SimpleNamespace(bot=self.telegram), raising=False)

    def context(self):
        return SimpleNamespace(bot=self.telegram, user_data={})

    @staticmethod
    def update(chat_id, text="/subscribe"):
        return SimpleNamespace(
            effective_chat=SimpleNamespace(id=chat_id),
            message=SimpleNamespace(text=text, message_id=1),
            callback_query=None,
        )

    async def subscribe(self, chat_id):
        return await bot.subscribe(self.update(chat_id), self.context())

    def number(self, chat_id):
        return self.db_handler.get_participant_number(chat_id)

    def condition(self, chat_id):
        return self.db_handler.get_condition(chat_id)

    async def send_daily(self):
        await bot.send_notification_broadcast_async(SurveyType.DAILY, "daily-job", self.daily_date_str)

    async def send_end(self):
        await bot.send_notification_broadcast_async(SurveyType.END, "end-job", self.end_date_str)


@pytest.fixture
def study(tmp_path, config_dict, monkeypatch):
    return Study(tmp_path, config_dict, monkeypatch)


@pytest.mark.asyncio
async def test_every_link_of_a_participant_uses_the_same_unique_number(study):
    participants = [101, 102, 103]
    for chat_id in participants:
        assert await study.subscribe(chat_id) == ConversationHandler.END

    await study.send_daily()
    await study.send_end()

    numbers = {chat_id: study.number(chat_id) for chat_id in participants}
    assert len(set(numbers.values())) == 3
    for chat_id, number in numbers.items():
        assert re.fullmatch(r"\d{3}", number)
        assert study.telegram.urls_for(chat_id) == [
            link(START_URL, number),
            link(DAILY_URL, number),
            link(END_URL, number),
        ]

    study.telegram.clear()
    await bot.send_survey(study.update(101, "/survey"), study.context())
    assert study.telegram.urls_for(101) == [link(DAILY_URL, numbers[101])]


@pytest.mark.asyncio
async def test_no_participant_is_ever_rejected_numbers_get_longer_instead(tmp_path, config_dict, monkeypatch):
    # one digit only has the nine numbers 1-9
    study = Study(tmp_path, config_dict, monkeypatch, participantNumberDigits=1)
    participants = list(range(101, 116))

    for chat_id in participants:
        assert await study.subscribe(chat_id) == ConversationHandler.END

    numbers = [study.number(chat_id) for chat_id in participants]
    assert "Full" not in [message.text for message in study.telegram.sent]
    assert len(set(numbers)) == 15
    assert sorted(number for number in numbers if len(number) == 1) == [str(n) for n in range(1, 10)]
    assert all(len(number) == 2 for number in numbers if len(number) != 1)
    for chat_id, number in zip(participants, numbers):
        assert study.telegram.urls_for(chat_id) == [link(START_URL, number)]


@pytest.mark.asyncio
async def test_participant_keeps_number_after_unsubscribing_and_subscribing_again(study):
    await study.subscribe(101)
    number_before = study.number(101)

    await bot.unsubscribe(study.update(101, "/unsubscribe"), study.context())
    study.telegram.clear()
    assert await study.subscribe(101) == ConversationHandler.END

    assert study.telegram.urls_for(101) == [link(START_URL, number_before)]


@pytest.mark.asyncio
async def test_number_survives_a_bot_restart(study, monkeypatch):
    await study.subscribe(101)
    number = study.number(101)

    monkeypatch.setattr(bot, "db_handler", DbHandler())
    await study.send_daily()

    assert study.telegram.urls_for(101)[-1] == link(DAILY_URL, number)


@pytest.mark.asyncio
async def test_number_stays_the_same_when_digits_are_changed_later(study, monkeypatch):
    await study.subscribe(101)
    old_number = study.number(101)

    data = yaml.safe_load(study.config_file.read_text(encoding="utf-8"))
    data["participantNumberDigits"] = 6
    study.config_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(bot, "config_handler", ConfigHandler(config_file=study.config_file))

    await study.subscribe(102)
    await study.send_daily()

    assert study.telegram.urls_for(101)[-1] == link(DAILY_URL, old_number)
    assert len(study.number(102)) == 6
    assert int(study.number(102)) != int(old_number)


@pytest.mark.asyncio
async def test_end_reminder_no_button_sends_end_link_with_number(study):
    await study.subscribe(101)
    number = study.number(101)
    study.telegram.clear()

    query = SimpleNamespace(
        answer=AsyncMock(),
        data=bot.ER_NO + "+" + study.end_date_str,
        message=SimpleNamespace(message_id=55),
    )
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=101), callback_query=query)

    await bot.handle_end_survey_reminder_callback(update, study.context())

    assert study.telegram.urls_for(101) == [link(END_URL, number)]


@pytest.mark.asyncio
async def test_number_is_drawn_with_the_first_link_of_a_multi_step_subscription(tmp_path, config_dict, monkeypatch):
    study = Study(tmp_path, config_dict, monkeypatch, useTimeZoneCalculation=True)
    context = study.context()

    assert await bot.subscribe(study.update(101), context) == bot.TIMEZONE_STATE
    assert study.number(101) is None  # an aborted subscription uses up no number

    local_time = datetime.now().strftime("%Y.%m.%d-%H:%M")
    assert await bot.subscribe_timezone(study.update(101, local_time), context) == ConversationHandler.END

    number = study.number(101)
    assert study.telegram.urls_for(101) == [link(START_URL, number)]


@pytest.mark.asyncio
async def test_subscribers_from_before_the_feature_get_a_number_on_their_first_link(study):
    # subscribed while the feature was off: schedule entries exist, but no number
    study.schedule_util.add_new_subscriber(201, 0, bot.send_notification_broadcast)
    assert study.number(201) is None

    await study.send_daily()

    assert study.telegram.urls_for(201) == [link(DAILY_URL, study.number(201))]


@pytest.mark.asyncio
async def test_broadcast_continues_when_one_participant_number_cannot_be_stored(study, monkeypatch):
    study.schedule_util.add_new_subscriber(201, 0, bot.send_notification_broadcast)
    study.schedule_util.add_new_subscriber(202, 0, bot.send_notification_broadcast)
    real_assign = study.db_handler.assign_participant_number

    def assign(chat_id, digits, rng=None):
        if chat_id == 201:
            raise sqlite3.OperationalError("database is locked")
        return real_assign(chat_id, digits, rng)

    monkeypatch.setattr(study.db_handler, "assign_participant_number", assign)

    await study.send_daily()

    assert [message.chat_id for message in study.telegram.sent] == [202]


@pytest.mark.asyncio
async def test_several_conditions_keep_their_own_urls(tmp_path, config_dict, monkeypatch):
    urls = {
        "start_url": ["https://a.example/start/{participant}", "https://b.example/start/{participant}"],
        "daily_url": ["https://a.example/daily?id={participant}", "https://b.example/daily?id={participant}"],
        "end_url": ["https://a.example/end/{participant}", "https://b.example/end/{participant}"],
        "end_url_distribution": "NONE",
    }
    study = Study(tmp_path, config_dict, monkeypatch, urls=urls, uniqueConditions=True)

    await study.subscribe(101)
    await study.subscribe(102)
    await study.send_daily()

    assert {study.condition(101), study.condition(102)} == {0, 1}
    for chat_id in (101, 102):
        condition = study.condition(chat_id)
        number = study.number(chat_id)
        assert study.telegram.urls_for(chat_id) == [
            link(urls["start_url"][condition], number),
            link(urls["daily_url"][condition], number),
        ]


@pytest.mark.asyncio
async def test_end_url_lists_still_work_for_end_url_distribution(tmp_path, config_dict, monkeypatch):
    now = datetime.now()
    end_day_1 = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    end_day_2 = (now + timedelta(days=3)).strftime("%Y-%m-%d")
    study = Study(
        tmp_path,
        config_dict,
        monkeypatch,
        end_dates=[end_day_1, end_day_2],
        end_times=[["18:00"], ["18:00"]],
        urls={
            "start_url": [START_URL],
            "daily_url": [DAILY_URL],
            "end_url": [["https://survey.example/end1/{participant}", "https://survey.example/end2/{participant}"]],
            "end_url_distribution": "DAY",
        },
    )

    await study.subscribe(101)
    await bot.send_notification_broadcast_async(SurveyType.END, "end-1", end_day_1 + "-18:00")
    await bot.send_notification_broadcast_async(SurveyType.END, "end-2", end_day_2 + "-18:00")

    number = study.number(101)
    assert study.telegram.urls_for(101)[1:] == [
        f"https://survey.example/end1/{number}",
        f"https://survey.example/end2/{number}",
    ]


@pytest.mark.asyncio
async def test_links_are_unchanged_when_feature_is_disabled(tmp_path, config_dict, monkeypatch):
    study = Study(
        tmp_path,
        config_dict,
        monkeypatch,
        useParticipantNumbers=False,
        urls={
            "start_url": ["https://survey.example/start-1"],
            "daily_url": ["https://survey.example/daily-1"],
            "end_url": ["https://survey.example/end-1"],
            "end_url_distribution": "NONE",
        },
    )

    await study.subscribe(101)
    await study.send_daily()
    await study.send_end()

    assert study.telegram.urls_for(101) == [
        "https://survey.example/start-1",
        "https://survey.example/daily-1",
        "https://survey.example/end-1",
    ]
    assert study.number(101) is None


@pytest.mark.asyncio
async def test_dashboard_shows_participant_numbers(study):
    await study.subscribe(101)
    number = study.number(101)

    console = Console(file=StringIO(), width=140, record=True)
    dashboard = ConsoleDashboard(study.db_handler, console, participant_number_digits=3)
    console.print(dashboard.render())
    summary = console.export_text()
    assert re.search(r"Nummern vergeben\s+1", summary)
    assert re.search(r"Nummernlänge\s+3 Stellen", summary)

    dashboard.view = "participants"
    console.print(dashboard.render())
    output = console.export_text()

    assert "Nr." in output
    assert re.search(rf"101\s+│\s+{number}\s+│", output)


def test_dashboard_without_participant_numbers_has_no_number_fields(study):
    console = Console(file=StringIO(), width=140, record=True)
    dashboard = ConsoleDashboard(study.db_handler, console)
    console.print(dashboard.render())
    dashboard.view = "participants"
    console.print(dashboard.render())
    output = console.export_text()

    assert "Nummern" not in output
    assert "Nr." not in output
