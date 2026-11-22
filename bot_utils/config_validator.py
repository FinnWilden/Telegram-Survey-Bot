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

from bot_utils.bot_enums import EndUrlDistribution
from bot_utils.config import PARTICIPANT_PLACEHOLDER, Config


class ConfigValidationException(Exception):
    """
    Exception for config validation errors.
    """
    message_list: list[str]

    def __init__(self, message_list: list[str]) -> None:
        """
        Constructor.

        :param message_list: list with error messages
        """
        self.message_list = message_list
        super().__init__("\n".join(message_list))


class ConfigValidator:
    """
    Util class for config validation.
    """

    @staticmethod
    def _all_inner_lengths_equal(values: list[list]) -> bool:
        if not values:
            return False

        first_length = len(values[0])
        return all(len(value) == first_length for value in values)

    @staticmethod
    def validate_config(config: Config) -> None:
        """
        Validates a config instance.

        :raises ConfigValidationException: When config is not valid
        :param config: the config instance
        :return: None
        """
        error_list: list[str] = []
        error_list.extend(ConfigValidator.validate_dates_and_times(config))
        error_list.extend(ConfigValidator.validate_link_deletion_settings(config))
        error_list.extend(ConfigValidator.validate_urls(config))
        error_list.extend(ConfigValidator.validate_participant_numbers(config))
        if error_list:
            raise ConfigValidationException(error_list)

    @staticmethod
    def validate_dates_and_times(config: Config) -> list[str]:
        """
        Validates all dates and times in the config.

        :param config: The config instance
        :return: The list of error messages. Empty when there are no errors
        """
        error_list: list[str] = []
        if config.subscription_start_date > config.subscription_deadline:
            error_list.append("subscription start date is after subscription deadline")
        if not config.useDayCalculation and not config.useTimeCalculation:
            if len(config.daily_dates) < len(config.daily_times):
                error_list.append("Not enough dates in 'daily_dates' to match number of time lists in 'daily_times'.")
            if len(config.end_dates) < len(config.end_times):
                error_list.append("Not enough dates in 'end_dates' to match number of time lists in 'end_times'.")
            if len(config.daily_times) < len(config.daily_dates):
                error_list.append("Not enough time lists in 'daily_times' to match number of dates in 'daily_dates'.")
            if len(config.end_times) < len(config.end_dates):
                error_list.append("Not enough time lists in 'end_times' to match number of dates in 'end_dates'.")
        if config.useDayCalculation and not config.useTimeCalculation:
            if len(config.dayCalculationSettings.daily_SurveyDays) < len(config.daily_times):
                error_list.append("Not enough dates in 'dayCalculationSettings.daily_SurveyDays' to match number of "
                                  "time lists in 'daily_times'.")
            if len(config.daily_times) < len(config.dayCalculationSettings.daily_SurveyDays):
                error_list.append("Not enough time lists in 'daily_times' to match number of "
                                  "dates in 'dayCalculationSettings.daily_SurveyDays'.")
            if len(config.dayCalculationSettings.end_SurveyDays) < len(config.end_times):
                error_list.append("Not enough dates in 'dayCalculationSettings.end_SurveyDays' to match number of "
                                  "time lists in 'end_times'.")
            if len(config.end_times) < len(config.dayCalculationSettings.end_SurveyDays):
                error_list.append("Not enough time lists in 'end_times' to match number of "
                                  "dates in 'dayCalculationSettings.end_SurveyDays'.")
        if config.useTimeCalculation:
            if config.timeCalculationSettings.daily_DelayMinutesAfterWakeup <= 0:
                error_list.append("'timeCalculationSettings.daily_DelayMinutesAfterWakeup' must be greater than 0")
            if config.timeCalculationSettings.daily_SurveysPerDay <= 0:
                error_list.append("'timeCalculationSettings.daily_SurveysPerDay' must be greater than 0")
            if not config.timeCalculationSettings.daily_SurveysPerDay == 1 and \
                    config.timeCalculationSettings.daily_DelayMinutesBetweenSurveys <= 0:
                error_list.append("'timeCalculationSettings.daily_DelayMinutesBetweenSurveys' must be greater than 0")
            if config.timeCalculationSettings.end_DelayMinutesAfterWakeup <= 0:
                error_list.append("'timeCalculationSettings.end_DelayMinutesAfterWakeup' must be greater than 0")
            if config.timeCalculationSettings.end_SurveysPerDay < 0:
                error_list.append("'timeCalculationSettings.end_SurveysPerDay' must be greater or equal than 0")
            if not (0 <= config.timeCalculationSettings.end_SurveysPerDay <= 1) and \
                    config.timeCalculationSettings.end_DelayMinutesBetweenSurveys <= 0:
                error_list.append("'timeCalculationSettings.end_DelayMinutesBetweenSurveys' must be greater than 0")
        if config.uniqueConditions and config.participantsEnterCondition:
            error_list.append("You cannot use 'uniqueConditions' and 'participantsEnterCondition' at the same time.")
        return error_list

    @staticmethod
    def validate_link_deletion_settings(config: Config) -> list[str]:
        """
        Validates the link deletion settings.

        :param config: The config instance
        :return: The list of error messages. Empty when there are no errors
        """
        error_list: list[str] = []
        if config.linkDeletionSettings.start_DeleteLinkTimer and \
                config.linkDeletionSettings.start_DeleteDelayMinutes <= 0:
            error_list.append("'linkDeletionSettings.start_DeleteDelayMinutes' must be greater than 0")
        if config.linkDeletionSettings.daily_DeleteLinkTimer and \
                config.linkDeletionSettings.daily_DeleteDelayMinutes <= 0:
            error_list.append("'linkDeletionSettings.daily_DeleteDelayMinutes' must be greater than 0")
        if config.linkDeletionSettings.end_DeleteLinkTimer and \
                config.linkDeletionSettings.end_DeleteDelayMinutes <= 0:
            error_list.append("'linkDeletionSettings.end_DeleteDelayMinutes' must be greater than 0")
        if config.endSurveyReminderEnabled and config.endSurveyReminderDelayHours <= 0:
            error_list.append("'endSurveyReminderDelayHours' must be greater than 0")
        return error_list

    @staticmethod
    def validate_urls(config: Config) -> list[str]:
        """
        Validates the urls.

        :param config: The config instance
        :return: The list of error messages. Empty when there are no errors
        """
        error_list: list[str] = []
        len_start = len(config.urls.start_url)
        len_daily = len(config.urls.daily_url)
        len_end = len(config.urls.end_url)
        if not (len_start == len_daily == len_end):
            error_list.append("Different count of conditions found in urls section.")
        if config.urls.end_url_distribution == EndUrlDistribution.TIME:
            if config.useTimeCalculation:
                time_count = config.timeCalculationSettings.end_SurveysPerDay
                for i, condition_links in enumerate(config.urls.end_url, start=1):
                    if len(condition_links) != time_count:
                        msg = "Different count of links found at position " + str(i) \
                              + " in 'end_url', while 'end_SurveysPerDay' are " + str(time_count)
                        error_list.append(msg)
            else:
                if not ConfigValidator._all_inner_lengths_equal(config.end_times):
                    msg = "Different count of times found in 'end_times'"
                    error_list.append(msg)
                else:
                    time_count = len(config.end_times[0])
                    for i, condition_links in enumerate(config.urls.end_url, start=1):
                        if len(condition_links) != time_count:
                            msg = "Different count of links found at position " + str(i) \
                                  + " in 'end_url', while length of 'end_times' are " + str(time_count)
                            error_list.append(msg)
        elif config.urls.end_url_distribution == EndUrlDistribution.DAY:
            if config.useDayCalculation:
                day_count = len(config.dayCalculationSettings.end_SurveyDays)
                for i, condition_links in enumerate(config.urls.end_url, start=1):
                    if len(condition_links) != day_count:
                        msg = "Different count of links found at position " + str(i) \
                              + " in 'end_url', while number of days in 'end_SurveyDays' are " + str(day_count)
                        error_list.append(msg)
            else:
                day_count = len(config.end_dates)
                for i, condition_links in enumerate(config.urls.end_url, start=1):
                    if len(condition_links) != day_count:
                        msg = "Different count of links found at position " + str(i) \
                              + " in 'end_url', while number of days in 'end_dates' are " + str(day_count)
                        error_list.append(msg)
        elif config.urls.end_url_distribution == EndUrlDistribution.MIXED:
            if not config.useTimeCalculation:
                count = sum([len(list_elem) for list_elem in config.end_times])
            else:
                if config.useDayCalculation:
                    count = config.timeCalculationSettings.end_SurveysPerDay * \
                            len(config.dayCalculationSettings.end_SurveyDays)
                else:
                    count = config.timeCalculationSettings.end_SurveysPerDay * \
                            len(config.end_dates)
            for i, condition_links in enumerate(config.urls.end_url, start=1):
                if len(condition_links) != count:
                    msg = "Different count of links found at position " + str(i) \
                          + " in 'end_url', while number of urls should be " + str(count)
                    error_list.append(msg)
        elif config.urls.end_url_distribution == EndUrlDistribution.NONE:
            for i, condition_links in enumerate(config.urls.end_url, start=1):
                if len(condition_links) != 1:
                    msg = "In distributionmode NONE only one url per condition is allowed"
                    error_list.append(msg)
        else:
            if not ConfigValidator._all_inner_lengths_equal(config.urls.end_url):
                msg = "In distributionmode RANDOM every condition should have the same number of links"
                error_list.append(msg)
        return error_list

    @staticmethod
    def _all_urls(config: Config) -> list[str]:
        return [
            *config.urls.start_url,
            *config.urls.daily_url,
            *(url for condition_links in config.urls.end_url for url in condition_links),
        ]

    @staticmethod
    def validate_participant_numbers(config: Config) -> list[str]:
        """
        Validates the participant number settings and the link stems they are combined with.

        :param config: The config instance
        :return: The list of error messages. Empty when there are no errors
        """
        error_list: list[str] = []

        if not config.useParticipantNumbers:
            if any(PARTICIPANT_PLACEHOLDER in str(url) for url in ConfigValidator._all_urls(config)):
                error_list.append(
                    "A url contains the placeholder '" + PARTICIPANT_PLACEHOLDER
                    + "', but 'useParticipantNumbers' is false."
                )
            return error_list

        settings = config.participantNumberSettings
        if settings is None:
            error_list.append("'participantNumberSettings' is required when 'useParticipantNumbers' is true.")
            return error_list

        values = {
            "minNumber": settings.minNumber,
            "maxNumber": settings.maxNumber,
            "padToDigits": settings.padToDigits,
        }
        invalid = [
            name for name, value in values.items()
            if not isinstance(value, int) or isinstance(value, bool) or value < 0
        ]
        for name in invalid:
            error_list.append("'participantNumberSettings." + name + "' must be a whole number >= 0")
        if not invalid and settings.minNumber > settings.maxNumber:
            error_list.append(
                "'participantNumberSettings.minNumber' must not be greater than 'participantNumberSettings.maxNumber'"
            )

        for url in ConfigValidator._all_urls(config):
            if not isinstance(url, str) or not url.strip():
                error_list.append("Every url stem must be a non-empty text when 'useParticipantNumbers' is true.")
                break

        return error_list
