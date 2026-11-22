"""
End-to-end tests for participant-number links.

These run the real bot handlers against a real config file, a real SQLite
database and the real ScheduleUtil. Only Telegram and the APScheduler thread
are replaced by fakes, so every link a participant would receive is checked.
"""
import itertools
import re
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from telegram.ext import ConversationHandler

import bot
import bot_utils.db_handler as db_module
from bot_utils.bot_enums import SurveyType
from bot_utils.config_handler import ConfigHandler
from bot_utils.db_handler import DbHandler
from bot_utils.schedule_util import ScheduleUtil


START_STEMS = [
    "https://survey.example/start?pid={participant}&c=a",
    "https://survey.example/start?pid={participant}&c=b",
]
DAILY_STEMS = ["https://survey.example/daily-a/", "https://survey.example/daily-b/"]
END_STEMS = [["https://survey.example/end-a/"], ["https://survey.example/end-b/"]]


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
            participantNumberSettings={"minNumber": 1, "maxNumber": 3, "padToDigits": 3},
            urls={
                "start_url": START_STEMS,
                "daily_url": DAILY_STEMS,
                "end_url": END_STEMS,
                "end_url_distribution": "NONE",
            },
        )
        data.update(overrides)

        config_file = tmp_path / "study.yml"
        config_file.write_text(yaml.safe_dump(data), encoding="utf-8")
        monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "study.db")

        self.config_handler = ConfigHandler(config_file=config_file)
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

    def condition(self, chat_id):
        return self.db_handler.get_condition(chat_id)


def number_in(url):
    return re.search(r"(\d{3})(?:&|/?$)", url).group(1)


@pytest.fixture
def study(tmp_path, config_dict, monkeypatch):
    return Study(tmp_path, config_dict, monkeypatch)


@pytest.mark.asyncio
async def test_every_link_of_a_participant_uses_the_same_unique_number(study):
    participants = [101, 102, 103]
    for chat_id in participants:
        assert await study.subscribe(chat_id) == ConversationHandler.END

    # start link: number at the placeholder, condition-specific stem
    numbers = {}
    for chat_id in participants:
        [start_url] = study.telegram.urls_for(chat_id)
        condition = study.condition(chat_id)
        number = study.db_handler.get_participant_number(chat_id)
        assert start_url == START_STEMS[condition].replace("{participant}", f"{number:03d}")
        numbers[chat_id] = number

    assert sorted(numbers.values()) == [1, 2, 3]

    # scheduled daily and end links: number appended to the stem
    await bot.send_notification_broadcast_async(SurveyType.DAILY, "daily-job", study.daily_date_str)
    await bot.send_notification_broadcast_async(SurveyType.END, "end-job", study.end_date_str)

    for chat_id in participants:
        condition = study.condition(chat_id)
        expected_number = f"{numbers[chat_id]:03d}"
        start_url, daily_url, end_url = study.telegram.urls_for(chat_id)
        assert daily_url == DAILY_STEMS[condition] + expected_number
        assert end_url == END_STEMS[condition][0] + expected_number
        assert {number_in(start_url), number_in(daily_url), number_in(end_url)} == {expected_number}

    # /survey command
    study.telegram.clear()
    await bot.send_survey(study.update(101, "/survey"), study.context())
    assert study.telegram.urls_for(101) == [DAILY_STEMS[study.condition(101)] + f"{numbers[101]:03d}"]


@pytest.mark.asyncio
async def test_subscription_is_rejected_when_all_numbers_are_taken(study):
    for chat_id in (101, 102, 103):
        await study.subscribe(chat_id)
    study.telegram.clear()

    assert await study.subscribe(104) == ConversationHandler.END

    assert [message.text for message in study.telegram.sent] == ["Full"]
    assert study.db_handler.get_participant_number(104) is None
    assert not study.db_handler.is_already_subscribed(104)


@pytest.mark.asyncio
async def test_participant_keeps_number_after_unsubscribing_even_when_range_is_full(study):
    for chat_id in (101, 102, 103):
        await study.subscribe(chat_id)
    number_before = study.db_handler.get_participant_number(101)

    await bot.unsubscribe(study.update(101, "/unsubscribe"), study.context())
    study.telegram.clear()
    assert await study.subscribe(101) == ConversationHandler.END

    [start_url] = study.telegram.urls_for(101)
    assert number_in(start_url) == f"{number_before:03d}"
    assert study.db_handler.get_participant_number(101) == number_before


@pytest.mark.asyncio
async def test_number_survives_a_bot_restart(study, monkeypatch):
    await study.subscribe(101)
    number = study.db_handler.get_participant_number(101)

    restarted_db_handler = DbHandler()
    monkeypatch.setattr(bot, "db_handler", restarted_db_handler)
    await bot.send_notification_broadcast_async(SurveyType.DAILY, "daily-job", study.daily_date_str)

    assert study.telegram.urls_for(101)[-1].endswith(f"{number:03d}")


@pytest.mark.asyncio
async def test_end_reminder_no_button_sends_end_link_with_number(study):
    await study.subscribe(101)
    number = study.db_handler.get_participant_number(101)
    study.telegram.clear()

    query = SimpleNamespace(
        answer=AsyncMock(),
        data=bot.ER_NO + "+" + study.end_date_str,
        message=SimpleNamespace(message_id=55),
    )
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=101), callback_query=query)

    await bot.handle_end_survey_reminder_callback(update, study.context())

    assert study.telegram.urls_for(101) == [END_STEMS[study.condition(101)][0] + f"{number:03d}"]


@pytest.mark.asyncio
async def test_multi_step_subscription_uses_number_from_first_step(tmp_path, config_dict, monkeypatch):
    study = Study(tmp_path, config_dict, monkeypatch, useTimeZoneCalculation=True)
    context = study.context()

    assert await bot.subscribe(study.update(101), context) == bot.TIMEZONE_STATE
    number = study.db_handler.get_participant_number(101)
    assert number is not None

    local_time = datetime.now().strftime("%Y.%m.%d-%H:%M")
    assert await bot.subscribe_timezone(study.update(101, local_time), context) == ConversationHandler.END

    start_url = study.telegram.urls_for(101)[-1]
    assert number_in(start_url) == f"{number:03d}"


@pytest.mark.asyncio
async def test_subscribers_from_before_the_feature_get_a_number_on_their_first_link(study):
    # subscribed while the feature was off: schedule entries exist, but no number
    study.schedule_util.add_new_subscriber(201, 0, bot.send_notification_broadcast)
    assert study.db_handler.get_participant_number(201) is None

    await bot.send_notification_broadcast_async(SurveyType.DAILY, "daily-job", study.daily_date_str)

    number = study.db_handler.get_participant_number(201)
    assert study.telegram.urls_for(201) == [DAILY_STEMS[0] + f"{number:03d}"]


@pytest.mark.asyncio
async def test_broadcast_continues_when_one_participant_cannot_get_a_number(tmp_path, config_dict, monkeypatch):
    study = Study(
        tmp_path,
        config_dict,
        monkeypatch,
        participantNumberSettings={"minNumber": 1, "maxNumber": 1},
    )
    study.schedule_util.add_new_subscriber(201, 0, bot.send_notification_broadcast)
    study.schedule_util.add_new_subscriber(202, 1, bot.send_notification_broadcast)

    await bot.send_notification_broadcast_async(SurveyType.DAILY, "daily-job", study.daily_date_str)

    sent_to = sorted(message.chat_id for message in study.telegram.sent)
    assert len(sent_to) == 1
    [received] = study.telegram.sent
    assert received.url.endswith("1")


@pytest.mark.asyncio
async def test_unique_conditions_and_participant_numbers_work_together(tmp_path, config_dict, monkeypatch):
    study = Study(
        tmp_path,
        config_dict,
        monkeypatch,
        uniqueConditions=True,
        participantNumberSettings={"minNumber": 10, "maxNumber": 99},
    )

    await study.subscribe(101)
    await study.subscribe(102)

    assert {study.condition(101), study.condition(102)} == {0, 1}
    number_101 = study.db_handler.get_participant_number(101)
    number_102 = study.db_handler.get_participant_number(102)
    assert number_101 != number_102
    assert 10 <= number_101 <= 99 and 10 <= number_102 <= 99


@pytest.mark.asyncio
async def test_links_are_unchanged_when_feature_is_disabled(tmp_path, config_dict, monkeypatch):
    study = Study(
        tmp_path,
        config_dict,
        monkeypatch,
        useParticipantNumbers=False,
        urls={
            "start_url": ["https://survey.example/start-1", "https://survey.example/start-2"],
            "daily_url": DAILY_STEMS,
            "end_url": END_STEMS,
            "end_url_distribution": "NONE",
        },
    )

    await study.subscribe(101)
    await bot.send_notification_broadcast_async(SurveyType.DAILY, "daily-job", study.daily_date_str)

    condition = study.condition(101)
    assert study.telegram.urls_for(101) == [
        ["https://survey.example/start-1", "https://survey.example/start-2"][condition],
        DAILY_STEMS[condition],
    ]
    assert study.db_handler.get_participant_number(101) is None


@pytest.mark.asyncio
async def test_dashboard_shows_participant_numbers(study):
    from io import StringIO

    from rich.console import Console

    from bot_utils.console_dashboard import ConsoleDashboard

    await study.subscribe(101)
    number = study.db_handler.get_participant_number(101)

    console = Console(file=StringIO(), width=140, record=True)
    dashboard = ConsoleDashboard(study.db_handler, console, participant_number_range=(1, 3))
    console.print(dashboard.render())
    summary = console.export_text()
    assert re.search(r"Nummern vergeben\s+1 / 3", summary)
    assert re.search(r"Nummern frei\s+2", summary)

    dashboard.view = "participants"
    console.print(dashboard.render())
    output = console.export_text()

    assert "Nr." in output
    assert re.search(rf"101\s+│\s+{number}\s+│", output)


def test_dashboard_without_participant_numbers_has_no_number_fields(study):
    from io import StringIO

    from rich.console import Console

    from bot_utils.console_dashboard import ConsoleDashboard

    console = Console(file=StringIO(), width=140, record=True)
    dashboard = ConsoleDashboard(study.db_handler, console)
    console.print(dashboard.render())
    dashboard.view = "participants"
    console.print(dashboard.render())
    output = console.export_text()

    assert "Nummern" not in output
    assert "Nr." not in output
