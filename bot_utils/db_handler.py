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

import logging
import sqlite3

from datetime import datetime
from pathlib import Path

from bot_utils.bot_enums import SurveyType
from bot_utils.sql_statements import *

from bot_utils.logging_strings import *

DB_FILE = Path("db") / "userIdDb.db"


class DbHandler:
    """
    A class for all interactions to the SQLite Database,
    which stores the chat-ids, message-ids and other information to address the users.
    """
    logger: logging.Logger

    def __init__(self) -> None:
        """
        Creates a connection to the SQLite Database-file and
        create, if not exist, all needed tables.
        """
        self.logger = logging.getLogger(__name__)
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)

        with self.create_connection() as connection:
            self.create_table(connection, CREATE_TABLE_SUBSCRIBER)
            self.create_table(connection, CREATE_TABLE_MESSAGES)
            self.create_table(connection, CREATE_TABLE_OFFSETS)
            self.create_table(connection, CREATE_TABLE_CONDITIONS)

    @staticmethod
    def create_connection() -> sqlite3.Connection:
        """
        Creates a connection to the SQLite Database-file.

        :return: the Connection instance
        """
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create_table(self, conn: sqlite3.Connection, command: str) -> None:
        """
        Creates a new table if it not already exists.

        :param conn: The database Connection instance
        :param command: The SQL-command string
        :return: None
        """
        try:
            conn.execute(command)
        except sqlite3.Error:
            self.logger.exception("Could not create database table")
            raise

    def insert_end_reminder_entries_from_list(
        self,
        survey_type: SurveyType,
        subscriber_information: list[tuple[int, int, int]],
        date_str: str,
    ) -> None:
        """
        Inserts entries for end survey reminder.

        :param survey_type: The survey type
        :param subscriber_information:
        :param date_str:
        :return: None
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()

            for chat_id, condition, end_index in subscriber_information:
                cursor.execute(
                    INSERT_SUBSCRIBER,
                    (chat_id, date_str, survey_type.name, condition, end_index),
                )

            connection.commit()

    def insert_new_subscriber_entries(
        self,
        chat_id: int,
        date_list: list[datetime],
        survey_type: SurveyType,
        condition: int,
        end_distribution_list: list[int] | None = None,
    ) -> None:
        """
        Inserts subscriber entries.

        :param chat_id: The chat id of the new subscriber
        :param date_list: The Datetime list
        :param survey_type: The survey type
        :param condition: The condition number
        :param end_distribution_list: The end distribution list (optional)
        :return: None
        """
        self.logger.info(DB_INSERT_SUBSCRIBER_ENTRY)

        with self.create_connection() as connection:
            cursor = connection.cursor()

            for i, date in enumerate(date_list):
                end_distribution = -1

                if survey_type == SurveyType.END and end_distribution_list is not None:
                    end_distribution = end_distribution_list[i]

                date_str = date.strftime("%Y-%m-%d-%H:%M")

                self.logger.info(
                    DB_INSERT_SUBSCRIBER_ENTRY_DATA.format(
                        chat_id,
                        date_str,
                        survey_type.name,
                        condition,
                        end_distribution,
                    )
                )

                cursor.execute(
                    INSERT_SUBSCRIBER,
                    (chat_id, date_str, survey_type.name, condition, end_distribution),
                )

            connection.commit()

    def update_subscriber_condition(self, chat_id: int, condition: int) -> None:
        """
        Updates the condition number of one subscriber.

        :param chat_id: The chat id of the subscriber
        :param condition: The new entered condition of the subscriber
        :return: None
        """
        self.logger.info(DB_UPDATE_CONDITION.format(chat_id, condition))

        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(UPDATE_SUBSCRIBER, (condition, chat_id))
            connection.commit()

    def is_already_subscribed(self, chat_id: int) -> bool:
        """
        Returns if the given chat id is already subscribed.

        :param chat_id: The chat id to check
        :return: if the chat id is already subscribed (bool)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_SUBSCRIBER_CHAT_ID, (chat_id,))
            return cursor.fetchone() is not None

    def query_subscribers_by_date_type(
        self,
        date_str: str,
        type_str: str,
    ) -> list[tuple[int, int, int]]:
        """
        Query all subscribers to a specific date string and survey type.

        :param date_str: The date string
        :param type_str: The type string
        :return: list with Triples (chat id, condition, end index)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_SUBSCRIBER_DATE_TYPE, (date_str, type_str))
            return cursor.fetchall()

    def query_subscribers_emergency_start(self) -> list[tuple[datetime, SurveyType]]:
        """
        Query all currently scheduled survey dates to reschedule them.

        :return: scheduled survey dates as list of tuples (datetime, SurveyType)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_SUBSCRIBER_EMERGENCY)
            rows = cursor.fetchall()

        return [
            (
                datetime.strptime(date_str, "%Y-%m-%d-%H:%M"),
                SurveyType[type_str],
            )
            for date_str, type_str in rows
        ]

    def delete_all_subscribers(self) -> None:
        """
        Delete all subscribers from the subscribers table.

        :return: None
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(DELETE_ALL_SUBSCRIBERS)
            connection.commit()

    def get_condition(self, chat_id: int) -> int:
        """
        Returns the condition of a given chat id.

        :param chat_id: The chat id
        :return: The condition (int)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_SUBSCRIBER_CHAT_ID, (chat_id,))
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"No subscriber found for chat_id={chat_id}")

        return row["condition"]

    def set_condition(self, chat_id: int, condition: int) -> None:
        """
        Sets the condition of a given chat id.

        :param chat_id: The chat id
        :param condition: The condition
        :return: None
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(INSERT_CONDITION, (chat_id, condition))
            connection.commit()

    def get_used_condition(self, chat_id: int) -> int:
        """
        Returns the condition of a given chat id.

        :param chat_id: The chat id
        :return: The condition (int)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_CONDITION, (chat_id,))
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"No condition found for chat_id={chat_id}")

        return row["condition"]

    def get_used_conditions(self) -> list[int]:
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_CONDITIONS)
            rows = cursor.fetchall()

        return [row["condition"] for row in rows]

    def get_condition_and_end_index(
        self,
        chat_id: int,
        date_str: str,
    ) -> tuple[int, int]:
        """
        Returns the condition and the end index of a given chat id and date string.

        :param chat_id: The chat id
        :param date_str: The date string
        :return: tuple (condition, end index)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_SUBSCRIBER_ID_DATE, (chat_id, date_str))
            row = cursor.fetchone()

        if row is None:
            raise LookupError(
                f"No subscriber entry found for chat_id={chat_id}, date={date_str}"
            )

        return row["condition"], row["end_index"]

    def remove_subscriber(self, chat_id: int) -> None:
        """
        Removes a subscriber from the database.

        :param chat_id: The chat id
        :return: None
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(DELETE_MESSAGE, (chat_id,))
            cursor.execute(DELETE_SUBSCRIBER_CHAT_ID, (chat_id,))
            cursor.execute(DELETE_CONDITION, (chat_id,))
            connection.commit()

    def insert_message_id(self, chat_id: int, message_id: int, survey_type: SurveyType) -> None:
        """
        Inserts a message id with the survey type.

        :param chat_id: The chat id
        :param message_id: The message id
        :param survey_type: The survey type
        :return: None
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(INSERT_MESSAGE, (chat_id, message_id, survey_type.name))
            connection.commit()

    def query_and_delete_message_ids(
        self,
        chat_ids: list[int],
        survey_type: SurveyType,
    ) -> list[tuple[int, int]]:
        """
        Query all message ids to a list of chat ids and a specific survey type.

        :param chat_ids: The chat id list
        :param survey_type: The survey type
        :return: list of tuples (chat id, message id)
        """
        chat_message_ids: list[tuple[int, int]] = []

        with self.create_connection() as connection:
            cursor = connection.cursor()

            for chat_id in chat_ids:
                cursor.execute(SELECT_MESSAGE_ID, (chat_id, survey_type.name))
                rows = cursor.fetchall()

                chat_message_ids.extend(
                    (row["chat_id"], row["message_id"])
                    for row in rows
                )

                cursor.execute(DELETE_MESSAGE_ID, (chat_id, survey_type.name))

            connection.commit()

        return chat_message_ids

    def query_and_delete_message_ids_by_type(self, survey_type: SurveyType) -> list[tuple[int, int]]:
        """
        Query all message ids to a specific survey type.

        :param survey_type: The survey type
        :return: list of tuples (chat id, message id)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_MESSAGE_TYPE, (survey_type.name,))
            rows = cursor.fetchall()

            message_ids = [
                (row["chat_id"], row["message_id"])
                for row in rows
            ]

            cursor.execute(DELETE_MESSAGE_TYPE, (survey_type.name,))
            connection.commit()

        return message_ids

    def insert_time_offset(self, chat_id: int, offset: int) -> None:
        """
        Insert the time zone offset for a specific chat id.

        :param chat_id: the chat id
        :param offset: the timezone offset
        :return: None
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(INSERT_OFFSET, (chat_id, offset))
            connection.commit()

    def get_time_offset(self, chat_id: int) -> int:
        """
        Return the time zone offset for a specific chat id.\n
        Return 0 if no time zone offset is stored for the chat id.

        :param chat_id: the chat id
        :return: the time zone offset (int)
        """
        with self.create_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_OFFSET, (chat_id,))
            row = cursor.fetchone()

        if row is None:
            return 0

        return row["offset"]
