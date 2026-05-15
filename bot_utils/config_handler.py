from __future__ import annotations

import json
import logging
from pathlib import Path
from random import randrange
from typing import Any

import yaml

from bot_utils.bot_enums import SurveyType
from bot_utils.config import Config
from bot_utils.config_validator import ConfigValidator


CONFIG_DIR = Path("config")
CONFIG_FILES = [
    CONFIG_DIR / "config.yml",
    CONFIG_DIR / "config.yaml",
    CONFIG_DIR / "config.json",
]


class ConfigHandler:
    """
    Class to parse and handle the config file.
    """

    config: Config
    config_file: Path
    logger: logging.Logger

    def __init__(self, config_file: Path | None = None) -> None:
        """
        Load and validate the config file.
        """
        self.logger = logging.getLogger(__name__)

        self.config_file = config_file or self._find_config_file()
        self.logger.info("Using config file: %s", self.config_file)

        data = self._load_config_file(self.config_file)

        self.config = Config(**data)
        ConfigValidator.validate_config(self.config)

    @staticmethod
    def _find_config_file() -> Path:
        """
        Find the first available config file.

        Priority:
        1. config/config.yml
        2. config/config.yaml
        3. config/config.json
        """
        for config_file in CONFIG_FILES:
            if config_file.exists():
                return config_file

        expected_files = ", ".join(str(path) for path in CONFIG_FILES)
        raise FileNotFoundError(
            f"No config file found. Expected one of: {expected_files}"
        )

    @staticmethod
    def _load_config_file(config_file: Path) -> dict[str, Any]:
        """
        Load a JSON or YAML config file.
        """
        suffix = config_file.suffix.lower()

        with config_file.open(encoding="utf-8") as file:
            if suffix in {".yml", ".yaml"}:
                data = yaml.safe_load(file)
            elif suffix == ".json":
                data = json.load(file)
            else:
                raise ValueError(
                    f"Unsupported config file format: {config_file.suffix}"
                )

        if data is None:
            raise ValueError(f"Config file is empty: {config_file}")

        if not isinstance(data, dict):
            raise TypeError(
                f"Config file must contain a dictionary/object at top level: {config_file}"
            )

        return data

    def get_condition_count(self) -> int:
        return len(self.config.urls.start_url)

    def get_condition(self) -> int:
        return randrange(self.get_condition_count())

    def get_url(
        self,
        survey_type: SurveyType,
        condition: int,
        end_distribution: int = -1,
    ) -> str:
        if survey_type == SurveyType.SUBSCRIBE:
            return self.config.urls.start_url[condition]

        if survey_type == SurveyType.DAILY:
            return self.config.urls.daily_url[condition]

        if survey_type == SurveyType.END:
            return self.config.urls.end_url[condition][end_distribution]

        raise ValueError(f"Unknown survey type: {survey_type}")

    def get_message(self, survey_type: SurveyType) -> str:
        if survey_type == SurveyType.DAILY:
            return self.config.texts.daily_reminder

        if survey_type == SurveyType.END:
            return self.config.texts.end_reminder

        raise ValueError(f"No reminder message defined for survey type: {survey_type}")