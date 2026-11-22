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

import asyncio
import atexit
import math
import os
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from rich.cells import cell_len
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bot_utils.db_handler import DbHandler


REFRESH_SECONDS = 2

# Lines a paged table view needs besides its data rows:
# title, header (3 lines incl. borders), bottom border, caption, control panel (3), two spare lines.
TABLE_VIEW_OVERHEAD = 11

# Participant columns that are hidden, in this order, when the terminal is too narrow.
# The participant's own answers (condition, wake-up time, offset) always stay visible.
OPTIONAL_PARTICIPANT_COLUMNS = ("Letzte Anm.", "Letzter Versand", "Erste Anm.", "Nachr.")

SURVEY_LINK_TYPES = ("SUBSCRIBE", "DAILY", "END")

MESSAGE_TYPE_LABELS = {
    "SUBSCRIBE": "Start-Link",
    "DAILY": "Tages-Link",
    "END": "End-Link",
    "END_REMINDER": "End-Erinnerung",
    "MESSAGE": "Bot-Nachricht",
}

VIEW_COMMANDS = {
    "d": "dashboard",
    "p": "participants",
    "v": "messages",
}


class _KeyReader:
    """
    Reads single key presses without echoing them.

    Echoed input would move the cursor and corrupt the live display, so the
    terminal is switched to non-echo, non-canonical mode while the dashboard runs.
    """

    def __init__(self, on_key: Callable[[str], None]) -> None:
        self._on_key = on_key
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._saved_mode: Any = None

    def start(self) -> bool:
        if os.name == "nt":
            target = self._read_windows
        else:
            try:
                self._enter_posix_mode()
            except (ImportError, OSError, ValueError):
                return False
            target = self._read_posix

        self._thread = threading.Thread(target=target, daemon=True, name="console-dashboard-input")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._restore_posix_mode()

    def _read_windows(self) -> None:
        import msvcrt

        while not self._stop.is_set():
            if not msvcrt.kbhit():
                self._stop.wait(0.05)
                continue
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()  # discard the second half of arrow/function keys
                continue
            self._on_key(key)

    def _enter_posix_mode(self) -> None:
        import termios

        fd = sys.stdin.fileno()
        self._saved_mode = termios.tcgetattr(fd)
        mode = termios.tcgetattr(fd)
        mode[3] &= ~(termios.ICANON | termios.ECHO)
        mode[6][termios.VMIN] = 1
        mode[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, mode)
        atexit.register(self._restore_posix_mode)

    def _restore_posix_mode(self) -> None:
        if self._saved_mode is None:
            return
        import termios

        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved_mode)
        except (OSError, ValueError):
            pass
        self._saved_mode = None

    def _read_posix(self) -> None:
        import select

        fd = sys.stdin.fileno()
        while not self._stop.is_set():
            readable, _, _ = select.select([fd], [], [], 0.2)
            if not readable:
                continue
            data = os.read(fd, 32).decode(errors="ignore")
            if not data:
                return
            if data.startswith("\x1b"):
                continue  # arrow/function key escape sequence
            for key in data:
                self._on_key(key)


class ConsoleDashboard:
    """
    Live operator dashboard with participant and delivery views for an interactive terminal.
    """

    def __init__(
        self,
        db_handler: DbHandler,
        console: Console,
        participant_number_range: tuple[int, int] | None = None,
    ) -> None:
        """
        :param participant_number_range: (min, max) of the participant numbers, or None
            when links are not completed with participant numbers
        """
        self.db_handler = db_handler
        self.console = console
        self.participant_number_range = participant_number_range
        self.view = "dashboard"
        self.page = 0
        self.command_queue: asyncio.Queue[str] = asyncio.Queue()

    @staticmethod
    def is_available(console: Console) -> bool:
        return bool(sys.stdin.isatty() and console.is_terminal)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_timestamp(value: str | None, fmt: str = "%d.%m.%Y %H:%M:%S") -> str:
        if value is None:
            return "Unbekannt"

        try:
            return datetime.fromisoformat(value).astimezone().strftime(fmt)
        except ValueError:
            return value

    @classmethod
    def _format_short_timestamp(cls, value: str | None) -> str:
        return cls._format_timestamp(value, "%d.%m. %H:%M")

    @staticmethod
    def _format_offset(seconds: int | None) -> str:
        if seconds is None:
            return "–"

        sign = "-" if seconds < 0 else "+"
        hours, minutes = divmod(round(abs(seconds) / 60), 60)
        return f"{sign}{hours}:{minutes:02d} h"

    @staticmethod
    def _format_optional(value: object) -> str:
        return "–" if value is None else str(value)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def handle_command(self, command: str) -> None:
        command = command.strip().lower()
        if command in VIEW_COMMANDS:
            self.view = VIEW_COMMANDS[command]
            self.page = 0
        elif command in ("n", " "):
            self.page += 1
        elif command == "b":
            self.page = max(0, self.page - 1)

    def _enqueue_key(self, loop: asyncio.AbstractEventLoop, key: str) -> None:
        try:
            loop.call_soon_threadsafe(self.command_queue.put_nowait, key)
        except RuntimeError:
            pass  # event loop already closed during shutdown

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self) -> Group:
        if self.view == "participants":
            return Group(self._render_participants(), self._render_controls())
        if self.view == "messages":
            return Group(self._render_messages(), self._render_controls())

        return Group(self._render_summary(), self._render_controls())

    def _safe_render(self) -> RenderableType:
        try:
            return self.render()
        except Exception as err:  # keep the dashboard alive, e.g. while the database is locked
            return Group(
                Panel(
                    f"Daten konnten gerade nicht geladen werden: {err}\n"
                    f"Neuer Versuch in {REFRESH_SECONDS} Sekunden.",
                    title="Telegram Survey Bot",
                    border_style="red",
                ),
                self._render_controls(),
            )

    def _paginate(self, rows: list[Any]) -> tuple[list[Any], str]:
        per_page = max(1, self.console.size.height - TABLE_VIEW_OVERHEAD)
        page_count = max(1, math.ceil(len(rows) / per_page))
        self.page = min(self.page, page_count - 1)
        start = self.page * per_page
        return rows[start:start + per_page], f"Seite {self.page + 1}/{page_count} · {len(rows)} Einträge"

    def _render_summary(self) -> Panel:
        summary = self.db_handler.get_dashboard_summary()
        counts = summary["message_counts"]
        survey_links = sum(counts.get(name, 0) for name in SURVEY_LINK_TYPES)

        table = Table.grid(padding=(0, 3))
        table.add_column(style="bold")
        table.add_column(justify="right")
        table.add_column(style="bold")
        table.add_column(justify="right")
        table.add_row(
            "Teilnehmende gesamt",
            str(summary["total_participants"]),
            "Aktiv angemeldet",
            str(summary["active_participants"]),
        )
        table.add_row(
            "Erste Anmeldung",
            self._format_timestamp(summary["first_registration"]),
            "Letzte Anmeldung",
            self._format_timestamp(summary["last_registration"]),
        )
        table.add_row(
            "Nachrichten gesamt",
            str(sum(counts.values())),
            "Umfrage-Links",
            str(survey_links),
        )
        table.add_row(
            "Start-Links",
            str(counts.get("SUBSCRIBE", 0)),
            "Tages-Links",
            str(counts.get("DAILY", 0)),
        )
        table.add_row(
            "End-Links",
            str(counts.get("END", 0)),
            "Andere Nachrichten",
            str(sum(
                count
                for message_type, count in counts.items()
                if message_type not in SURVEY_LINK_TYPES
            )),
        )
        if self.participant_number_range is not None:
            min_number, max_number = self.participant_number_range
            range_size = max_number - min_number + 1
            used = self.db_handler.count_participant_numbers(min_number, max_number)
            free = range_size - used
            table.add_row(
                "Nummern vergeben",
                f"{used} / {range_size}",
                "Nummern frei",
                f"[bold red]{free}[/]" if free <= max(1, range_size // 10) else str(free),
            )
        return Panel(table, title="Telegram Survey Bot · Live-Übersicht", border_style="cyan")

    def _render_participants(self) -> Table:
        rows, page_info = self._paginate(self.db_handler.get_participant_overview())

        columns: list[tuple[str, str, Callable[[Any], str | Text]]] = [
            ("Telegram-ID", "right", lambda p: str(p["chat_id"])),
            *(
                [("Nr.", "right", lambda p: self._format_optional(p["participant_number"]))]
                if self.participant_number_range is not None else []
            ),
            ("Erste Anm.", "left", lambda p: self._format_short_timestamp(p["first_registered_at"])),
            ("Letzte Anm.", "left", lambda p: self._format_short_timestamp(p["last_registered_at"])),
            ("Status", "left", lambda p: Text("Aktiv", style="green") if p["is_active"] else Text("Abgemeldet", style="dim")),
            ("Kond.", "right", lambda p: self._format_optional(p["condition"])),
            ("Weckzeit", "left", lambda p: self._format_optional(p["wakeup_time"])),
            ("Versatz", "right", lambda p: self._format_offset(p["time_offset"])),
            ("Nachr.", "right", lambda p: str(p["message_count"])),
            ("Letzter Versand", "left", lambda p: self._format_short_timestamp(p["last_message_at"])),
        ]
        cells = [[render(participant) for _, _, render in columns] for participant in rows]

        visible = self._fit_columns([header for header, _, _ in columns], cells)
        caption_parts = [page_info, "Versatz = Uhrzeit der Person minus Serverzeit"]
        if len(visible) < len(columns):
            caption_parts.append("weitere Spalten bei breiterem Fenster")
        # The page size assumes a one-line caption, so drop hints that would wrap.
        while len(caption_parts) > 1 and cell_len(" · ".join(caption_parts)) > self.console.width:
            caption_parts.pop()
        caption = " · ".join(caption_parts)

        table = Table(title="Teilnehmende und ihre Angaben", caption=caption, expand=True)
        for index in visible:
            header, justify, _ = columns[index]
            table.add_column(header, justify=justify, no_wrap=True)
        for row in cells:
            table.add_row(*(row[index] for index in visible))

        return table

    def _fit_columns(self, headers: list[str], cells: list[list[str | Text]]) -> list[int]:
        """
        Return the indices of the columns that fit into the terminal width.
        """
        widths = [
            max([cell_len(header)] + [cell_len(str(row[index])) for row in cells])
            for index, header in enumerate(headers)
        ]
        visible = list(range(len(headers)))

        def table_width() -> int:
            # each column: content + 2 padding + 1 border, plus the closing border
            return sum(widths[index] + 3 for index in visible) + 1

        for header in OPTIONAL_PARTICIPANT_COLUMNS:
            if table_width() <= self.console.width:
                break
            visible.remove(headers.index(header))

        return visible

    def _render_messages(self) -> Table:
        rows, page_info = self._paginate(self.db_handler.get_recent_outbound_messages())

        table = Table(title="Letzte 100 versendete Nachrichten", caption=page_info, expand=True)
        table.add_column("Versandzeit", no_wrap=True)
        table.add_column("Telegram-ID", justify="right", no_wrap=True)
        table.add_column("Typ", no_wrap=True)

        for message in rows:
            table.add_row(
                self._format_timestamp(message["sent_at"]),
                str(message["chat_id"]),
                MESSAGE_TYPE_LABELS.get(message["message_type"], message["message_type"]),
            )

        return table

    def _render_controls(self) -> Panel:
        controls = "[bold]d[/] Dashboard   [bold]p[/] Teilnehmende   [bold]v[/] Versandverlauf"
        if self.view != "dashboard":
            controls += "   [bold]n[/]/[bold]b[/] Seite vor/zurück"
        return Panel(controls, border_style="dim")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self, stop_event: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        key_reader = _KeyReader(lambda key: self._enqueue_key(loop, key))
        key_reader.start()

        try:
            with Live(self._safe_render(), console=self.console, auto_refresh=False) as live:
                while not stop_event.is_set():
                    try:
                        command = await asyncio.wait_for(self.command_queue.get(), timeout=REFRESH_SECONDS)
                        self.handle_command(command)
                    except asyncio.TimeoutError:
                        pass
                    live.update(self._safe_render(), refresh=True)
        finally:
            key_reader.stop()
