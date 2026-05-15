"""
Copyright: (c) 2020, Michael Barthelmäs, Marcel Killinger, Johannes Keller
GNU General Public License v3.0 (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

This file is part of Telegram Survey Bot.

Telegram Survey Bot is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Telegram Survey Bot is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Telegram Survey Bot.  If not, see <http://www.gnu.org/licenses/>.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from bot_utils.bot_enums import EndUrlDistribution


@dataclass
class DayCalculationSettings:
    daily_SurveyDays: list[int]
    end_SurveyDays: list[int]


@dataclass
class TimeCalculationSettings:
    daily_DelayMinutesAfterWakeup: int
    daily_SurveysPerDay: int
    daily_DelayMinutesBetweenSurveys: int
    end_DelayMinutesAfterWakeup: int
    end_SurveysPerDay: int
    end_DelayMinutesBetweenSurveys: int


@dataclass
class LinkDeletionSettings:
    start_DeleteLinkAtSubscriptionDeadline: bool
    start_DeleteLinkTimer: bool
    start_DeleteDelayMinutes: int
    daily_DeleteLinkAtNewLink: bool
    daily_DeleteLinkTimer: bool
    daily_DeleteDelayMinutes: int
    end_DeleteLinkAtNewLink: bool
    end_DeleteLinkTimer: bool
    end_DeleteDelayMinutes: int


@dataclass
class RandomTimeShiftSettings:
    daily_RandomTimeShiftMinutes: int
    end_RandomTimeShiftMinutes: int


@dataclass
class Urls:
    start_url: list[str]
    daily_url: list[str]
    end_url: list[list[str]]
    end_url_distribution: EndUrlDistribution | str

    def __post_init__(self) -> None:
        if isinstance(self.end_url_distribution, str):
            self.end_url_distribution = EndUrlDistribution[self.end_url_distribution]

from dataclasses import dataclass


@dataclass
class Texts:
    welcome: str
    subscribe: str
    subscribe_early: str
    subscribe_late: str
    subscribe_already: str
    subscribe_max_participants: str
    subscribe_wakeup_time: str
    subscribe_condition: str
    subscribe_timezone: str
    unsubscribe: str
    daily_reminder: str
    end_reminder: str
    survey_reply: str
    endSurveyReminder: str
    endSurveyReminderYes: str
    endSurveyReminderNo: str


@dataclass
class Help:
    helpEnabled: bool
    help_text: str
    surveyCommandHelp: str


@dataclass
class Config:
    api_token: str
    subscription_start_date: datetime | str
    subscription_deadline: datetime | str
    daily_dates: list[datetime | str]
    daily_times: list[list[time | str]]
    end_dates: list[datetime | str]
    end_times: list[list[time | str]]
    useTimeZoneCalculation: bool
    useDayCalculation: bool
    dayCalculationSettings: DayCalculationSettings | dict
    useTimeCalculation: bool
    timeCalculationSettings: TimeCalculationSettings | dict
    linkDeletionSettings: LinkDeletionSettings | dict
    randomTimeShiftSettings: RandomTimeShiftSettings | dict
    endSurveyReminderEnabled: bool
    endSurveyReminderDelayHours: int
    participantsEnterCondition: bool
    uniqueConditions: bool
    urls: Urls | dict
    surveyCommandEnabled: bool
    texts: Texts | dict
    help: Help | dict

    def __post_init__(self) -> None:
        if isinstance(self.subscription_start_date, str):
            self.subscription_start_date = datetime.strptime(self.subscription_start_date, "%Y-%m-%d %H:%M")

        if isinstance(self.subscription_deadline, str):
            self.subscription_deadline = datetime.strptime(self.subscription_deadline, "%Y-%m-%d %H:%M")

        self.daily_dates = [
            datetime.fromisoformat(date_str) if isinstance(date_str, str) else date_str
            for date_str in self.daily_dates
        ]

        self.daily_times = [
            [
                time.fromisoformat(time_str) if isinstance(time_str, str) else time_str
                for time_str in time_list
            ]
            for time_list in self.daily_times
        ]

        self.end_dates = [
            datetime.fromisoformat(date_str) if isinstance(date_str, str) else date_str
            for date_str in self.end_dates
        ]

        self.end_times = [
            [
                time.fromisoformat(time_str) if isinstance(time_str, str) else time_str
                for time_str in time_list
            ]
            for time_list in self.end_times
        ]

        if isinstance(self.dayCalculationSettings, dict):
            self.dayCalculationSettings = DayCalculationSettings(**self.dayCalculationSettings)

        if isinstance(self.timeCalculationSettings, dict):
            self.timeCalculationSettings = TimeCalculationSettings(**self.timeCalculationSettings)

        if isinstance(self.linkDeletionSettings, dict):
            self.linkDeletionSettings = LinkDeletionSettings(**self.linkDeletionSettings)

        if isinstance(self.randomTimeShiftSettings, dict):
            self.randomTimeShiftSettings = RandomTimeShiftSettings(**self.randomTimeShiftSettings)

        if isinstance(self.urls, dict):
            self.urls = Urls(**self.urls)

        if isinstance(self.texts, dict):
            self.texts = Texts(**self.texts)

        if isinstance(self.help, dict):
            self.help = Help(**self.help)