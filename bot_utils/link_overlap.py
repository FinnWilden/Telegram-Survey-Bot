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

Finds survey links that are still shown in the chat when the next survey link arrives,
because their deletion settings only remove them later.

The links of one example participant are calculated from the config. With
useTimeCalculation, the participant subscribes at the wake-up time they enter, which is
how a test run works and the earliest a participant usually subscribes. Without it, the
subscription time is not known in advance, so the start link is not checked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from bot_utils.bot_utils import TimeSettings
from bot_utils.config import Config
from bot_utils.time_util import TimeUtil

EXAMPLE_WAKEUP_TIME = time(8, 0)

START = "start link"
DAILY = "daily link"
END = "end link"


@dataclass(frozen=True)
class LinkOverlap:
    link: str
    next_link: str
    next_link_after: timedelta   # time between the two links
    deleted_after: timedelta     # when the first link is deleted, counted from its sending

    def describe(self) -> str:
        return (
            f"{self.link} -> {self.next_link}: the {self.link} is deleted {_minutes(self.deleted_after)} "
            f"after sending, the next link comes after {_minutes(self.next_link_after)}"
        )


def _minutes(value: timedelta) -> str:
    minutes = round(value.total_seconds() / 60)
    if minutes >= 60 * 24 and minutes % (60 * 24) == 0:
        return f"{minutes // (60 * 24)} day(s)"
    if minutes >= 60 and minutes % 60 == 0:
        return f"{minutes // 60} h"
    return f"{minutes} min"


def _survey_times(config: Config, today: datetime, daily: bool) -> list[datetime]:
    if config.useDayCalculation:
        days = (config.dayCalculationSettings.daily_SurveyDays if daily
                else config.dayCalculationSettings.end_SurveyDays)
        dates = [today + timedelta(days=day) for day in days]
    else:
        dates = list(config.daily_dates if daily else config.end_dates)

    if config.useTimeCalculation:
        settings = config.timeCalculationSettings
        times = TimeSettings(
            EXAMPLE_WAKEUP_TIME,
            settings.daily_DelayMinutesAfterWakeup if daily else settings.end_DelayMinutesAfterWakeup,
            settings.daily_SurveysPerDay if daily else settings.end_SurveysPerDay,
            settings.daily_DelayMinutesBetweenSurveys if daily else settings.end_DelayMinutesBetweenSurveys,
        )
        return TimeUtil.generate_date_time_list(dates, times)

    return TimeUtil.generate_date_time_list(dates, config.daily_times if daily else config.end_times)


def example_links(config: Config, today: datetime | None = None) -> list[tuple[datetime, str]]:
    """
    The survey links of the example participant in sending order, as (time, kind).
    """
    today = (today or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    links = [(moment, DAILY) for moment in _survey_times(config, today, daily=True)]
    links += [(moment, END) for moment in _survey_times(config, today, daily=False)]
    if config.useTimeCalculation:
        links.append((TimeUtil.get_date_time(today, EXAMPLE_WAKEUP_TIME), START))
    order = {START: 0, DAILY: 1, END: 2}
    return sorted(links, key=lambda link: (link[0], order[link[1]]))


def _deletion_time(config: Config, links: list[tuple[datetime, str]], index: int) -> datetime | None:
    """
    When the link at index is deleted according to the settings, or None if never.
    """
    sent_at, kind = links[index]
    settings = config.linkDeletionSettings
    candidates: list[datetime] = []

    prefix = {START: "start", DAILY: "daily", END: "end"}[kind]
    if getattr(settings, f"{prefix}_DeleteLinkTimer"):
        candidates.append(sent_at + timedelta(minutes=getattr(settings, f"{prefix}_DeleteDelayMinutes")))
    if kind == START and settings.start_DeleteLinkAtSubscriptionDeadline:
        candidates.append(max(sent_at, config.subscription_deadline))
    if kind != START and getattr(settings, f"{prefix}_DeleteLinkAtNewLink"):
        candidates += [moment for moment, other in links[index + 1:] if other == kind][:1]

    return min(candidates) if candidates else None


def find_link_overlaps(config: Config, today: datetime | None = None) -> list[LinkOverlap]:
    """
    Every kind of link that is deleted only after the next link arrived, once per pair of
    link kinds with the largest overlap. Empty when deleteOldLinksBeforeNewLink is on, because
    then each link is deleted right before the next one is sent.

    Links that are never deleted are not reported: keeping them is a choice, not an overlap.
    """
    if config.linkDeletionSettings.deleteOldLinksBeforeNewLink:
        return []

    links = example_links(config, today)
    overlaps: dict[tuple[str, str], LinkOverlap] = {}
    for index in range(len(links) - 1):
        sent_at, kind = links[index]
        next_at, next_kind = links[index + 1]
        deleted_at = _deletion_time(config, links, index)
        if deleted_at is None or deleted_at <= next_at:
            continue

        overlap = LinkOverlap(kind, next_kind, next_at - sent_at, deleted_at - sent_at)
        known = overlaps.get((kind, next_kind))
        if known is None or overlap.deleted_after - overlap.next_link_after > known.deleted_after - known.next_link_after:
            overlaps[(kind, next_kind)] = overlap

    return list(overlaps.values())
