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
import random
import sqlite3

from datetime import datetime
from pathlib import Path
from typing import TypedDict

from bot_utils.bot_enums import SurveyType
from bot_utils.config import MAX_PARTICIPANT_NUMBER_DIGITS
from bot_utils.sql_statements import *

from bot_utils.logging_strings import *

DB_FILE = Path("db") / "userIdDb.db"

# Up to this range size the free participant numbers are listed and one is chosen;
# for larger ranges random numbers are drawn until a free one is found.
FREE_NUMBER_ENUMERATION_LIMIT = 100_000


class DashboardSummary(TypedDict):
    total_participants: int
    active_participants: int
    first_registration: str | None
    last_registration: str | None
    message_counts: dict[str, int]


class ParticipantOverview(TypedDict):
    chat_id: int
    first_registered_at: str | None
    last_registered_at: str | None
    is_active: bool
    condition: int | None
    wakeup_time: str | None
    time_offset: int | None
    participant_number: str | None
    message_count: int
    last_message_at: str | None


class OutboundMessageOverview(TypedDict):
    chat_id: int
    message_type: str
    sent_at: str


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
            self.create_table(connection, CREATE_TABLE_PARTICIPANTS)
            self.create_table(connection, CREATE_TABLE_OUTBOUND_MESSAGES)
            self.create_table(connection, CREATE_TABLE_PARTICIPANT_NUMBERS)
            self.create_table(connection, CREATE_INDEX_OUTBOUND_MESSAGES_CHAT_ID)
            self._migrate_participants_table(connection)
            connection.execute(BACKFILL_PARTICIPANTS)
            connection.execute(BACKFILL_PARTICIPANT_CONDITIONS)
            connection.commit()

    @staticmethod
    def _migrate_participants_table(connection: sqlite3.Connection) -> None:
        """
        Add columns introduced after the participants table was first created.
        """
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(participants)")
        }
        for column, statement in PARTICIPANT_MIGRATION_COLUMNS.items():
            if column not in existing_columns:
                connection.execute(statement)

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
            cursor.execute(MARK_ALL_PARTICIPANTS_UNSUBSCRIBED, (self._timestamp_now(),))
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
            cursor.execute(MARK_PARTICIPANT_UNSUBSCRIBED, (self._timestamp_now(), chat_id))
            cursor.execute(DELETE_MESSAGE, (chat_id,))
            cursor.execute(DELETE_SUBSCRIBER_CHAT_ID, (chat_id,))
            cursor.execute(DELETE_CONDITION, (chat_id,))
            connection.commit()

    @staticmethod
    def _timestamp_now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def register_participant(
        self,
        chat_id: int,
        condition: int | None = None,
        wakeup_time: str | None = None,
    ) -> None:
        """
        Record a completed subscription while retaining the participant's history.

        :param chat_id: The chat id
        :param condition: The condition the participant was assigned to
        :param wakeup_time: The wake-up time entered by the participant (HH:MM)
        """
        timestamp = self._timestamp_now()
        with self.create_connection() as connection:
            connection.execute(
                UPSERT_PARTICIPANT,
                (chat_id, timestamp, timestamp, condition, wakeup_time),
            )
            connection.commit()

    def get_participant_number(self, chat_id: int) -> str | None:
        """
        Return the participant number of a chat id as used in links, or None if none was assigned yet.
        """
        with self.create_connection() as connection:
            row = connection.execute(SELECT_PARTICIPANT_NUMBER, (chat_id,)).fetchone()

        return None if row is None else row["code"]

    def count_participant_numbers(self) -> int:
        """
        Return how many participant numbers have been assigned.
        """
        with self.create_connection() as connection:
            row = connection.execute(COUNT_PARTICIPANT_NUMBERS).fetchone()

        return row["used_count"]

    def assign_participant_number(
        self,
        chat_id: int,
        digits: int,
        rng: random.Random | None = None,
    ) -> str:
        """
        Return the participant's permanent number, drawing a new one if necessary.

        A new number is drawn at random among the numbers with 'digits' digits
        (leading zeros included, e.g. 00042) that no other participant has. When
        all of them are taken, the number gets one more digit, so the number of
        participants is unlimited. The number is stored exactly as it appears in
        the links and never released, so it stays the same after unsubscribing,
        re-subscribing, restarts and changes of 'digits'.

        :return: The participant number as used in the links
        """
        rng = rng or random
        with self.create_connection() as connection:
            # Lock the database so two subscriptions cannot draw the same number.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(SELECT_PARTICIPANT_NUMBER, (chat_id,)).fetchone()
            if row is not None:
                return row["code"]

            for length in range(digits, MAX_PARTICIPANT_NUMBER_DIGITS + 1):
                # the first length also covers the numbers that need leading zeros
                min_number = 1 if length == digits else 10 ** (length - 1)
                max_number = 10 ** length - 1
                used_numbers = {
                    used_row["number"]
                    for used_row in connection.execute(SELECT_PARTICIPANT_NUMBERS_IN_RANGE, (min_number, max_number))
                }
                number = self._draw_free_number(used_numbers, min_number, max_number, rng)
                if number is not None:
                    break
                logging.warning(PARTICIPANT_NUMBERS_LENGTH_FULL.format(length, length + 1))
            else:
                raise RuntimeError("No participant number with up to %d digits left" % MAX_PARTICIPANT_NUMBER_DIGITS)

            code = str(number).zfill(digits)
            connection.execute(INSERT_PARTICIPANT_NUMBER, (chat_id, number, code, self._timestamp_now()))
            connection.commit()

        logging.info(PARTICIPANT_NUMBER_ASSIGNED.format(chat_id, code))
        return code

    @staticmethod
    def _draw_free_number(
        used_numbers: set[int],
        min_number: int,
        max_number: int,
        rng: random.Random,
    ) -> int | None:
        range_size = max_number - min_number + 1
        if len(used_numbers) >= range_size:
            return None

        if range_size <= FREE_NUMBER_ENUMERATION_LIMIT:
            free_numbers = [number for number in range(min_number, max_number + 1) if number not in used_numbers]
            return rng.choice(free_numbers)

        while True:
            number = rng.randint(min_number, max_number)
            if number not in used_numbers:
                return number

    def record_outbound_message(self, chat_id: int, message_id: int, message_type: str) -> None:
        """
        Keep a permanent record of a successfully sent bot message.
        """
        with self.create_connection() as connection:
            connection.execute(
                INSERT_OUTBOUND_MESSAGE,
                (chat_id, message_id, message_type, self._timestamp_now()),
            )
            connection.commit()

    def get_dashboard_summary(self) -> DashboardSummary:
        """
        Return persistent participant and outbound-message counts for the console.
        """
        with self.create_connection() as connection:
            summary_row = connection.execute(SELECT_PARTICIPANT_SUMMARY).fetchone()
            message_rows = connection.execute(SELECT_OUTBOUND_MESSAGE_COUNTS).fetchall()

        return {
            "total_participants": summary_row["total_participants"],
            "active_participants": summary_row["active_participants"],
            "first_registration": summary_row["first_registration"],
            "last_registration": summary_row["last_registration"],
            "message_counts": {
                row["message_type"]: row["message_count"]
                for row in message_rows
            },
        }

    def get_participant_overview(self) -> list[ParticipantOverview]:
        """
        Return all known participants with their message totals and latest delivery.
        """
        with self.create_connection() as connection:
            rows = connection.execute(SELECT_PARTICIPANT_OVERVIEW).fetchall()

        return [
            {
                "chat_id": row["chat_id"],
                "first_registered_at": row["first_registered_at"],
                "last_registered_at": row["last_registered_at"],
                "is_active": bool(row["is_active"]),
                "condition": row["condition"],
                "wakeup_time": row["wakeup_time"],
                "time_offset": row["time_offset"],
                "participant_number": row["participant_number"],
                "message_count": row["message_count"],
                "last_message_at": row["last_message_at"],
            }
            for row in rows
        ]

    def get_recent_outbound_messages(self) -> list[OutboundMessageOverview]:
        """
        Return the 100 most recently sent bot messages.
        """
        with self.create_connection() as connection:
            rows = connection.execute(SELECT_RECENT_OUTBOUND_MESSAGES).fetchall()

        return [
            {
                "chat_id": row["chat_id"],
                "message_type": row["message_type"],
                "sent_at": row["sent_at"],
            }
            for row in rows
        ]

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
