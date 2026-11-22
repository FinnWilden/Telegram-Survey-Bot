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

Readable error messages for problems that stop the bot from starting.

The people running the bot are often researchers without programming
experience, so these messages explain what went wrong and how to fix it
instead of showing a Python traceback. They never contain the bot token.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import yaml
from telegram.error import InvalidToken, NetworkError


PLACEHOLDER_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# "<bot id>:<secret>", e.g. 123456789:AAH... (the secret uses letters, digits, '_' and '-')
TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]+$")

WIKI_CONFIGURE = "https://github.com/FinnWilden/Telegram-Survey-Bot/wiki/Configure"
WIKI_CREATE_BOT = "https://github.com/FinnWilden/Telegram-Survey-Bot/wiki/Create-and-Configure-Telegram-Bot"

HOW_TO_GET_TOKEN = (
    "In Telegram, open @BotFather, send /mybots, choose your bot and press 'API Token'. "
    "Copy the token into 'api_token' (keep the quotes) and save the file. Guide: " + WIKI_CREATE_BOT
)


class StartupError(Exception):
    """
    A problem that stops the bot from starting, described for the person running it.
    """

    def __init__(self, title: str, causes: list[str] | None = None, fix: str | None = None) -> None:
        super().__init__(title)
        self.title = title
        self.causes = causes or []
        self.fix = fix

    def describe(self) -> str:
        lines = [self.title]
        if self.causes:
            lines.append("")
            lines.append("Possible causes:")
            lines.extend("  - " + cause for cause in self.causes)
        if self.fix:
            lines.append("")
            lines.append("How to fix it: " + self.fix)
        return "\n".join(lines)


def report(error: StartupError) -> None:
    """
    Log a startup error as one readable message, without a traceback.
    """
    logging.getLogger("bot").error("The bot could not be started.\n\n%s\n", error.describe())


# -----------------------------------------------------------------------------
# Bot token
# -----------------------------------------------------------------------------


def check_api_token(token: object, config_file: Path) -> str:
    """
    Check the token before contacting Telegram and return it without surrounding spaces.

    :raises StartupError: when the token is missing, still the placeholder or malformed
    """
    if not isinstance(token, str) or not token.strip():
        raise StartupError(
            f"No Telegram bot token is set in 'api_token' of {config_file}.",
            fix=HOW_TO_GET_TOKEN,
        )

    token = token.strip()
    if token == PLACEHOLDER_TOKEN:
        raise StartupError(
            f"The Telegram bot token in {config_file} is still the placeholder '{PLACEHOLDER_TOKEN}'.",
            causes=[
                "The token was not entered yet.",
                "The token was entered, but the file was not saved.",
                f"The token was entered in a different file than {config_file}. Without a file name, "
                "the bot uses config/config.yml; another file must be given when starting, "
                "e.g. 'python bot.py config/test.yml'.",
            ],
            fix=HOW_TO_GET_TOKEN,
        )

    if not TOKEN_PATTERN.match(token):
        raise StartupError(
            f"The value of 'api_token' in {config_file} does not look like a Telegram bot token.",
            causes=[
                "A bot token looks like 123456789:AAH4x... (digits, a colon, then letters, digits, '_' or '-').",
                "Only part of the token was copied, or extra characters such as spaces, line breaks, "
                "a second pair of quotes or the word 'bot' in front were copied with it.",
            ],
            fix=HOW_TO_GET_TOKEN,
        )

    return token


def invalid_token_error(config_file: Path) -> StartupError:
    return StartupError(
        "Telegram rejected the bot token. The bot could not log in.",
        causes=[
            f"The token in {config_file} was changed but the file was not saved.",
            "The token was copied incompletely or with a typo.",
            "A new token was created in @BotFather (/revoke). Old tokens stop working immediately; "
            "tokens do not expire on their own.",
            "The bot was deleted in @BotFather.",
            f"The bot was started with a different config file than the one you edited (used: {config_file}).",
        ],
        fix=HOW_TO_GET_TOKEN,
    )


def network_error(error: NetworkError) -> StartupError:
    return StartupError(
        "The bot could not connect to Telegram.",
        causes=[
            "This computer has no internet connection right now.",
            "A firewall, VPN or proxy (for example in a university or company network) blocks "
            "api.telegram.org.",
            "Telegram is temporarily unavailable.",
            f"Technical detail: {error.message}",
        ],
        fix="Check the internet connection and start the bot again. If the problem stays, try another network.",
    )


# -----------------------------------------------------------------------------
# Config file
# -----------------------------------------------------------------------------


def config_file_not_found(error: FileNotFoundError) -> StartupError:
    if error.filename:
        title = f"The config file '{error.filename}' was not found."
    else:
        title = "No config file was found in the 'config' folder (expected config/config.yml)."
    return StartupError(
        title,
        causes=[
            "The file name or folder was misspelled when starting the bot.",
            "The bot was started from a different folder. Start it from the folder that contains "
            "the 'config' folder.",
            "The file was renamed, moved or saved with a different extension (e.g. config.yml.txt).",
        ],
        fix="Start the bot without a file name to use config/config.yml, or give the correct path, "
            "e.g. 'python bot.py config/test.yml'.",
    )


def _position_text(line: int | None, column: int | None) -> str:
    if line is None:
        return ""
    return f" (line {line}, column {column})" if column is not None else f" (line {line})"


def config_syntax_error(error: yaml.YAMLError | json.JSONDecodeError, config_file: Path) -> StartupError:
    if isinstance(error, json.JSONDecodeError):
        position = _position_text(error.lineno, error.colno)
        detail = error.msg
    else:
        mark = getattr(error, "problem_mark", None)
        position = _position_text(mark.line + 1, mark.column + 1) if mark is not None else ""
        detail = getattr(error, "problem", None) or str(error)

    return StartupError(
        f"The config file {config_file} could not be read because of a formatting error{position}.",
        causes=[
            "The indentation is wrong. Settings that belong together must start at exactly the same "
            "position; use spaces, not tabs.",
            "A text with special characters such as ':' or '#' is not in quotes.",
            "A quote, bracket or comma is missing or one too many.",
            f"Technical detail: {detail}",
        ],
        fix="Open the file, look at the line mentioned above and the line before it, and compare it with "
            "the example in the wiki: " + WIKI_CONFIGURE,
    )


def config_incomplete(error: TypeError, config_file: Path) -> StartupError:
    message = str(error)
    missing = re.findall(r"'(\w+)'", message) if "missing" in message else []
    unknown = re.search(r"unexpected keyword argument '(\w+)'", message)

    if missing:
        title = f"The config file {config_file} is missing the setting(s): {', '.join(missing)}."
        causes = [
            "The setting was deleted or its name was changed.",
            "The setting is indented under the wrong section.",
            "The config file is from an older version of the bot.",
        ]
    elif unknown:
        title = f"The config file {config_file} contains the unknown setting '{unknown.group(1)}'."
        causes = [
            "The name of the setting is misspelled (names are case-sensitive).",
            "The setting is indented under the wrong section.",
            "The setting belongs to a newer version of the bot than the one you are running.",
        ]
    else:
        title = f"The config file {config_file} contains an invalid setting."
        causes = [f"Technical detail: {message}"]

    return StartupError(
        title,
        causes=causes,
        fix="Compare your file with the config.yml that comes with the bot or with the wiki: " + WIKI_CONFIGURE,
    )


# -----------------------------------------------------------------------------
# Log filter
# -----------------------------------------------------------------------------


class HideBootstrapTracebacks(logging.Filter):
    """
    Hide python-telegram-bot's own traceback when logging in to Telegram fails at startup.

    The bot reports these errors with a readable message instead. PTB's traceback would also
    print the bot token into the console and the log file.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info or "Bootstrap" not in record.getMessage():
            return True
        return not isinstance(record.exc_info[1], (InvalidToken, NetworkError))
