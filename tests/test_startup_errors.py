import json
import logging
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from telegram.error import InvalidToken, NetworkError, TimedOut

import bot
import bot_utils.db_handler as db_module
from bot_utils.config import Config
from bot_utils.startup_errors import (
    PLACEHOLDER_TOKEN,
    HideBootstrapTracebacks,
    StartupError,
    check_api_token,
    config_file_not_found,
    config_incomplete,
    config_syntax_error,
    invalid_token_error,
    network_error,
)


CONFIG_FILE = Path("config/test.yml")
SECRET_TOKEN = "123456789:AAsecretPartThatMustNeverBeLogged_-"


# -----------------------------------------------------------------------------
# Token check before contacting Telegram
# -----------------------------------------------------------------------------


def test_valid_token_is_returned_without_surrounding_spaces():
    assert check_api_token("  " + SECRET_TOKEN + "\n", CONFIG_FILE) == SECRET_TOKEN


@pytest.mark.parametrize("token", ["", "   ", None, 12345])
def test_missing_token_is_reported(token):
    with pytest.raises(StartupError) as exc_info:
        check_api_token(token, CONFIG_FILE)

    assert "No Telegram bot token is set" in exc_info.value.title
    assert "@BotFather" in exc_info.value.fix


def test_placeholder_token_mentions_saving_and_the_used_file():
    with pytest.raises(StartupError) as exc_info:
        check_api_token(PLACEHOLDER_TOKEN, CONFIG_FILE)

    text = exc_info.value.describe()
    assert "still the placeholder" in text
    assert "not saved" in text
    assert str(CONFIG_FILE) in text


@pytest.mark.parametrize("token", [
    "bot123456789:AAabc",       # copied with 'bot' in front
    "123456789:AA abc",         # space inside
    "123456789",                # only the bot id
    "'123456789:AAabc'",        # extra quotes
    "123456789:AAabc\n456",     # line break
])
def test_malformed_token_is_reported(token):
    with pytest.raises(StartupError) as exc_info:
        check_api_token(token, CONFIG_FILE)

    assert "does not look like a Telegram bot token" in exc_info.value.title


# -----------------------------------------------------------------------------
# Messages
# -----------------------------------------------------------------------------


def test_describe_contains_title_causes_and_fix():
    text = StartupError("Title", ["first cause", "second cause"], "do this").describe()

    assert text.splitlines()[0] == "Title"
    assert "  - first cause" in text
    assert "  - second cause" in text
    assert "How to fix it: do this" in text


def test_rejected_token_message_explains_causes_without_the_token():
    text = invalid_token_error(CONFIG_FILE).describe()

    assert "Telegram rejected the bot token" in text
    assert "not saved" in text
    assert "/revoke" in text
    assert "do not expire" in text
    assert str(CONFIG_FILE) in text


def test_network_error_message():
    text = network_error(TimedOut()).describe()

    assert "could not connect to Telegram" in text
    assert "internet connection" in text


def test_missing_config_file_message():
    error = FileNotFoundError(2, "No such file or directory", "config/missing.yml")

    assert "'config/missing.yml' was not found" in config_file_not_found(error).title


def test_no_config_file_at_all_message():
    error = FileNotFoundError("No config file found. Expected one of: config/config.yml")

    assert config_file_not_found(error).title.startswith("No config file was found")


def test_yaml_error_message_contains_line_and_column():
    try:
        yaml.safe_load("urls:\n  start_url: [\n  daily_url: x\n   end_url: y\n")
    except yaml.YAMLError as err:
        error = err

    title = config_syntax_error(error, CONFIG_FILE).title
    assert "formatting error (line" in title
    assert str(CONFIG_FILE) in title


def test_json_error_message_contains_line_and_column():
    try:
        json.loads('{\n  "api_token": "x",\n  oops\n}')
    except json.JSONDecodeError as err:
        error = err

    assert "(line 3, column 3)" in config_syntax_error(error, CONFIG_FILE).title


def test_missing_setting_is_named(config_dict):
    data = config_dict()
    data.pop("texts")
    data.pop("help")
    with pytest.raises(TypeError) as exc_info:
        Config(**data)

    title = config_incomplete(exc_info.value, CONFIG_FILE).title
    assert "is missing the setting(s): texts, help" in title


def test_unknown_setting_is_named(config_dict):
    with pytest.raises(TypeError) as exc_info:
        Config(**config_dict(useParticipantNumber=True))  # typo: missing 's'

    assert "unknown setting 'useParticipantNumber'" in config_incomplete(exc_info.value, CONFIG_FILE).title


def test_other_type_errors_fall_back_to_a_generic_message():
    error = config_incomplete(TypeError("something else"), CONFIG_FILE)

    assert "contains an invalid setting" in error.title
    assert "something else" in error.describe()


# -----------------------------------------------------------------------------
# Log filter
# -----------------------------------------------------------------------------


def make_record(message, error=None):
    exc_info = (type(error), error, None) if error is not None else None
    return logging.LogRecord("telegram.ext", logging.ERROR, __file__, 1, message, (), exc_info)


@pytest.mark.parametrize("error", [InvalidToken("rejected " + SECRET_TOKEN), NetworkError("offline")])
def test_filter_hides_ptb_bootstrap_traceback(error):
    record = make_record("Network Retry Loop (Bootstrap Initialize Application): Aborting.", error)

    assert HideBootstrapTracebacks().filter(record) is False


@pytest.mark.parametrize("record", [
    make_record("Normal message"),
    make_record("Exception happened while polling for updates.", NetworkError("offline")),
    make_record("Network Retry Loop (Bootstrap Initialize Application)", ValueError("other")),
])
def test_filter_keeps_all_other_records(record):
    assert HideBootstrapTracebacks().filter(record) is True


# -----------------------------------------------------------------------------
# main() with each startup problem
# -----------------------------------------------------------------------------


@pytest.fixture
def run_main(tmp_path, monkeypatch, config_dict):
    monkeypatch.setattr(db_module, "DB_FILE", tmp_path / "bot.db")
    for name in ("config_handler", "schedule_util", "db_handler", "scheduler"):
        monkeypatch.setattr(bot, name, None, raising=False)
    init_application = Mock()
    monkeypatch.setattr(bot, "init_application", init_application)
    monkeypatch.setattr(bot, "init_handlers", Mock())

    def _run(config_text=None, token=SECRET_TOKEN, file_name="config.yml", **overrides):
        config_file = tmp_path / file_name
        if config_text is None:
            config_text = yaml.safe_dump(config_dict(api_token=token, **overrides))
        if config_text is not False:
            config_file.write_text(config_text, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["bot.py", str(config_file)])
        with pytest.raises(SystemExit) as exc_info:
            bot.main()
        return exc_info.value.code, init_application

    return _run


def logged_text(caplog):
    return "\n".join(record.getMessage() for record in caplog.records)


def test_main_reports_rejected_token_readably(run_main, caplog):
    # this is what python-telegram-bot raises when Telegram rejects the token
    bot.init_application.return_value.run_polling.side_effect = InvalidToken(
        f"The token `{SECRET_TOKEN}` was rejected by the server."
    )
    caplog.set_level(logging.INFO)

    code, _ = run_main()

    text = logged_text(caplog)
    assert code == 1
    assert "Telegram rejected the bot token" in text
    assert SECRET_TOKEN not in text
    assert "AAsecretPart" not in text


def test_main_reports_network_problem_readably(run_main, caplog):
    bot.init_application.return_value.run_polling.side_effect = TimedOut()
    caplog.set_level(logging.INFO)

    code, _ = run_main()

    assert code == 1
    assert "could not connect to Telegram" in logged_text(caplog)


def test_main_stops_before_contacting_telegram_when_token_is_placeholder(run_main, caplog):
    code, init_application = run_main(token=PLACEHOLDER_TOKEN)

    assert code == 1
    assert "still the placeholder" in logged_text(caplog)
    init_application.assert_not_called()


def test_main_reports_missing_config_file(run_main, caplog):
    code, init_application = run_main(config_text=False, file_name="missing.yml")

    assert code == 1
    assert "missing.yml' was not found" in logged_text(caplog)
    init_application.assert_not_called()


def test_main_reports_yaml_formatting_error(run_main, caplog):
    code, _ = run_main(config_text="api_token: \"x\"\nurls:\n  start_url:\n    - \"a\"\n   daily_url: b\n")

    assert code == 1
    assert "formatting error (line 5" in logged_text(caplog)


def test_main_reports_missing_setting(run_main, caplog, config_dict):
    data = config_dict(api_token=SECRET_TOKEN)
    data.pop("texts")

    code, _ = run_main(config_text=yaml.safe_dump(data))

    assert code == 1
    assert "is missing the setting(s): texts" in logged_text(caplog)


def test_main_lists_config_validation_errors(run_main, caplog):
    code, _ = run_main(subscription_start_date="2026-05-21 08:00", subscription_deadline="2026-05-20 20:00")

    text = logged_text(caplog)
    assert code == 1
    assert "contains errors" in text
    assert "subscription start date is after subscription deadline" in text


def test_main_strips_spaces_around_a_valid_token(run_main):
    bot.init_application.return_value.run_polling.side_effect = TimedOut()

    run_main(token="  " + SECRET_TOKEN + "  ")

    assert bot.config_handler.config.api_token == SECRET_TOKEN
