from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import ConversationHandler

import bot
from bot_utils.bot_enums import SurveyType


@pytest.fixture
def mock_message():
    return SimpleNamespace(message_id=999)


@pytest.fixture
def context(mock_message):
    context = SimpleNamespace()
    context.bot = SimpleNamespace()
    context.bot.send_message = AsyncMock(return_value=mock_message)
    context.bot.delete_message = AsyncMock()
    context.user_data = {}
    return context


@pytest.fixture
def update():
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        message=SimpleNamespace(text="06:30", message_id=555),
        callback_query=None,
    )


@pytest.fixture
def mock_config_handler():
    config = SimpleNamespace()

    config.subscription_start_date = datetime.now() - timedelta(days=1)
    config.subscription_deadline = datetime.now() + timedelta(days=1)

    config.useTimeZoneCalculation = False
    config.useTimeCalculation = False
    config.participantsEnterCondition = False
    config.uniqueConditions = False
    config.surveyCommandEnabled = True
    config.endSurveyReminderEnabled = False

    config.texts = SimpleNamespace(
        welcome="Welcome",
        subscribe="Subscribed",
        subscribe_early="Too early",
        subscribe_late="Too late",
        subscribe_already="Already subscribed",
        subscribe_max_participants="Full",
        subscribe_timezone="Timezone?",
        subscribe_wakeup_time="Wakeup?",
        subscribe_condition="Condition?",
        unsubscribe="Unsubscribed",
        survey_reply="Survey reply",
        daily_reminder="Daily reminder",
        end_reminder="End reminder",
        endSurveyReminder="End survey reminder",
    )

    config.help = SimpleNamespace(
        helpEnabled=True,
        help_text="Help",
        surveyCommandHelp=" Survey help",
    )

    config.linkDeletionSettings = SimpleNamespace(
        start_DeleteLinkTimer=False,
        start_DeleteDelayMinutes=1,
        daily_DeleteLinkTimer=False,
        daily_DeleteDelayMinutes=1,
        end_DeleteLinkAtNewLink=False,
        end_DeleteLinkTimer=False,
        end_DeleteDelayMinutes=1,
    )

    handler = Mock()
    handler.config = config
    handler.get_condition.return_value = 1
    handler.get_condition_count.return_value = 3
    handler.get_message.side_effect = lambda survey_type: {
        SurveyType.DAILY: "Daily reminder",
        SurveyType.END: "End reminder",
    }[survey_type]
    return handler


@pytest.fixture
def mock_db_handler():
    db = Mock()
    db.is_already_subscribed.return_value = False
    db.get_used_condition.return_value = 1
    db.get_condition.return_value = 1
    db.get_condition_and_end_index.return_value = (1, 0)
    db.query_and_delete_message_ids.return_value = []
    return db


@pytest.fixture
def mock_schedule_util():
    scheduler = Mock()
    scheduler.assign_condition.return_value = True
    return scheduler


@pytest.fixture(autouse=True)
def patch_bot_globals(monkeypatch, mock_config_handler, mock_db_handler, mock_schedule_util):
    monkeypatch.setattr(bot, "config_handler", mock_config_handler, raising=False)
    monkeypatch.setattr(bot, "db_handler", mock_db_handler, raising=False)
    monkeypatch.setattr(bot, "schedule_util", mock_schedule_util, raising=False)


@pytest.mark.asyncio
async def test_start_sends_welcome_message(update, context):
    await bot.start(update, context)

    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="Welcome",
    )


@pytest.mark.asyncio
async def test_unsubscribe_removes_subscriber_and_sends_message(update, context, mock_db_handler):
    await bot.unsubscribe(update, context)

    mock_db_handler.remove_subscriber.assert_called_once_with(123)
    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="Unsubscribed",
    )


@pytest.mark.asyncio
async def test_send_help_sends_help_text(update, context):
    await bot.send_help(update, context)

    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="Help Survey help",
    )


@pytest.mark.asyncio
async def test_send_survey_sends_daily_link(update, context, mock_db_handler, monkeypatch):
    markup = Mock()
    monkeypatch.setattr(
        bot.KeyboardBuilder,
        "generate_link_markup",
        Mock(return_value=markup),
    )

    await bot.send_survey(update, context)

    mock_db_handler.get_condition.assert_called_once_with(123)
    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="Survey reply",
        reply_markup=markup,
    )
    mock_db_handler.insert_message_id.assert_called_once_with(
        123,
        999,
        SurveyType.DAILY,
    )


@pytest.mark.asyncio
async def test_subscribe_direct_success(update, context, mock_schedule_util, monkeypatch):
    markup = Mock()
    monkeypatch.setattr(
        bot.KeyboardBuilder,
        "generate_link_markup",
        Mock(return_value=markup),
    )

    result = await bot.subscribe(update, context)

    assert result == ConversationHandler.END
    mock_schedule_util.add_new_subscriber.assert_called_once()
    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="Subscribed",
        reply_markup=markup,
    )


@pytest.mark.asyncio
async def test_subscribe_rejects_if_already_subscribed(update, context, mock_db_handler, mock_schedule_util):
    mock_db_handler.is_already_subscribed.return_value = True

    result = await bot.subscribe(update, context)

    assert result == ConversationHandler.END
    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="Already subscribed",
    )
    mock_schedule_util.schedule_delete_message.assert_called_once()
    mock_schedule_util.add_new_subscriber.assert_not_called()


@pytest.mark.asyncio
async def test_subscribe_asks_for_wakeup_time_when_time_calculation_enabled(
    update,
    context,
    mock_config_handler,
    mock_db_handler,
):
    mock_config_handler.config.useTimeCalculation = True

    result = await bot.subscribe(update, context)

    assert result == bot.TIME_STATE
    assert context.user_data["subscribe_state"] == bot.TIME_STATE
    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="Wakeup? (HH:MM)",
    )
    mock_db_handler.insert_message_id.assert_called_once_with(
        123,
        999,
        SurveyType.SUBSCRIBE,
    )


@pytest.mark.asyncio
async def test_subscribe_wakeup_time_finishes_subscription(
    update,
    context,
    mock_schedule_util,
    monkeypatch,
):
    markup = Mock()
    monkeypatch.setattr(
        bot.KeyboardBuilder,
        "generate_link_markup",
        Mock(return_value=markup),
    )

    result = await bot.subscribe_wakeup_time(update, context)

    assert result == ConversationHandler.END
    mock_schedule_util.add_new_subscriber.assert_called_once()
    args = mock_schedule_util.add_new_subscriber.call_args.args

    assert args[0] == 123
    assert args[1] == 1
    assert args[3].hour == 6
    assert args[3].minute == 30


@pytest.mark.asyncio
async def test_subscribe_condition_updates_condition_when_time_calculation_enabled(
    update,
    context,
    mock_config_handler,
    mock_db_handler,
    monkeypatch,
):
    update.message.text = "2"
    mock_config_handler.config.useTimeCalculation = True

    markup = Mock()
    monkeypatch.setattr(
        bot.KeyboardBuilder,
        "generate_link_markup",
        Mock(return_value=markup),
    )

    result = await bot.subscribe_condition(update, context)

    assert result == ConversationHandler.END
    mock_db_handler.update_subscriber_condition.assert_called_once_with(123, 2)


@pytest.mark.asyncio
async def test_callback_yes_only_deletes_reminder(update, context):
    query = SimpleNamespace()
    query.answer = AsyncMock()
    query.data = "ER_YES+2026-05-15-18:00"
    query.message = SimpleNamespace(message_id=777)

    update.callback_query = query

    await bot.handle_end_survey_reminder_callback(update, context)

    query.answer.assert_called_once()
    context.bot.delete_message.assert_called_once_with(
        chat_id=123,
        message_id=777,
    )
    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_callback_no_sends_end_link(update, context, mock_db_handler, monkeypatch):
    query = SimpleNamespace()
    query.answer = AsyncMock()
    query.data = "ER_NO+2026-05-15-18:00"
    query.message = SimpleNamespace(message_id=777)

    update.callback_query = query

    markup = Mock()
    monkeypatch.setattr(
        bot.KeyboardBuilder,
        "generate_link_markup",
        Mock(return_value=markup),
    )

    await bot.handle_end_survey_reminder_callback(update, context)

    mock_db_handler.get_condition_and_end_index.assert_called_once_with(
        123,
        "2026-05-15-18:00",
    )
    context.bot.delete_message.assert_called_once_with(
        chat_id=123,
        message_id=777,
    )
    context.bot.send_message.assert_called_once_with(
        chat_id=123,
        text="End survey reminder",
        reply_markup=markup,
    )