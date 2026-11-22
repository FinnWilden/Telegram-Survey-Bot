import random
import sqlite3
import threading
from datetime import datetime

import pytest

import bot_utils.db_handler as db_module
from bot_utils.bot_enums import SurveyType
from bot_utils.db_handler import DbHandler


@pytest.fixture
def db_handler(tmp_path, monkeypatch):
    test_db_file = tmp_path / "test_userIdDb.db"
    monkeypatch.setattr(db_module, "DB_FILE", test_db_file)

    return DbHandler()


def test_initializes_database_tables(db_handler):
    with db_handler.create_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        )
        table_names = {row["name"] for row in cursor.fetchall()}

    assert {"subscribers", "messages", "offsets", "conditions"} <= table_names


def test_insert_new_subscriber_entries_and_is_already_subscribed(db_handler):
    chat_id = 123
    dates = [
        datetime(2026, 5, 15, 9, 0),
        datetime(2026, 5, 16, 9, 0),
    ]

    db_handler.insert_new_subscriber_entries(
        chat_id=chat_id,
        date_list=dates,
        survey_type=SurveyType.DAILY,
        condition=2,
    )

    assert db_handler.is_already_subscribed(chat_id) is True
    assert db_handler.is_already_subscribed(999) is False


def test_get_condition(db_handler):
    chat_id = 123

    db_handler.insert_new_subscriber_entries(
        chat_id=chat_id,
        date_list=[datetime(2026, 5, 15, 9, 0)],
        survey_type=SurveyType.DAILY,
        condition=2,
    )

    assert db_handler.get_condition(chat_id) == 2


def test_get_condition_raises_for_unknown_subscriber(db_handler):
    with pytest.raises(LookupError):
        db_handler.get_condition(999)


def test_update_subscriber_condition(db_handler):
    chat_id = 123

    db_handler.insert_new_subscriber_entries(
        chat_id=chat_id,
        date_list=[datetime(2026, 5, 15, 9, 0)],
        survey_type=SurveyType.DAILY,
        condition=1,
    )

    db_handler.update_subscriber_condition(chat_id, 3)

    assert db_handler.get_condition(chat_id) == 3


def test_query_subscribers_by_date_type(db_handler):
    chat_id = 123
    date = datetime(2026, 5, 15, 9, 0)
    date_str = "2026-05-15-09:00"

    db_handler.insert_new_subscriber_entries(
        chat_id=chat_id,
        date_list=[date],
        survey_type=SurveyType.DAILY,
        condition=2,
    )

    rows = db_handler.query_subscribers_by_date_type(
        date_str,
        SurveyType.DAILY.name,
    )

    assert len(rows) == 1
    assert rows[0]["chat_id"] == chat_id
    assert rows[0]["condition"] == 2
    assert rows[0]["end_index"] == -1


def test_insert_end_reminder_entries_from_list(db_handler):
    date_str = "2026-05-15-18:00"

    db_handler.insert_end_reminder_entries_from_list(
        survey_type=SurveyType.END,
        subscriber_information=[
            (111, 0, 5),
            (222, 1, 6),
        ],
        date_str=date_str,
    )

    rows = db_handler.query_subscribers_by_date_type(
        date_str,
        SurveyType.END.name,
    )

    assert len(rows) == 2
    assert [(row["chat_id"], row["condition"], row["end_index"]) for row in rows] == [
        (111, 0, 5),
        (222, 1, 6),
    ]


def test_query_subscribers_emergency_start(db_handler):
    db_handler.insert_new_subscriber_entries(
        chat_id=123,
        date_list=[datetime(2026, 5, 15, 9, 0)],
        survey_type=SurveyType.DAILY,
        condition=2,
    )

    result = db_handler.query_subscribers_emergency_start()

    assert result == [
        (datetime(2026, 5, 15, 9, 0), SurveyType.DAILY),
    ]


def test_delete_all_subscribers(db_handler):
    db_handler.insert_new_subscriber_entries(
        chat_id=123,
        date_list=[datetime(2026, 5, 15, 9, 0)],
        survey_type=SurveyType.DAILY,
        condition=2,
    )

    db_handler.delete_all_subscribers()

    assert db_handler.is_already_subscribed(123) is False


def test_set_and_get_used_condition(db_handler):
    db_handler.set_condition(chat_id=123, condition=2)

    assert db_handler.get_used_condition(123) == 2


def test_get_used_condition_raises_for_unknown_chat_id(db_handler):
    with pytest.raises(LookupError):
        db_handler.get_used_condition(999)


def test_get_used_conditions(db_handler):
    db_handler.set_condition(chat_id=111, condition=0)
    db_handler.set_condition(chat_id=222, condition=2)

    assert sorted(db_handler.get_used_conditions()) == [0, 2]


def test_get_condition_and_end_index(db_handler):
    chat_id = 123
    date_str = "2026-05-15-18:00"

    db_handler.insert_end_reminder_entries_from_list(
        survey_type=SurveyType.END,
        subscriber_information=[(chat_id, 2, 7)],
        date_str=date_str,
    )

    assert db_handler.get_condition_and_end_index(chat_id, date_str) == (2, 7)


def test_get_condition_and_end_index_raises_for_unknown_entry(db_handler):
    with pytest.raises(LookupError):
        db_handler.get_condition_and_end_index(999, "2026-05-15-18:00")


def test_remove_subscriber_removes_subscriber_messages_and_condition(db_handler):
    chat_id = 123

    db_handler.insert_new_subscriber_entries(
        chat_id=chat_id,
        date_list=[datetime(2026, 5, 15, 9, 0)],
        survey_type=SurveyType.DAILY,
        condition=2,
    )
    db_handler.insert_message_id(chat_id, 555, SurveyType.DAILY)
    db_handler.set_condition(chat_id, 2)

    db_handler.remove_subscriber(chat_id)

    assert db_handler.is_already_subscribed(chat_id) is False
    assert db_handler.query_and_delete_message_ids([chat_id], SurveyType.DAILY) == []

    with pytest.raises(LookupError):
        db_handler.get_used_condition(chat_id)


def test_insert_and_query_and_delete_message_ids(db_handler):
    db_handler.insert_message_id(111, 10, SurveyType.DAILY)
    db_handler.insert_message_id(111, 11, SurveyType.DAILY)
    db_handler.insert_message_id(222, 12, SurveyType.DAILY)
    db_handler.insert_message_id(111, 13, SurveyType.END)

    result = db_handler.query_and_delete_message_ids(
        [111],
        SurveyType.DAILY,
    )

    assert sorted(result) == [
        (111, 10),
        (111, 11),
    ]

    assert db_handler.query_and_delete_message_ids([111], SurveyType.DAILY) == []
    assert db_handler.query_and_delete_message_ids([222], SurveyType.DAILY) == [(222, 12)]
    assert db_handler.query_and_delete_message_ids([111], SurveyType.END) == [(111, 13)]


def test_query_and_delete_message_ids_by_type(db_handler):
    db_handler.insert_message_id(111, 10, SurveyType.DAILY)
    db_handler.insert_message_id(222, 20, SurveyType.DAILY)
    db_handler.insert_message_id(333, 30, SurveyType.END)

    result = db_handler.query_and_delete_message_ids_by_type(SurveyType.DAILY)

    assert sorted(result) == [
        (111, 10),
        (222, 20),
    ]

    assert db_handler.query_and_delete_message_ids_by_type(SurveyType.DAILY) == []
    assert db_handler.query_and_delete_message_ids_by_type(SurveyType.END) == [(333, 30)]


def test_insert_and_get_time_offset(db_handler):
    db_handler.insert_time_offset(chat_id=123, offset=3600)

    assert db_handler.get_time_offset(123) == 3600


def test_get_time_offset_returns_zero_if_missing(db_handler):
    assert db_handler.get_time_offset(999) == 0


def test_participant_history_and_outbound_messages_are_persistent(db_handler, monkeypatch):
    timestamps = iter([
        "2026-11-11T10:00:00+01:00",
        "2026-11-11T10:00:00+01:00",
        "2026-11-11T10:05:00+01:00",
        "2026-11-11T10:10:00+01:00",
        "2026-11-11T10:15:00+01:00",
    ])
    monkeypatch.setattr(db_handler, "_timestamp_now", lambda: next(timestamps))

    db_handler.insert_time_offset(123, -3600)
    db_handler.register_participant(123, 2)
    db_handler.record_outbound_message(123, 10, "SUBSCRIBE")
    db_handler.register_participant(123, 1, "07:30")
    db_handler.record_outbound_message(123, 11, "DAILY")

    summary = db_handler.get_dashboard_summary()
    participant = db_handler.get_participant_overview()[0]

    assert summary == {
        "total_participants": 1,
        "active_participants": 1,
        "first_registration": "2026-11-11T10:00:00+01:00",
        "last_registration": "2026-11-11T10:05:00+01:00",
        "message_counts": {"DAILY": 1, "SUBSCRIBE": 1},
    }
    assert participant == {
        "chat_id": 123,
        "first_registered_at": "2026-11-11T10:00:00+01:00",
        "last_registered_at": "2026-11-11T10:05:00+01:00",
        "is_active": True,
        "condition": 1,
        "wakeup_time": "07:30",
        "time_offset": -3600,
        "participant_number": None,
        "message_count": 2,
        "last_message_at": "2026-11-11T10:10:00+01:00",
    }
    assert db_handler.get_recent_outbound_messages() == [
        {
            "chat_id": 123,
            "message_type": "DAILY",
            "sent_at": "2026-11-11T10:10:00+01:00",
        },
        {
            "chat_id": 123,
            "message_type": "SUBSCRIBE",
            "sent_at": "2026-11-11T10:00:00+01:00",
        },
    ]

    db_handler.remove_subscriber(123)

    participant = db_handler.get_participant_overview()[0]
    assert participant["is_active"] is False
    assert participant["message_count"] == 2
    assert db_handler.get_dashboard_summary()["total_participants"] == 1
    assert db_handler.get_dashboard_summary()["active_participants"] == 0


def test_backfills_existing_subscriber_without_inventing_registration_time(db_handler):
    db_handler.insert_new_subscriber_entries(
        chat_id=456,
        date_list=[datetime(2026, 11, 12, 9, 0)],
        survey_type=SurveyType.DAILY,
        condition=0,
    )

    with db_handler.create_connection() as connection:
        connection.execute("DELETE FROM participants WHERE chat_id=?", (456,))
        connection.commit()

    migrated_db_handler = DbHandler()

    participant = migrated_db_handler.get_participant_overview()[0]
    assert participant["chat_id"] == 456
    assert participant["first_registered_at"] is None
    assert participant["condition"] == 0


def test_migrates_participants_table_created_without_parameter_columns(tmp_path, monkeypatch):
    db_file = tmp_path / "old.db"
    monkeypatch.setattr(db_module, "DB_FILE", db_file)
    connection = sqlite3.connect(db_file)
    connection.execute(
        "CREATE TABLE participants (chat_id INTEGER PRIMARY KEY, first_registered_at TEXT, "
        "last_registered_at TEXT, is_active INTEGER NOT NULL DEFAULT 1, unsubscribed_at TEXT)"
    )
    connection.execute("INSERT INTO participants VALUES (789, '2026-11-01T08:00:00+01:00', NULL, 1, NULL)")
    connection.commit()
    connection.close()

    migrated_db_handler = DbHandler()
    migrated_db_handler.register_participant(790, 3, "06:45")

    participants = {p["chat_id"]: p for p in migrated_db_handler.get_participant_overview()}
    assert participants[789]["condition"] is None
    assert participants[789]["first_registered_at"] == "2026-11-01T08:00:00+01:00"
    assert participants[790]["condition"] == 3
    assert participants[790]["wakeup_time"] == "06:45"


# ---------------------------------------------------------------------------
# Participant numbers
# ---------------------------------------------------------------------------


def test_assign_participant_number_has_the_configured_length(db_handler):
    number = db_handler.assign_participant_number(123, 5)

    assert len(number) == 5
    assert number.isdigit()
    assert number != "00000"
    assert db_handler.get_participant_number(123) == number


def test_numbers_are_unique_and_overflow_to_more_digits_instead_of_running_out(db_handler):
    # one digit gives the nine numbers 1-9; participant ten and later get two digits
    numbers = [db_handler.assign_participant_number(chat_id, 1) for chat_id in range(25)]

    assert sorted(numbers[:9]) == [str(n) for n in range(1, 10)]
    assert all(len(number) == 2 and 10 <= int(number) <= 99 for number in numbers[9:])
    assert len(set(numbers)) == 25
    assert db_handler.count_participant_numbers() == 25


def test_leading_zeros_are_kept(db_handler):
    class Always:
        def choice(self, numbers):
            return 42

    assert db_handler.assign_participant_number(123, 5, Always()) == "00042"


def test_assign_participant_number_is_random(db_handler):
    numbers = [db_handler.assign_participant_number(chat_id, 4) for chat_id in range(30)]

    # ascending numbers would mean the number is not drawn at random
    assert numbers != sorted(numbers)


def test_assign_participant_number_uses_given_random_source(db_handler):
    expected = random.Random(42).choice(list(range(1, 1000)))

    assert db_handler.assign_participant_number(123, 3, random.Random(42)) == f"{expected:03d}"


def test_participant_keeps_number_across_calls_unsubscribe_and_restart(db_handler):
    number = db_handler.assign_participant_number(123, 5)

    assert db_handler.assign_participant_number(123, 5) == number
    db_handler.remove_subscriber(123)
    db_handler.delete_all_subscribers()
    assert db_handler.get_participant_number(123) == number

    restarted_db_handler = DbHandler()
    assert restarted_db_handler.assign_participant_number(123, 5) == number


def test_existing_number_is_kept_when_digits_change(db_handler):
    number = db_handler.assign_participant_number(123, 3)

    assert db_handler.assign_participant_number(123, 6) == number
    assert len(db_handler.assign_participant_number(456, 6)) == 6


def test_shorter_numbers_from_an_old_setting_are_not_given_out_twice(db_handler):
    class Fixed:
        def __init__(self, value):
            self.value = value

        def choice(self, numbers):
            return self.value if self.value in numbers else numbers[0]

    db_handler.assign_participant_number(1, 2, Fixed(42))  # stored as 42, link "42"

    # with 4 digits 42 would be "0042"; the same value must not be reused
    assert db_handler.assign_participant_number(2, 4, Fixed(42)) != "0042"


def test_many_digits_draw_without_listing_every_number(db_handler, monkeypatch):
    monkeypatch.setattr(db_module, "FREE_NUMBER_ENUMERATION_LIMIT", 10)
    numbers = {db_handler.assign_participant_number(chat_id, 12) for chat_id in range(50)}

    assert len(numbers) == 50
    assert all(len(number) == 12 for number in numbers)


def test_many_digits_skip_numbers_already_taken(db_handler, monkeypatch):
    monkeypatch.setattr(db_module, "FREE_NUMBER_ENUMERATION_LIMIT", 1)

    class Draws:
        def __init__(self, values):
            self.values = iter(values)

        def randint(self, low, high):
            return next(self.values)

    assert db_handler.assign_participant_number(1, 2, Draws([7])) == "07"
    assert db_handler.assign_participant_number(2, 2, Draws([7, 7, 8])) == "08"


def test_concurrent_assignments_never_share_a_number(db_handler):
    results = []
    errors = []

    def assign(chat_id):
        try:
            results.append(DbHandler().assign_participant_number(chat_id, 1))
        except Exception as err:  # reported below
            errors.append(err)

    threads = [threading.Thread(target=assign, args=(chat_id,)) for chat_id in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(set(results)) == 40
    assert sorted(int(number) for number in results if len(number) == 1) == list(range(1, 10))


def test_participant_overview_contains_participant_number(db_handler):
    number = db_handler.assign_participant_number(123, 5)
    db_handler.register_participant(123, 0)

    assert db_handler.get_participant_overview()[0]["participant_number"] == number
