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
from dataclasses import dataclass
from datetime import time
from typing import Callable, List, Optional, Sequence, TypeVar

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot_utils.bot_enums import SurveyType
from bot_utils.config_handler import ConfigHandler

T = TypeVar("T")
R = TypeVar("R")

def destruct_tuple(f: Callable[..., R]) -> Callable[[tuple], R]:
    """
    Helper function to use functions on tuple elements.
    """
    return lambda args: f(*args)


@dataclass
class TimeSettings:
    """
    Settings for time-based survey scheduling.
    """
    wakeup_time: time
    delay_minutes_after_wakeup: int
    survey_count: int
    delay_minutes_between_surveys: int

class KeyboardBuilder:
    """
    Utility class for building Telegram inline keyboards.
    """

    @staticmethod
    def generate_link_markup(
        config_handler: ConfigHandler,
        survey_type: SurveyType,
        condition: int,
        end_index: int = -1,
    ) -> InlineKeyboardMarkup:
        """
        Generate an InlineKeyboardMarkup with one survey start button.
        """
        url = config_handler.get_url(survey_type, condition, end_index)

        return InlineKeyboardMarkup(
            KeyboardBuilder.build_menu(
                [InlineKeyboardButton(text="Start", url=url)],
                n_cols=1,
            )
        )

    @staticmethod
    def build_menu(
        buttons: Sequence[InlineKeyboardButton],
        n_cols: int,
        header_buttons: Optional[Sequence[InlineKeyboardButton]] = None,
        footer_buttons: Optional[Sequence[InlineKeyboardButton]] = None,
    ) -> List[List[InlineKeyboardButton]]:
        """
        Build a two-dimensional button layout for InlineKeyboardMarkup.
        """
        if n_cols < 1:
            raise ValueError("n_cols must be at least 1")

        menu = [list(buttons[i:i + n_cols]) for i in range(0, len(buttons), n_cols)]

        if header_buttons:
            menu.insert(0, list(header_buttons))

        if footer_buttons:
            menu.append(list(footer_buttons))

        return menu
