import csv
import logging
import os
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

import bot
import bot_utils.db_handler as db_module
import bot_utils.overview_export as export_module
from bot_utils.bot_enums import SurveyType
from bot_utils.db_handler import DbHandler
from bot_utils.overview_export import (
    DELIVERIES_FILE,
    DELIVERY_COLUMNS,
    OVERVIEW_FILE,
    PARTICIPANT_COLUMNS,
    PARTICIPANTS_FILE,
    OverviewExporter,
)
from test_participant_number_flow import Study


@pytest.fixture
def db_handler(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "export.db")
    return DbHandler()


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file, delimiter=";"))


def add_participant(db_handler, chat_id, survey_date, condition=0, wakeup=None, offset=None, digits=5):
    if offset is not None:
        db_handler.insert_time_offset(chat_id, offset)
    db_handler.insert_new_subscriber_entries(chat_id, [survey_date], SurveyType.DAILY, condition)
    number = db_handler.assign_participant_number(chat_id, digits)
    db_handler.register_participant(chat_id, condition, wakeup)
    return number


@pytest.fixture
def study_data(db_handler):
    future, past = datetime.now() + timedelta(days=1), datetime(2020, 1, 1, 9, 0)
    numbers = {
        101: add_participant(db_handler, 101, future, condition=1, wakeup="07:30", offset=-5400),
        102: add_participant(db_handler, 102, past),
        103: add_participant(db_handler, 103, future),
    }
    db_handler.remove_subscriber(103)
    for message_id, (chat_id, message_type) in enumerate(
        [(101, "SUBSCRIBE"), (101, "DAILY"), (102, "END"), (102, "END_REMINDER"), (103, "MESSAGE")], start=1
    ):
        db_handler.record_outbound_message(chat_id, message_id, message_type)
    return numbers


def test_participants_csv_lists_everyone_with_status_and_answers(tmp_path, db_handler, study_data):
    OverviewExporter(db_handler, tmp_path / "export", participant_number_digits=5).export()

    rows = read_csv(tmp_path / "export" / PARTICIPANTS_FILE)
    assert list(rows[0].keys()) == PARTICIPANT_COLUMNS
    by_id = {row["telegram_id"]: row for row in rows}
    assert by_id["101"]["status"] == "active"
    assert by_id["102"]["status"] == "finished"
    assert by_id["103"]["status"] == "unsubscribed"
    assert by_id["101"]["participant_number"] == study_data[101]  # leading zeros kept
    assert by_id["101"]["condition"] == "1"
    assert by_id["101"]["wakeup_time"] == "07:30"
    assert by_id["101"]["time_offset_minutes"] == "-90"
    assert by_id["102"]["time_offset_minutes"] == ""
    assert by_id["101"]["messages_received"] == "2"
    datetime.strptime(by_id["101"]["first_registration"], "%Y-%m-%d %H:%M:%S")


def test_deliveries_csv_contains_every_message_oldest_first(tmp_path, db_handler, study_data):
    for message_id in range(6, 156):  # more than the 100 the console shows
        db_handler.record_outbound_message(101, message_id, "DAILY")

    OverviewExporter(db_handler, tmp_path).export()

    rows = read_csv(tmp_path / DELIVERIES_FILE)
    assert list(rows[0].keys()) == DELIVERY_COLUMNS
    assert len(rows) == 155
    assert [row["type"] for row in rows[:5]] == ["start link", "daily link", "end link", "end reminder", "bot message"]
    assert rows[0]["participant_number"] == study_data[101]
    assert rows[0]["sent_at"] <= rows[-1]["sent_at"]


def test_overview_text_matches_the_dashboard(tmp_path, db_handler, study_data):
    OverviewExporter(db_handler, tmp_path, participant_number_digits=5).export()

    text = (tmp_path / OVERVIEW_FILE).read_text(encoding="utf-8")
    assert "Stand: " in text
    for line in ("Gesamt:              3", "Aktiv:               1", "Beendet:             1",
                 "Abgemeldet:          1", "Gesamt:              5", "Umfrage-Links:       3",
                 "Andere Nachrichten:  2", "Vergeben:            3", "Länge:               5 Stellen"):
        assert line in text
    assert PARTICIPANTS_FILE in text and DELIVERIES_FILE in text


def test_overview_without_participant_numbers_has_no_number_section(tmp_path, db_handler, study_data):
    OverviewExporter(db_handler, tmp_path).export()

    assert "TEILNEHMERNUMMERN" not in (tmp_path / OVERVIEW_FILE).read_text(encoding="utf-8")


def test_files_open_cleanly_in_excel_and_leave_no_temporary_files(tmp_path, db_handler, study_data):
    tmp_path = tmp_path / "export"  # without the test database next to it
    OverviewExporter(db_handler, tmp_path).export()

    for name in (PARTICIPANTS_FILE, DELIVERIES_FILE):
        raw = (tmp_path / name).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel
        assert b"\r\n" in raw and b";" in raw.splitlines()[0]
    assert "ü".encode("utf-8") in (tmp_path / OVERVIEW_FILE).read_bytes()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([OVERVIEW_FILE, PARTICIPANTS_FILE, DELIVERIES_FILE])


def test_empty_database_gives_files_with_headers_only(tmp_path, db_handler):
    OverviewExporter(db_handler, tmp_path).export()

    assert read_csv(tmp_path / PARTICIPANTS_FILE) == []
    assert (tmp_path / PARTICIPANTS_FILE).read_text(encoding="utf-8-sig").startswith("telegram_id;")
    assert "unbekannt" in (tmp_path / OVERVIEW_FILE).read_text(encoding="utf-8")


def test_export_reflects_the_current_state(tmp_path, db_handler, study_data):
    exporter = OverviewExporter(db_handler, tmp_path)
    exporter.export()
    add_participant(db_handler, 104, datetime.now() + timedelta(days=1))

    exporter.export()

    assert len(read_csv(tmp_path / PARTICIPANTS_FILE)) == 4


def test_file_open_in_excel_is_skipped_with_one_warning(tmp_path, db_handler, study_data, monkeypatch, caplog):
    exporter = OverviewExporter(db_handler, tmp_path)
    exporter.export()
    real_replace = os.replace
    locked = {"on": True}

    def replace(source, target):
        if locked["on"] and str(target).endswith(PARTICIPANTS_FILE):
            raise PermissionError("file is open")
        return real_replace(source, target)

    monkeypatch.setattr(export_module.os, "replace", replace)
    caplog.set_level(logging.INFO)
    add_participant(db_handler, 104, datetime.now() + timedelta(days=1))

    exporter.export()
    exporter.export()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "open in another program" in warnings[0].getMessage()
    assert len(read_csv(tmp_path / PARTICIPANTS_FILE)) == 3  # old content kept, not half-written
    assert len(read_csv(tmp_path / DELIVERIES_FILE)) == 5    # other files are still updated
    assert not (tmp_path / (PARTICIPANTS_FILE + ".tmp")).exists()

    locked["on"] = False
    exporter.export()
    assert len(read_csv(tmp_path / PARTICIPANTS_FILE)) == 4
    assert any("updated again" in r.getMessage() for r in caplog.records)


# -----------------------------------------------------------------------------
# In the running bot
# -----------------------------------------------------------------------------


def test_bot_writes_the_files_at_startup_and_every_minute(tmp_path, config_dict, monkeypatch):
    study = Study(tmp_path, config_dict, monkeypatch)
    scheduler = Mock()
    monkeypatch.setattr(bot, "scheduler", scheduler)

    bot.schedule_notifications()

    export_job = [c for c in scheduler.add_job.call_args_list if c.args[0] is bot.export_overview][0]
    assert export_job.kwargs["seconds"] == 60
    assert export_job.kwargs["next_run_time"] <= datetime.now()
    assert bot.overview_exporter.participant_number_digits == study.config_handler.config.participantNumberDigits


@pytest.mark.asyncio
async def test_files_show_a_real_study_run(tmp_path, config_dict, monkeypatch):
    study = Study(tmp_path, config_dict, monkeypatch)
    monkeypatch.setattr(bot, "overview_exporter", OverviewExporter(study.db_handler, tmp_path / "export", 3))
    await study.subscribe(101)
    await study.send_daily()

    bot.export_overview()

    [participant] = read_csv(tmp_path / "export" / PARTICIPANTS_FILE)
    assert participant["participant_number"] == study.number(101)
    assert participant["status"] == "active"
    assert [row["type"] for row in read_csv(tmp_path / "export" / DELIVERIES_FILE)] == ["start link", "daily link"]


@pytest.mark.asyncio
async def test_files_are_written_once_more_when_the_bot_stops(tmp_path, monkeypatch):
    export = Mock()
    monkeypatch.setattr(bot, "overview_exporter", Mock(export=export))
    monkeypatch.setattr(bot, "scheduler", Mock(running=False), raising=False)
    monkeypatch.setattr(bot, "dashboard_stop_event", None)
    monkeypatch.setattr(bot, "dashboard_task", None)

    await bot.post_shutdown(Mock())

    export.assert_called_once()


def test_export_problems_never_stop_the_bot(monkeypatch, caplog):
    failing = Mock(folder="export")
    failing.export.side_effect = OSError("disk full")
    monkeypatch.setattr(bot, "overview_exporter", failing)

    bot.export_overview()

    assert any("Could not update the overview files" in r.getMessage() for r in caplog.records)
