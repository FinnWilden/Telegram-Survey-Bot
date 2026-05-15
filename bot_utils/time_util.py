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

from datetime import datetime, timedelta, time

from bot_utils.bot_utils import TimeSettings

FIVE_MINUTES_SECONDS = 300


class TimeUtil:
    """
    Helper class for time calculations and parsing.
    """

    @staticmethod
    def get_time_from_str(time_str: str) -> time:
        """
        Converts an string with the format "HH:MM" to a time instance

        :param time_str: The time string
        :return: The time instance
        """
        return time.fromisoformat(time_str)

    @staticmethod
    def get_date_time(date: datetime, clock_time: time) -> datetime:
        """
        Combines a datetime and a time instance to one datetime instance.
        Therefore the time from the time instance and the year, month and day values from the date are used.

        :param date: The date
        :param clock_time: The time
        :return: The combined datetime
        """
        return datetime.combine(date.date(), clock_time)
    
    @staticmethod
    def generate_date_list(day_list: list[int]) -> list[datetime]:
        """
        Generates a date list from a list of day offsets.

        Example:
        day_list = [0, 1, 2]
        means today, tomorrow, and the day after tomorrow.
        """
        today = datetime.now()

        return [
            today + timedelta(days=day_delta)
            for day_delta in day_list
        ]

    @staticmethod
    def apply_time_offset(date_time: datetime, offset: int) -> datetime:
        """
        Applies the time zone offset to the given datetime object.

        :param date_time: the date time object
        :param offset: the time zone offset
        :return: the updated datetime
        """
        return date_time + timedelta(seconds=offset)

    @staticmethod
    def get_date_time_in(
        start_time: datetime | None = None,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
    ) -> datetime:
        """
        Calculates the datetime in a specific future from a specific time-point.

        :param start_time: The start time point (default: datetime.now())
        :param hours: The hours in future (default: 0)
        :param seconds: The minutes in future (default: 0)
        :param minutes: The seconds in future (default: 0)
        :return: datetime in specific future
        """
        if start_time is None:
            start_time = datetime.now()
        return start_time + timedelta(hours=hours, minutes=minutes, seconds=seconds)

    @staticmethod
    def generate_date_time_list(
        dates: list[datetime],
        times: list[list[time]] | TimeSettings,
        offset: int = 0,
    ) -> list[datetime]:
        """
        Generates a list of datetime instances from a list of date-strings and a list of time-strings.

        :param dates: the list of date-strings
        :param times: the list of time-strings
        :param offset: the time offset
        :return: the list of datetime instances
        """

        if isinstance(times, list) and len(times) != len(dates):
            raise ValueError(
                f"Expected {len(dates)} time lists, got {len(times)}."
            )

        date_times: list[datetime] = []

        for i, date in enumerate(dates):

            if isinstance(times, TimeSettings):

                current_datetime = TimeUtil.get_date_time(date, times.wakeup_time)

                for survey_index in range(times.survey_count):

                    if survey_index == 0:
                        current_datetime += timedelta(
                            minutes=times.delay_minutes_after_wakeup
                        )
                    else:
                        current_datetime += timedelta(
                            minutes=times.delay_minutes_between_surveys
                        )

                    date_times.append(current_datetime)

            else:
                for survey_time in times[i]:
                    date_times.append(
                        TimeUtil.get_date_time(date, survey_time)
                    )

        if offset:
            date_times = [
                TimeUtil.apply_time_offset(dt, offset)
                for dt in date_times
            ]

        return date_times

    @staticmethod
    def add_dates(
        date: datetime,
        time_settings: TimeSettings,
    ) -> list[datetime]:
        """
        Generates a datetime list from a specific date and timesettings.

        :param date: The date
        :param time_settings: The time settings.
        :return: list of all datetimes
        """
        return TimeUtil.generate_date_time_list(
            [date],
            time_settings,
        )

    @staticmethod
    def get_time_offset(participant_datetime: datetime) -> int:
        """
        Calculates the time zone offset with the given datetime.

        :param participant_datetime: the datetime of the participant
        :return: the time zone offset (int)
        """
        datetime_now = datetime.now().replace(second=0, microsecond=0)

        delta_seconds = int(
            (participant_datetime - datetime_now).total_seconds()
        )

        if -FIVE_MINUTES_SECONDS <= delta_seconds <= FIVE_MINUTES_SECONDS:
            return 0

        return delta_seconds
