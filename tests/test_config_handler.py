import json
import yaml

import pytest

from bot_utils.bot_enums import SurveyType
from bot_utils.config_handler import ConfigHandler

@pytest.fixture
def config_handler(tmp_path, config_dict):
    config_file = tmp_path / "config.json"

    config_file.write_text(
        json.dumps(config_dict()),
        encoding="utf-8",
    )

    return ConfigHandler(config_file=config_file)


def test_invalid_config_raises(tmp_path, config_dict):
    config_file = tmp_path / "config.json"

    invalid_config = config_dict(
        subscription_start_date="2026-05-21 08:00",
        subscription_deadline="2026-05-20 20:00",
    )

    config_file.write_text(
        json.dumps(invalid_config),
        encoding="utf-8",
    )

    with pytest.raises(Exception):
        ConfigHandler(config_file=config_file)


def test_loads_config_file(config_handler):
    assert config_handler.config.api_token == "dummy-token"
    assert config_handler.config.texts.welcome == "Welcome"


def test_get_condition_count(config_handler):
    assert config_handler.get_condition_count() == 2


def test_get_condition_returns_valid_condition_index(config_handler):
    for _ in range(100):
        condition = config_handler.get_condition()
        assert condition in (0, 1)


def test_get_url_for_subscribe(config_handler):
    assert (
        config_handler.get_url(SurveyType.SUBSCRIBE, condition=1)
        == "https://example.com/start-b"
    )


def test_get_url_for_daily(config_handler):
    assert (
        config_handler.get_url(SurveyType.DAILY, condition=1)
        == "https://example.com/daily-b"
    )


def test_get_url_for_end(config_handler):
    assert (
        config_handler.get_url(SurveyType.END, condition=1, end_distribution=0)
        == "https://example.com/end-b"
    )


def test_get_message_for_daily(config_handler):
    assert config_handler.get_message(SurveyType.DAILY) == "Daily reminder"


def test_get_message_for_end(config_handler):
    assert config_handler.get_message(SurveyType.END) == "End reminder"


def test_get_message_raises_for_subscribe(config_handler):
    with pytest.raises(ValueError):
        config_handler.get_message(SurveyType.SUBSCRIBE)


def test_loads_yaml_config_file(tmp_path, config_dict):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        yaml.safe_dump(config_dict(), sort_keys=False),
        encoding="utf-8",
    )

    handler = ConfigHandler(config_file=config_file)

    assert handler.config_file == config_file
    assert handler.config.api_token == "dummy-token"
    assert handler.config.texts.welcome == "Welcome"


def test_prefers_yml_over_yaml_and_json(tmp_path, monkeypatch, config_dict):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    json_config = config_dict(api_token="json-token")
    yaml_config = config_dict(api_token="yaml-token")
    yml_config = config_dict(api_token="yml-token")

    (config_dir / "config.json").write_text(
        json.dumps(json_config),
        encoding="utf-8",
    )
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(yaml_config, sort_keys=False),
        encoding="utf-8",
    )
    (config_dir / "config.yml").write_text(
        yaml.safe_dump(yml_config, sort_keys=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "bot_utils.config_handler.CONFIG_FILES",
        [
            config_dir / "config.yml",
            config_dir / "config.yaml",
            config_dir / "config.json",
        ],
    )

    handler = ConfigHandler()

    assert handler.config_file == config_dir / "config.yml"
    assert handler.config.api_token == "yml-token"