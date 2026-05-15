from unittest.mock import Mock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot_utils.bot_enums import SurveyType
from bot_utils.bot_utils import KeyboardBuilder


def test_build_menu_single_column():
    buttons = [
        InlineKeyboardButton(text="A", url="https://example.com/a"),
        InlineKeyboardButton(text="B", url="https://example.com/b"),
    ]

    menu = KeyboardBuilder.build_menu(buttons, n_cols=1)

    assert menu == [
        [buttons[0]],
        [buttons[1]],
    ]


def test_build_menu_two_columns():
    buttons = [
        InlineKeyboardButton(text="A", url="https://example.com/a"),
        InlineKeyboardButton(text="B", url="https://example.com/b"),
        InlineKeyboardButton(text="C", url="https://example.com/c"),
    ]

    menu = KeyboardBuilder.build_menu(buttons, n_cols=2)

    assert menu == [
        [buttons[0], buttons[1]],
        [buttons[2]],
    ]


def test_build_menu_with_header_and_footer():
    header = [InlineKeyboardButton(text="Header", url="https://example.com/header")]
    footer = [InlineKeyboardButton(text="Footer", url="https://example.com/footer")]
    buttons = [
        InlineKeyboardButton(text="A", url="https://example.com/a"),
        InlineKeyboardButton(text="B", url="https://example.com/b"),
    ]

    menu = KeyboardBuilder.build_menu(
        buttons,
        n_cols=2,
        header_buttons=header,
        footer_buttons=footer,
    )

    assert menu == [
        header,
        [buttons[0], buttons[1]],
        footer,
    ]


def test_build_menu_raises_for_invalid_column_count():
    buttons = [
        InlineKeyboardButton(text="A", url="https://example.com/a"),
    ]

    with pytest.raises(ValueError):
        KeyboardBuilder.build_menu(buttons, n_cols=0)


def test_generate_link_markup():
    config_handler = Mock()
    config_handler.get_url.return_value = "https://example.com/survey"

    markup = KeyboardBuilder.generate_link_markup(
        config_handler=config_handler,
        survey_type=SurveyType.DAILY,
        condition=1,
        end_index=-1,
    )

    assert isinstance(markup, InlineKeyboardMarkup)

    button = markup.inline_keyboard[0][0]
    assert button.text == "Start"
    assert button.url == "https://example.com/survey"

    config_handler.get_url.assert_called_once_with(
        SurveyType.DAILY,
        1,
        -1,
    )