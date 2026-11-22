import json
from pathlib import Path
import yaml

import pytest

from bot_utils.bot_enums import SurveyType
from bot_utils.config_handler import ConfigHandler
from bot_utils.config_validator import ConfigValidationException

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


def make_participant_number_handler(tmp_path, config_dict, **overrides):
    data = config_dict(
        useParticipantNumbers=True,
        urls={
            "start_url": ["https://example.com/start?id={participant}&lang=de"],
            "daily_url": ["https://example.com/daily/{participant}"],
            "end_url": ["https://example.com/end/{participant}/done"],
            "end_url_distribution": "NONE",
        },
        **overrides,
    )
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    return ConfigHandler(config_file=config_file)


def test_participant_number_replaces_placeholder_in_every_link_type(tmp_path, config_dict):
    handler = make_participant_number_handler(tmp_path, config_dict)

    assert handler.get_url(SurveyType.SUBSCRIBE, 0, participant_number="04711") == \
        "https://example.com/start?id=04711&lang=de"
    assert handler.get_url(SurveyType.DAILY, 0, participant_number="04711") == "https://example.com/daily/04711"
    assert handler.get_url(SurveyType.END, 0, 0, participant_number="04711") == \
        "https://example.com/end/04711/done"


def test_participant_number_required_when_enabled(tmp_path, config_dict):
    handler = make_participant_number_handler(tmp_path, config_dict)

    with pytest.raises(ValueError):
        handler.get_url(SurveyType.DAILY, 0)


def test_links_unchanged_when_participant_numbers_disabled(config_handler):
    assert config_handler.get_url(SurveyType.DAILY, 0, participant_number="04711") == "https://example.com/daily-a"


def test_url_without_placeholder_is_rejected_at_startup(tmp_path, config_dict):
    data = config_dict(useParticipantNumbers=True)  # default test urls have no placeholder
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ConfigValidationException) as exc_info:
        ConfigHandler(config_file=config_file)

    assert "Url 'https://example.com/start-a' must contain '{participant}'" in exc_info.value.message_list[0]


def test_handwritten_yaml_with_plain_end_url_loads(tmp_path, config_dict):
    base = config_dict()
    base.pop("urls")
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        yaml.safe_dump(base)
        + "useParticipantNumbers: true\n"
        + "participantNumberDigits: 4\n"
        + "urls:\n"
        + "  start_url:\n"
        + "    - \"https://example.com/start?id={participant}&src=bot\"\n"
        + "  daily_url:\n"
        + "    - \"https://example.com/daily/{participant}\"\n"
        + "  end_url:\n"
        + "    - \"https://example.com/end?id={participant}\"\n"
        + "  end_url_distribution: \"NONE\"\n",
        encoding="utf-8",
    )

    handler = ConfigHandler(config_file=config_file)

    assert handler.config.participantNumberDigits == 4
    assert handler.get_url(SurveyType.END, 0, 0, participant_number="0042") == "https://example.com/end?id=0042"


@pytest.mark.parametrize("config_name, uses_participant_numbers", [("config.yml", True), ("test.yml", False)])
def test_shipped_config_templates_are_valid(config_name, uses_participant_numbers):
    # config.yml is packaged with every precompiled release
    handler = ConfigHandler(config_file=Path(__file__).parent.parent / "config" / config_name)

    assert handler.config.useParticipantNumbers is uses_participant_numbers
