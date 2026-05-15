import pytest

from bot_utils.config import Config

@pytest.fixture
def config_dict():
    def _make_config_dict(**overrides):
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
                "deleteSubscriptionSetupMessages": False,
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
                "survey_not_subscribed": "You are not subscribed yet. Please send /subscribe first.",
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

    return _make_config_dict

@pytest.fixture
def config(config_dict):
    return Config(**config_dict())