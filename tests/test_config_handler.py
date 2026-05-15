import json

import pytest

import bot_utils.config_handler as config_handler_module
from bot_utils.bot_enums import SurveyType
from bot_utils.config_handler import ConfigHandler


def make_config_dict(**overrides):
    data = {
        "api_token": "dummy-token",
        "subscription_start_date": "2026-05-15 08:00",
        "subscription_deadline": "2026-05-20 20:00",
        "daily_dates": ["2026-05-16"],
        "daily_times": [["09:00"]],
        "end_dates": ["2026-05-18"],
        "end_times": [["18:00"]],
        "useTimeZoneCalculation": False,
        "useDayCalculation": False,
        "dayCalculationSettings": {
            "daily_SurveyDays": [1],
            "end_SurveyDays": [3],
        },
        "useTimeCalculation": False,
        "timeCalculationSettings": {
            "daily_DelayMinutesAfterWakeup": 30,
            "daily_SurveysPerDay": 1,
            "daily_DelayMinutesBetweenSurveys": 60,
            "end_DelayMinutesAfterWakeup": 30,
            "end_SurveysPerDay": 1,
            "end_DelayMinutesBetweenSurveys": 60,
        },
        "linkDeletionSettings": {
            "start_DeleteLinkAtSubscriptionDeadline": False,
            "start_DeleteLinkTimer": False,
            "start_DeleteDelayMinutes": 10,
            "daily_DeleteLinkAtNewLink": False,
            "daily_DeleteLinkTimer": False,
            "daily_DeleteDelayMinutes": 10,
            "end_DeleteLinkAtNewLink": False,
            "end_DeleteLinkTimer": False,
            "end_DeleteDelayMinutes": 10,
        },
        "randomTimeShiftSettings": {
            "daily_RandomTimeShiftMinutes": 0,
            "end_RandomTimeShiftMinutes": 0,
        },
        "endSurveyReminderEnabled": False,
        "endSurveyReminderDelayHours": 1,
        "participantsEnterCondition": False,
        "uniqueConditions": False,
        "urls": {
            "start_url": [
                "https://example.com/start-a",
                "https://example.com/start-b",
            ],
            "daily_url": [
                "https://example.com/daily-a",
                "https://example.com/daily-b",
            ],
            "end_url": [
                ["https://example.com/end-a"],
                ["https://example.com/end-b"],
            ],
            "end_url_distribution": "NONE",
        },
        "surveyCommandEnabled": True,
        "texts": {
            "welcome": "Welcome",
            "subscribe": "Subscribe",
            "subscribe_early": "Too early",
            "subscribe_late": "Too late",
            "subscribe_already": "Already subscribed",
            "subscribe_max_participants": "Full",
            "subscribe_wakeup_time": "Wakeup time?",
            "subscribe_condition": "Condition?",
            "subscribe_timezone": "Timezone?",
            "unsubscribe": "Unsubscribed",
            "daily_reminder": "Daily reminder",
            "end_reminder": "End reminder",
            "survey_reply": "Survey reply",
            "endSurveyReminder": "End survey reminder",
            "endSurveyReminderYes": "Yes",
            "endSurveyReminderNo": "No",
        },
        "help": {
            "helpEnabled": True,
            "help_text": "Help",
            "surveyCommandHelp": "Survey help",
        },
    }

    data.update(overrides)
    return data


@pytest.fixture
def config_handler(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(make_config_dict()),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_handler_module, "CONFIG_FILE", config_file)

    return ConfigHandler()


def test_loads_config_file(config_handler):
    assert config_handler.config.api_token == "dummy-token"
    assert config_handler.config.texts.welcome == "Welcome"


def test_get_condition_count(config_handler):
    assert config_handler.get_condition_count() == 2


def test_get_condition_returns_valid_condition_index(config_handler):
    for _ in range(100):
        condition = config_handler.get_condition()
        assert condition in (0, 1)


def test_get_url_for_subscribe(config_handler):
    assert (
        config_handler.get_url(SurveyType.SUBSCRIBE, condition=1)
        == "https://example.com/start-b"
    )


def test_get_url_for_daily(config_handler):
    assert (
        config_handler.get_url(SurveyType.DAILY, condition=1)
        == "https://example.com/daily-b"
    )


def test_get_url_for_end(config_handler):
    assert (
        config_handler.get_url(SurveyType.END, condition=1, end_distribution=0)
        == "https://example.com/end-b"
    )


def test_get_message_for_daily(config_handler):
    assert config_handler.get_message(SurveyType.DAILY) == "Daily reminder"


def test_get_message_for_end(config_handler):
    assert config_handler.get_message(SurveyType.END) == "End reminder"


def test_get_message_raises_for_subscribe(config_handler):
    with pytest.raises(ValueError):
        config_handler.get_message(SurveyType.SUBSCRIBE)


def test_invalid_config_raises(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"

    invalid_config = make_config_dict(
        subscription_start_date="2026-05-21 08:00",
        subscription_deadline="2026-05-20 20:00",
    )

    config_file.write_text(
        json.dumps(invalid_config),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_handler_module, "CONFIG_FILE", config_file)

    with pytest.raises(Exception):
        ConfigHandler()