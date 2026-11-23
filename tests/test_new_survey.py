"""
Tests for closing a survey and starting a new one with the same config (key u in the console):
the database and the overview files are saved under a new name, then the bot continues with an
empty database, so everyone can subscribe again.
"""
import logging
import sqlite3
from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from rich.console import Console

import bot
import bot_utils.db_handler as db_module
from bot_utils.console_dashboard import ConsoleDashboard
from bot_utils.db_handler import DbHandler
from bot_utils.overview_export import OverviewExporter
from bot_utils.schedule_util import ScheduleUtil
from test_link_deletion import Clock, deleted, make_study, sent_link_ids


def row_count(db_file, table):
    connection = sqlite3.connect(db_file)
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------


@pytest.fixture
def filled_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "db" / "userIdDb.db")
    db_handler = DbHandler()
    db_handler.insert_new_subscriber_entries(101, [datetime(2099, 1, 1, 9, 0)], bot.SurveyType.DAILY, 1)
    db_handler.register_participant(101, 1, "07:30")
    db_handler.assign_participant_number(101, 5)
    db_handler.insert_time_offset(101, 3600)
    db_handler.record_outbound_message(101, 7, "DAILY")
    db_handler.insert_message_id(101, 7, "DAILY", delete_at=datetime(2099, 1, 1, 10, 0))
    return db_handler


def test_archive_name_contains_the_label_next_to_the_database(filled_db, tmp_path):
    assert filled_db.archive_file("abgeschlossen_2026-11-23_10-45") == (
        tmp_path / "db" / "userIdDb_abgeschlossen_2026-11-23_10-45.db"
    )


def test_archive_keeps_everything_and_the_running_database_starts_empty(filled_db, tmp_path):
    archive = filled_db.archive_file("abgeschlossen_test")

    filled_db.archive_and_reset(archive)

    for table in ("subscribers", "participants", "participant_numbers", "offsets", "outbound_messages", "messages"):
        assert row_count(archive, table) == 1, table
    assert row_count(db_module.DB_FILE, "subscribers") == 0
    assert row_count(db_module.DB_FILE, "participants") == 0
    assert row_count(db_module.DB_FILE, "participant_numbers") == 0
    assert row_count(db_module.DB_FILE, "outbound_messages") == 0
    assert filled_db.get_dashboard_summary()["total_participants"] == 0
    assert not filled_db.is_already_subscribed(101)
    # links the bot still has to delete stay planned
    due = filled_db.get_due_message_deletions(datetime(2099, 1, 1, 11, 0))
    assert [(chat_id, message_id) for chat_id, message_id, _ in due] == [(101, 7)]


def test_new_survey_database_works_like_a_new_one(filled_db):
    filled_db.archive_and_reset(filled_db.archive_file("abgeschlossen_test"))

    filled_db.register_participant(202, 0)
    filled_db.record_outbound_message(202, 1, "SUBSCRIBE")

    assert filled_db.get_dashboard_summary()["total_participants"] == 1
    assert [row["chat_id"] for row in filled_db.get_recent_outbound_messages()] == [202]
    # reopening (bot restart) keeps using the new, emptied database
    assert DbHandler().get_dashboard_summary()["total_participants"] == 1


def test_existing_archive_is_never_overwritten(filled_db):
    archive = filled_db.archive_file("abgeschlossen_test")
    archive.write_bytes(b"older survey")

    with pytest.raises(FileExistsError):
        filled_db.archive_and_reset(archive)

    assert archive.read_bytes() == b"older survey"
    assert filled_db.get_dashboard_summary()["total_participants"] == 1


def test_failed_copy_leaves_the_running_survey_unchanged(filled_db, monkeypatch):
    archive = filled_db.archive_file("abgeschlossen_test")
    real_connect = sqlite3.connect

    class BrokenBackup:
        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            return getattr(self._connection, name)

        def backup(self, target):
            raise sqlite3.OperationalError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(
            DbHandler, "create_connection",
            staticmethod(lambda: BrokenBackup(_row_connection(real_connect))),
        )
        with pytest.raises(sqlite3.OperationalError):
            filled_db.archive_and_reset(archive)

    assert not archive.exists()
    assert row_count(db_module.DB_FILE, "participants") == 1
    assert row_count(db_module.DB_FILE, "subscribers") == 1


def _row_connection(connect):
    connection = connect(db_module.DB_FILE, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


# ----------------------------------------------------------------------------
# Bot: closing the survey while it runs
# ----------------------------------------------------------------------------


@pytest.fixture
def running_study(tmp_path, config_dict, monkeypatch):
    study = make_study(tmp_path, config_dict, monkeypatch)
    scheduler = BackgroundScheduler()  # not started: jobs stay pending and can be inspected
    monkeypatch.setattr(bot, "scheduler", scheduler)
    study.schedule_util = ScheduleUtil(scheduler, study.config_handler.config, study.db_handler)
    monkeypatch.setattr(bot, "schedule_util", study.schedule_util)
    monkeypatch.setattr(bot, "EXPORT_FOLDER", tmp_path / "export")
    monkeypatch.setattr(
        bot, "overview_exporter",
        OverviewExporter(study.db_handler, folder=tmp_path / "export", participant_number_digits=3),
    )
    for job_id in bot.BACKGROUND_JOB_IDS:
        scheduler.add_job(Mock(), "interval", seconds=60, id=job_id)
    study.scheduler = scheduler
    return study


@pytest.mark.asyncio
async def test_new_survey_saves_the_old_one_and_lets_everyone_subscribe_again(running_study, tmp_path):
    study = running_study
    await study.subscribe(101)
    old_number = study.number(101)
    assert {job.id for job in study.scheduler.get_jobs()} > bot.BACKGROUND_JOB_IDS
    study.scheduler.add_job(Mock(), "date", run_date=datetime(2099, 1, 1))  # an end reminder has no id

    note = bot.start_new_survey()

    archives = list((tmp_path).glob("study_abgeschlossen_*.db"))
    assert len(archives) == 1
    assert archives[0].name in note
    assert row_count(archives[0], "participants") == 1
    archived_export = list((tmp_path / "export").glob("abgeschlossen_*"))
    assert len(archived_export) == 1
    assert "101" in (archived_export[0] / "participants.csv").read_text(encoding="utf-8-sig")
    assert "101" not in (tmp_path / "export" / "participants.csv").read_text(encoding="utf-8-sig")

    # survey dates and reminders of the old survey are gone, the background jobs stay
    assert {job.id for job in study.scheduler.get_jobs()} == bot.BACKGROUND_JOB_IDS
    assert study.db_handler.get_dashboard_summary()["total_participants"] == 0

    # the same person can take part in the new survey
    study.telegram.clear()
    await study.subscribe(101)
    assert study.db_handler.is_already_subscribed(101)
    assert study.telegram.urls_for(101)
    assert study.number(101) is not None
    assert old_number is not None


@pytest.mark.asyncio
async def test_two_new_surveys_in_the_same_minute_get_separate_archives(running_study, tmp_path, monkeypatch):
    clock = Clock(monkeypatch)
    await running_study.subscribe(101)
    bot.start_new_survey()
    clock.advance(seconds=1)  # still the same minute in most cases; the name must differ anyway
    await running_study.subscribe(202)
    bot.start_new_survey()

    archives = sorted(tmp_path.glob("study_abgeschlossen_*.db"))
    assert len(archives) == 2
    participants = {row_count(archive, "participants") for archive in archives}
    assert participants == {1}


@pytest.mark.asyncio
async def test_failed_save_keeps_the_survey_running_and_leaves_no_copy(running_study, tmp_path, monkeypatch):
    study = running_study
    await study.subscribe(101)
    jobs_before = {job.id for job in study.scheduler.get_jobs()}

    def broken(_archive_file):
        raise OSError("disk full")

    monkeypatch.setattr(study.db_handler, "archive_and_reset", broken)
    with pytest.raises(OSError):
        bot.start_new_survey()

    assert list((tmp_path / "export").glob("abgeschlossen_*")) == []
    assert {job.id for job in study.scheduler.get_jobs()} == jobs_before
    assert study.db_handler.is_already_subscribed(101)


@pytest.mark.asyncio
async def test_links_of_the_closed_survey_are_still_deleted_as_planned(running_study, monkeypatch):
    clock = Clock(monkeypatch)
    study = running_study
    await study.subscribe(101)
    await study.send_daily()
    daily_link = sent_link_ids(study, 101)[-1]

    bot.start_new_survey()
    clock.advance(minutes=61)
    await bot.delete_due_messages_async()

    assert deleted(study) == [(101, daily_link)]


# ----------------------------------------------------------------------------
# Console
# ----------------------------------------------------------------------------


def make_dashboard(tmp_path, monkeypatch, new_survey=None, width=140, height=40):
    monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "dashboard.db")
    db_handler = DbHandler()
    db_handler.insert_new_subscriber_entries(101, [datetime(2099, 1, 1, 9, 0)], bot.SurveyType.DAILY, 0)
    db_handler.register_participant(101, 0)
    console = Console(file=StringIO(), width=width, height=height, record=True)
    return ConsoleDashboard(db_handler, console, new_survey=new_survey), console


def shown(dashboard, console):
    console.print(dashboard.render())
    return console.export_text()


def test_controls_tell_how_to_stop_the_bot(tmp_path, monkeypatch):
    dashboard, console = make_dashboard(tmp_path, monkeypatch)
    assert "Strg+C Bot beenden" in shown(dashboard, console)
    dashboard.handle_command("p")
    assert "Strg+C Bot beenden" in shown(dashboard, console)


def test_new_survey_needs_a_confirmation(tmp_path, monkeypatch):
    new_survey = Mock(return_value="Gesichert als db/x.db")
    dashboard, console = make_dashboard(tmp_path, monkeypatch, new_survey)
    assert "u Neue Umfrage" in shown(dashboard, console)

    dashboard.handle_command("u")
    question = shown(dashboard, console)
    assert "Neue Umfrage starten?" in question
    assert "abgeschlossen_<Datum>_<Uhrzeit>" in question
    assert "1 aktive Teilnehmende bekommen keine weiteren Links" in question
    assert "j Ja, Umfrage abschließen und neu starten" in question
    new_survey.assert_not_called()

    dashboard.handle_command("j")
    new_survey.assert_called_once()
    result = shown(dashboard, console)
    assert "Neue Umfrage gestartet" in result
    assert "Gesichert als db/x.db" in result

    dashboard.handle_command("d")  # the note disappears with the next key
    assert "Neue Umfrage gestartet" not in shown(dashboard, console)


@pytest.mark.parametrize("key", ["n", "u", "\r", " ", "x"])
def test_any_other_key_cancels_the_new_survey(tmp_path, monkeypatch, key):
    new_survey = Mock()
    dashboard, console = make_dashboard(tmp_path, monkeypatch, new_survey)

    dashboard.handle_command("u")
    dashboard.handle_command(key)

    new_survey.assert_not_called()
    assert "Abgebrochen" in shown(dashboard, console)
    assert not dashboard.confirming_new_survey


def test_failed_new_survey_is_shown_and_the_old_one_continues(tmp_path, monkeypatch):
    dashboard, console = make_dashboard(tmp_path, monkeypatch, Mock(side_effect=OSError("disk full")))

    dashboard.handle_command("u")
    dashboard.handle_command("j")

    output = shown(dashboard, console)
    assert "konnte nicht gestartet werden" in output
    assert "disk full" in output


def test_without_new_survey_function_the_key_does_nothing(tmp_path, monkeypatch):
    dashboard, console = make_dashboard(tmp_path, monkeypatch)
    dashboard.handle_command("u")
    assert not dashboard.confirming_new_survey
    assert "Neue Umfrage" not in shown(dashboard, console)


# ----------------------------------------------------------------------------
# Old end survey reminders
# ----------------------------------------------------------------------------


async def answer_no_to_reminder(study, chat_id, reminder_date_str, question_message_id=999):
    async def answer():
        return None

    update = study.update(chat_id)
    update.callback_query = SimpleNamespace(
        data=f"{bot.ER_NO}+{reminder_date_str}",
        message=SimpleNamespace(message_id=question_message_id),
        answer=answer,
    )
    await bot.handle_end_survey_reminder_callback(update, study.context())


@pytest.mark.asyncio
@pytest.mark.parametrize("close_survey", ["new survey", "unsubscribe"])
async def test_no_to_a_reminder_of_a_closed_survey_only_removes_the_question(
    running_study, monkeypatch, caplog, close_survey
):
    study = running_study
    monkeypatch.setattr(study.config_handler.config, "endSurveyReminderEnabled", True)
    await study.subscribe(101)
    await study.send_end()
    reminder_date_str = next(date.strftime("%Y-%m-%d-%H:%M") for date in study.db_handler.query_end_reminders())

    if close_survey == "new survey":
        bot.start_new_survey()
    else:
        await bot.unsubscribe(study.update(101, "/unsubscribe"), study.context())
    study.telegram.clear()
    caplog.set_level(logging.INFO)

    await answer_no_to_reminder(study, 101, reminder_date_str)

    assert deleted(study)[-1] == (101, 999)  # the question disappears as before
    assert study.telegram.urls_for(101) == []  # no end link of the old survey
    assert "no longer belongs to a running survey" in caplog.text
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.asyncio
async def test_no_to_a_current_reminder_still_sends_the_end_link(running_study, monkeypatch):
    study = running_study
    monkeypatch.setattr(study.config_handler.config, "endSurveyReminderEnabled", True)
    await study.subscribe(101)
    await study.send_end()
    reminder_date_str = next(date.strftime("%Y-%m-%d-%H:%M") for date in study.db_handler.query_end_reminders())
    study.telegram.clear()

    await answer_no_to_reminder(study, 101, reminder_date_str)

    assert len(study.telegram.urls_for(101)) == 1
