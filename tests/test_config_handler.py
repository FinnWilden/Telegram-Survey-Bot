import json
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Participant numbers
# ---------------------------------------------------------------------------


def make_participant_number_handler(tmp_path, config_dict, pad_to_digits=0, **url_overrides):
    data = config_dict(
        useParticipantNumbers=True,
        participantNumberSettings={"minNumber": 1, "maxNumber": 999, "padToDigits": pad_to_digits},
    )
    data["urls"].update(url_overrides)
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    return ConfigHandler(config_file=config_file)


def test_participant_number_is_appended_to_every_link_type(tmp_path, config_dict):
    handler = make_participant_number_handler(tmp_path, config_dict)

    assert handler.get_url(SurveyType.SUBSCRIBE, 1, participant_number=42) == "https://example.com/start-b42"
    assert handler.get_url(SurveyType.DAILY, 0, participant_number=42) == "https://example.com/daily-a42"
    assert handler.get_url(SurveyType.END, 1, 0, participant_number=42) == "https://example.com/end-b42"


def test_participant_number_replaces_placeholder(tmp_path, config_dict):
    handler = make_participant_number_handler(
        tmp_path,
        config_dict,
        daily_url=["https://example.com/s?id={participant}&lang=de", "https://example.com/{participant}/daily"],
    )

    assert handler.get_url(SurveyType.DAILY, 0, participant_number=7) == "https://example.com/s?id=7&lang=de"
    assert handler.get_url(SurveyType.DAILY, 1, participant_number=7) == "https://example.com/7/daily"


def test_participant_number_is_zero_padded(tmp_path, config_dict):
    handler = make_participant_number_handler(tmp_path, config_dict, pad_to_digits=3)

    assert handler.get_url(SurveyType.DAILY, 0, participant_number=7) == "https://example.com/daily-a007"
    assert handler.get_url(SurveyType.DAILY, 0, participant_number=1234) == "https://example.com/daily-a1234"


def test_participant_number_required_when_enabled(tmp_path, config_dict):
    handler = make_participant_number_handler(tmp_path, config_dict)

    with pytest.raises(ValueError):
        handler.get_url(SurveyType.DAILY, 0)


def test_links_unchanged_when_participant_numbers_disabled(config_handler):
    assert config_handler.get_url(SurveyType.DAILY, 0, participant_number=42) == "https://example.com/daily-a"


def test_handwritten_yaml_with_placeholder_loads(tmp_path, config_dict):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        yaml.safe_dump(config_dict()).replace("start-a", "start?id={participant}&src=bot")
        + "useParticipantNumbers: true\n"
        + "participantNumberSettings:\n"
        + "  minNumber: 1\n"
        + "  maxNumber: 50\n",
        encoding="utf-8",
    )

    handler = ConfigHandler(config_file=config_file)

    assert handler.get_url(SurveyType.SUBSCRIBE, 0, participant_number=3) == "https://example.com/start?id=3&src=bot"


@pytest.mark.parametrize("config_name", ["config.yml", "test.yml"])
def test_shipped_config_templates_are_valid(config_name):
    # config.yml is packaged with every precompiled release
    handler = ConfigHandler(config_file=Path(__file__).parent.parent / "config" / config_name)

    assert handler.config.useParticipantNumbers is False
