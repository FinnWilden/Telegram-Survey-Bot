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
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Telegram Survey Bot.  If not, see <http://www.gnu.org/licenses/>.
"""
import json
from pathlib import Path
from random import randrange

from bot_utils.bot_enums import SurveyType
from bot_utils.config import Config
from bot_utils.config_validator import ConfigValidator


CONFIG_FILE = Path("config") / "config.json"


class ConfigHandler:
    """
    Class to parse and handle the config file.
    """

    config: Config

    def __init__(self) -> None:
        """
        Load and validate the config file.
        """
        with CONFIG_FILE.open(encoding="utf-8") as file:
            data = json.load(file)

        self.config = Config(**data)
        ConfigValidator.validate_config(self.config)

    def get_condition_count(self) -> int:
        """
        Return the number of experimental conditions.
        """
        return len(self.config.urls.start_url)

    def get_condition(self) -> int:
        """
        Return a random condition index.
        """
        return randrange(self.get_condition_count())

    def get_url(
        self,
        survey_type: SurveyType,
        condition: int,
        end_distribution: int = -1,
    ) -> str:
        """
        Return the survey URL for the given survey type, condition and end-distribution index.
        """
        if survey_type == SurveyType.SUBSCRIBE:
            return self.config.urls.start_url[condition]

        if survey_type == SurveyType.DAILY:
            return self.config.urls.daily_url[condition]

        if survey_type == SurveyType.END:
            return self.config.urls.end_url[condition][end_distribution]

        raise ValueError(f"Unknown survey type: {survey_type}")

    def get_message(self, survey_type: SurveyType) -> str:
        """
        Return the reminder message for the given survey type.
        """
        if survey_type == SurveyType.DAILY:
            return self.config.texts.daily_reminder

        if survey_type == SurveyType.END:
            return self.config.texts.end_reminder

        raise ValueError(f"No reminder message defined for survey type: {survey_type}")