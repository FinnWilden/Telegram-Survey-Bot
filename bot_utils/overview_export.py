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

Readable copies of the operator console: an overview text file and CSV files with all
participants and all sent messages, so the study can be followed without opening the database.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import datetime
from pathlib import Path

from bot_utils.db_handler import DbHandler


EXPORT_FOLDER = Path("export")
OVERVIEW_FILE = "overview.txt"
PARTICIPANTS_FILE = "participants.csv"
DELIVERIES_FILE = "deliveries.csv"

# Semicolon and UTF-8 with BOM: a double click opens the files in Excel with separate columns
# and correct umlauts, also with German regional settings.
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"

SURVEY_LINK_TYPES = ("SUBSCRIBE", "DAILY", "END")

MESSAGE_TYPES = {
    "SUBSCRIBE": "start link",
    "DAILY": "daily link",
    "END": "end link",
    "END_REMINDER": "end reminder",
    "MESSAGE": "bot message",
}

PARTICIPANT_COLUMNS = [
    "telegram_id",
    "participant_number",
    "status",
    "first_registration",
    "last_registration",
    "condition",
    "wakeup_time",
    "time_offset_minutes",
    "messages_received",
    "last_message",
]

DELIVERY_COLUMNS = ["sent_at", "telegram_id", "participant_number", "type"]


def format_time(value: str | None) -> str:
    """
    Stored ISO time -> "YYYY-MM-DD HH:MM:SS" in local time, or "" when unknown.
    """
    if value is None:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def blank(value: object) -> object:
    return "" if value is None else value


class OverviewExporter:
    """
    Writes overview.txt, participants.csv and deliveries.csv into the export folder.
    """

    def __init__(
        self,
        db_handler: DbHandler,
        folder: Path = EXPORT_FOLDER,
        participant_number_digits: int | None = None,
    ) -> None:
        """
        :param participant_number_digits: configured length of participant numbers, or None
            when links are not completed with participant numbers
        """
        self.db_handler = db_handler
        self.folder = Path(folder)
        self.participant_number_digits = participant_number_digits
        self.logger = logging.getLogger(__name__)
        self._blocked_files: set[str] = set()

    def export(self) -> None:
        """
        Write all three files. A file that cannot be replaced (e.g. open in Excel) is skipped
        and written again at the next export.
        """
        self.folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        participants = self.db_handler.get_participant_overview()
        self._write(PARTICIPANTS_FILE, self._participants_csv(participants), CSV_ENCODING)
        self._write(DELIVERIES_FILE, self._deliveries_csv(self.db_handler.get_outbound_messages()), CSV_ENCODING)
        self._write(OVERVIEW_FILE, self._overview_text(now), "utf-8")

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    @staticmethod
    def _csv(columns: list[str], rows: list[list[object]]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
        return buffer.getvalue()

    def _participants_csv(self, participants: list[dict]) -> str:
        rows = [
            [
                p["chat_id"],
                blank(p["participant_number"]),
                p["status"],
                format_time(p["first_registered_at"]),
                format_time(p["last_registered_at"]),
                blank(p["condition"]),
                blank(p["wakeup_time"]),
                "" if p["time_offset"] is None else round(p["time_offset"] / 60),
                p["message_count"],
                format_time(p["last_message_at"]),
            ]
            for p in participants
        ]
        return self._csv(PARTICIPANT_COLUMNS, rows)

    def _deliveries_csv(self, deliveries: list[dict]) -> str:
        rows = [
            [
                format_time(d["sent_at"]),
                d["chat_id"],
                blank(d["participant_number"]),
                MESSAGE_TYPES.get(d["message_type"], d["message_type"]),
            ]
            for d in deliveries
        ]
        return self._csv(DELIVERY_COLUMNS, rows)

    def _overview_text(self, now: datetime) -> str:
        summary = self.db_handler.get_dashboard_summary()
        counts = summary["message_counts"]
        other = sum(count for message_type, count in counts.items() if message_type not in SURVEY_LINK_TYPES)

        lines = [
            "Telegram Survey Bot - Übersicht",
            f"Stand: {now.strftime('%d.%m.%Y %H:%M:%S')} (wird jede Minute aktualisiert, solange der Bot läuft)",
            "",
            "TEILNEHMENDE",
            f"  Gesamt:              {summary['total_participants']}",
            f"  Aktiv:               {summary['active_participants']}",
            f"  Beendet:             {summary['finished_participants']}",
            f"  Abgemeldet:          {summary['unsubscribed_participants']}",
            f"  Erste Anmeldung:     {format_time(summary['first_registration']) or 'unbekannt'}",
            f"  Letzte Anmeldung:    {format_time(summary['last_registration']) or 'unbekannt'}",
            "",
            "NACHRICHTEN",
            f"  Gesamt:              {sum(counts.values())}",
            f"  Umfrage-Links:       {sum(counts.get(t, 0) for t in SURVEY_LINK_TYPES)}",
            f"    Start-Links:       {counts.get('SUBSCRIBE', 0)}",
            f"    Tages-Links:       {counts.get('DAILY', 0)}",
            f"    End-Links:         {counts.get('END', 0)}",
            f"  Andere Nachrichten:  {other}",
        ]
        if self.participant_number_digits is not None:
            lines += [
                "",
                "TEILNEHMERNUMMERN",
                f"  Vergeben:            {self.db_handler.count_participant_numbers()}",
                f"  Länge:               {self.participant_number_digits} Stellen",
            ]
        lines += [
            "",
            "WEITERE DATEIEN IN DIESEM ORDNER (öffnen z. B. mit Excel)",
            f"  {PARTICIPANTS_FILE}  alle Teilnehmenden mit ihren Angaben und ihrem Status",
            "                      (active = Termine stehen aus, finished = alle Termine vorbei,",
            "                       unsubscribed = abgemeldet)",
            f"  {DELIVERIES_FILE}    jede verschickte Nachricht mit Zeit und Typ",
            "",
            "Hinweis: Excel zeigt Teilnehmernummern ohne führende Nullen an (04711 wird zu 4711).",
            "In der Datei selbst und in den Umfrage-Links steht die Nummer vollständig.",
            "",
            "Die Dateien werden vom Bot überschrieben. Zum Bearbeiten bitte eine Kopie anlegen.",
        ]
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def _write(self, name: str, content: str, encoding: str) -> None:
        """
        Write via a temporary file, so a reader never sees a half-written file.
        """
        target = self.folder / name
        temporary = self.folder / (name + ".tmp")
        try:
            with open(temporary, "w", encoding=encoding, newline="\r\n") as file:
                file.write(content)
            os.replace(temporary, target)
        except PermissionError:
            if name not in self._blocked_files:
                self._blocked_files.add(name)
                self.logger.warning(
                    "%s could not be updated, probably because it is open in another program "
                    "(e.g. Excel). It is updated again once it is closed.", target
                )
            try:
                temporary.unlink()
            except OSError:
                pass
            return

        if name in self._blocked_files:
            self._blocked_files.discard(name)
            self.logger.info("%s is updated again.", target)
