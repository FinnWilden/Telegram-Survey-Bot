import sqlite3
from io import StringIO

from rich.console import Console

import bot_utils.db_handler as db_module
from bot_utils.console_dashboard import TABLE_VIEW_OVERHEAD, ConsoleDashboard
from bot_utils.db_handler import DbHandler


def test_dashboard_renders_persistent_counts_and_participant_details(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "dashboard.db")
    db_handler = DbHandler()
    db_handler.insert_time_offset(123, 5400)
    db_handler.register_participant(123, 2, "07:15")
    db_handler.record_outbound_message(123, 10, "SUBSCRIBE")
    db_handler.record_outbound_message(123, 11, "DAILY")

    console = Console(file=StringIO(), width=120, record=True)
    dashboard = ConsoleDashboard(db_handler, console)

    console.print(dashboard.render())
    summary_output = console.export_text()
    assert "Teilnehmende gesamt" in summary_output
    assert "Umfrage-Links" in summary_output
    assert "2" in summary_output

    dashboard.view = "participants"
    console.print(dashboard.render())
    participant_output = console.export_text()
    assert "Telegram-ID" in participant_output
    assert "123" in participant_output
    assert "Letzter Versand" in participant_output
    assert "Aktiv" in participant_output
    assert "07:15" in participant_output
    assert "+1:30 h" in participant_output

    dashboard.view = "messages"
    console.print(dashboard.render())
    message_output = console.export_text()
    assert "Letzte 100 versendete Nachrichten" in message_output
    assert "Start-Link" in message_output
    assert "Tages-Link" in message_output


def make_dashboard(tmp_path, monkeypatch, participants=0, width=120, height=30):
    monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "dashboard.db")
    db_handler = DbHandler()
    for index in range(participants):
        db_handler.register_participant(1000 + index, index % 2)
    console = Console(file=StringIO(), width=width, height=height, record=True)
    return ConsoleDashboard(db_handler, console), console


def test_commands_switch_views_and_pages(tmp_path, monkeypatch):
    dashboard, _ = make_dashboard(tmp_path, monkeypatch)

    dashboard.handle_command("P")
    assert dashboard.view == "participants"
    dashboard.handle_command("n")
    dashboard.handle_command("n")
    dashboard.handle_command("b")
    assert dashboard.page == 1
    dashboard.handle_command(chr(13))  # Enter is ignored
    assert dashboard.page == 1
    dashboard.handle_command("v")
    assert (dashboard.view, dashboard.page) == ("messages", 0)
    dashboard.handle_command("b")
    assert dashboard.page == 0
    dashboard.handle_command("d")
    assert dashboard.view == "dashboard"


def test_participant_view_pages_to_fit_terminal_height(tmp_path, monkeypatch):
    dashboard, console = make_dashboard(tmp_path, monkeypatch, participants=50, height=30)
    dashboard.view = "participants"
    rows_per_page = 30 - TABLE_VIEW_OVERHEAD

    console.print(dashboard.render())
    first_page = console.export_text()
    assert "1000" in first_page
    assert str(1000 + rows_per_page) not in first_page
    assert "Seite 1/3 · 50 Einträge" in first_page
    assert len(first_page.splitlines()) <= 30

    dashboard.page = 99  # beyond the end is clamped to the last page
    console.print(dashboard.render())
    last_page = console.export_text()
    assert "1049" in last_page
    assert "Seite 3/3" in last_page


def test_narrow_terminal_hides_optional_columns_but_keeps_participant_answers(tmp_path, monkeypatch):
    dashboard, console = make_dashboard(tmp_path, monkeypatch, participants=1, width=80)
    dashboard.view = "participants"

    console.print(dashboard.render())
    output = console.export_text()
    for header in ("Telegram-ID", "Status", "Kond.", "Weckzeit", "Versatz"):
        assert header in output
    assert "Letzte Anm." not in output
    assert max(len(line) for line in output.splitlines()) <= 80


def test_render_error_is_shown_instead_of_stopping_the_dashboard(tmp_path, monkeypatch):
    dashboard, console = make_dashboard(tmp_path, monkeypatch)

    def broken_summary():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(dashboard.db_handler, "get_dashboard_summary", broken_summary)
    console.print(dashboard._safe_render())
    assert "database is locked" in console.export_text()


def test_offset_formatting():
    assert ConsoleDashboard._format_offset(None) == "–"
    assert ConsoleDashboard._format_offset(0) == "+0:00 h"
    assert ConsoleDashboard._format_offset(-5400) == "-1:30 h"
    assert ConsoleDashboard._format_offset(7200) == "+2:00 h"
