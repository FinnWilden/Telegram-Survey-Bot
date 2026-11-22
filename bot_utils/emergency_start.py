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
import logging
from datetime import datetime
from typing import List, Tuple, Callable

from bot_utils.bot_enums import SurveyType
from bot_utils.bot_utils import destruct_tuple
from bot_utils.db_handler import DbHandler
from bot_utils.logging_strings import *
from bot_utils.schedule_util import ScheduleUtil

class EmergencyStart:
    """
    Class for the Emergency-Start.
    """
    schedule_util: ScheduleUtil
    db_handler: DbHandler
    logger: logging

    def __init__(self,
                 schedule_util: ScheduleUtil,
                 db_handler: DbHandler,
                 exec_function: Callable,
                 reminder_function: Callable | None = None) -> None:
        """
        Constructor.\n
        After initializing all fields, this constructor will automatically run the check, if an emergency-start
        is possible.

        :param scheduler: the schedule util instance
        :param db_handler: the database handler instance
        :param exec_function: the send notification broadcast function of the bot main file
        :param reminder_function: the send end survey reminder function of the bot main file,
            or None when end survey reminders are disabled (stored reminders are then not rescheduled)
        """
        self.schedule_util = schedule_util
        self.db_handler = db_handler
        self.logger = logging.getLogger(__name__)
        self.progress(exec_function, reminder_function)

    def progress(self, exec_function: Callable, reminder_function: Callable | None = None) -> None:
        """
        Handles the whole emergency-start progress.

        :param exec_function: the send notification broadcast function of the bot main file
        :param reminder_function: the send end survey reminder function of the bot main file, or None
        :return: None
        """
        future_dates: List[Tuple[datetime, SurveyType]] = list(dict.fromkeys(self.get_future_survey_dates()))
        future_reminders = self.get_future_end_reminders() if reminder_function is not None else {}
        count = len(future_dates) + len(future_reminders)
        if count:
            if self.ask_for_emergency_start(count):
                self.restore_scheduler_entries(future_dates, exec_function)
                self.restore_end_reminders(future_reminders, reminder_function)
            else:
                if self.ask_for_database_cleanup():
                    self.db_handler.delete_all_subscribers()
                    self.logger.info(EMERGENCY_DATES_IGNORE_DELETE.format(count))
                else:
                    self.logger.info(EMERGENCY_DATES_IGNORE.format(count))

    def get_future_end_reminders(self) -> dict[datetime, list[int]]:
        """
        Queries the stored end survey reminders that are still ahead.

        :return: reminder date -> chat ids to remind
        """
        datetime_now = datetime.now()
        return {
            reminder_date: chat_ids
            for reminder_date, chat_ids in self.db_handler.query_end_reminders().items()
            if datetime_now < reminder_date
        }

    def restore_end_reminders(self,
                              future_reminders: dict[datetime, list[int]],
                              reminder_function: Callable | None) -> None:
        """
        Reschedules stored end survey reminders as reminders (question with Yes/No buttons).

        :param future_reminders: reminder date -> chat ids to remind
        :param reminder_function: the send end survey reminder function of the bot main file
        :return: None
        """
        if not future_reminders or reminder_function is None:
            return
        self.logger.info(EMERGENCY_REMINDERS_RESCHEDULE.format(len(future_reminders)))
        for reminder_date, chat_ids in future_reminders.items():
            self.schedule_util.schedule_end_survey_reminder_at(reminder_function, reminder_date, chat_ids)

    def get_future_survey_dates(self) -> List[Tuple[datetime, SurveyType]]:
        """
        Queries all survey dates in the database pick the future dates out to reschedule them.

        :return: list of future dates tuples (datetime, SurveyType)
        """
        tuple_list: List[Tuple[datetime, SurveyType]] = self.db_handler.query_subscribers_emergency_start()
        datetime_now = datetime.now()
        return list(filter(destruct_tuple(lambda dt, _: datetime_now < dt), tuple_list))

    def ask_yes_no(self, message: str, default: bool) -> bool:
        """
        Ask a yes/no question in the command line.

        Without a terminal to answer in (e.g. when the bot runs as a background service),
        the default is used instead of stopping the bot.
        """
        while True:
            self.logger.warning(message)
            try:
                answer = input("[y/n]: ").strip().lower()
            except EOFError:
                self.logger.warning(EMERGENCY_NO_TERMINAL.format("y" if default else "n"))
                return default

            if answer in ("y", "yes"):
                return True

            if answer in ("n", "no"):
                return False

            self.logger.warning("Please enter 'y' or 'n'.")


    def ask_for_emergency_start(self, count_future_dates: int) -> bool:
        """
        Ask whether future survey dates should be rescheduled.
        """
        return self.ask_yes_no(
            EMERGENCY_DATES_FOUND.format(count_future_dates),
            default=True,
        )


    def ask_for_database_cleanup(self) -> bool:
        """
        Ask whether all current database entries should be deleted.
        """
        # never delete data without an explicit answer
        return self.ask_yes_no(EMERGENCY_DATES_WARN, default=False)

    def restore_scheduler_entries(self,
                                  future_dates: List[Tuple[datetime, SurveyType]],
                                  exec_function: Callable) -> None:
        """
        Reschedules all entries of the given future dates list with the send_message_broadcast function
        (given as exec_function parameter).

        :param future_dates: the send notification broadcast function of the bot main file
        :param exec_function: the send notification broadcast function of the bot main file
        :return: None
        """
        self.logger.info(EMERGENCY_DATES_RESCHEDULE.format(len(future_dates)))
        for date, survey_type in future_dates:
            self.schedule_util.add_job(date, exec_function, survey_type)
