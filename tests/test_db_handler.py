import sqlite3
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
