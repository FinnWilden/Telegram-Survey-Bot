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
along with Telegram Survey Bot. If not, see <http://www.gnu.org/licenses/>.
"""
from __future__ import annotations

import asyncio, logging, sys
from asyncio import AbstractEventLoop
from datetime import datetime, time
from pathlib import Path
from collections.abc import Awaitable, Callable

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest, Forbidden, InvalidToken, NetworkError, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    BaseHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot_utils.bot_enums import SurveyType
from bot_utils.bot_utils import KeyboardBuilder
from bot_utils.config_handler import ConfigHandler
from bot_utils.config_validator import ConfigValidationException
from bot_utils.db_handler import DbHandler
from bot_utils.emergency_start import EmergencyStart
from bot_utils.schedule_util import ScheduleUtil
from bot_utils.time_util import TimeUtil
from bot_utils.logging_strings import *


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s-%(name)s-%(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("log/log_{}.log".format(datetime.now().strftime("%Y%m%d-%H%M%S"))),
        logging.StreamHandler(),
    ],
)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

TIMEZONE_STATE = 0
TIME_STATE = 1
CONDITION_STATE = 2
ER_YES = "ER_YES"
ER_NO = "ER_NO"

config_handler: ConfigHandler
schedule_util: ScheduleUtil
scheduler: BackgroundScheduler
db_handler: DbHandler
application: Application
application_loop: AbstractEventLoop | None = None


# -----------------------------------------------------------------------------
# Application setup
# -----------------------------------------------------------------------------


def init_application() -> Application:
    """
    Initializes the Telegram Application.

    In python-telegram-bot v20+, Application replaces the old Updater/Dispatcher
    architecture. The bot instance, request handling and polling lifecycle are
    managed by the Application.
    """
    return (
        ApplicationBuilder()
        .token(config_handler.config.api_token)
        .connection_pool_size(200)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )


def init_handlers(app: Application) -> None:
    """
    Initializes all handlers for the bot.
    """
    subscribe_handler = CommandHandler("subscribe", subscribe)

    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("start", start))

    if config_handler.config.help.helpEnabled:
        app.add_handler(CommandHandler("help", send_help))

    if config_handler.config.surveyCommandEnabled:
        app.add_handler(CommandHandler("survey", send_survey))

    if config_handler.config.endSurveyReminderEnabled:
        app.add_handler(CallbackQueryHandler(handle_end_survey_reminder_callback))

    if (
        config_handler.config.useTimeCalculation
        or config_handler.config.participantsEnterCondition
        or config_handler.config.useTimeZoneCalculation
    ):
        states: dict[int, list[BaseHandler]] = {}

        if config_handler.config.useTimeZoneCalculation:
            regex_str = r"^\d{4}\.(0?[1-9]|1[012])\.(0?[1-9]|[12][0-9]|3[01])\-(0\d|1\d|2\d|\d):[0-5]\d$"
            states[TIMEZONE_STATE] = [MessageHandler(filters.Regex(regex_str), subscribe_timezone)]

        if config_handler.config.participantsEnterCondition:
            regex_str = "^[0-%d]$" % (config_handler.get_condition_count() - 1)
            states[CONDITION_STATE] = [MessageHandler(filters.Regex(regex_str), subscribe_condition)]

        if config_handler.config.useTimeCalculation:
            regex_str = r"^(0[0-9]|1[0-9]|2[0-3]|[0-9]):[0-5][0-9]$"
            states[TIME_STATE] = [MessageHandler(filters.Regex(regex_str), subscribe_wakeup_time)]

        app.add_handler(
            ConversationHandler(
                entry_points=[subscribe_handler],
                states=states,
                fallbacks=[MessageHandler(filters.ALL, subscribe_wakeup_time_fallback)],
            )
        )
    else:
        app.add_handler(subscribe_handler)

    app.add_error_handler(error)


async def post_init(app: Application) -> None:
    """
    Called by PTB after initialization and before polling starts.

    This is the right place to capture the running asyncio loop and start
    APScheduler. APScheduler runs synchronous jobs in a background thread, while
    Telegram API calls are async; therefore scheduled jobs submit coroutines to
    this event loop via asyncio.run_coroutine_threadsafe().
    """
    global application, application_loop

    application = app
    application_loop = asyncio.get_running_loop()

    EmergencyStart(schedule_util, db_handler, send_notification_broadcast)
    schedule_notifications()

    logging.info("Start scheduler...")
    scheduler.start()


async def post_shutdown(_: Application) -> None:
    """
    Called by PTB during shutdown.
    """
    if scheduler.running:
        logging.info("Shutdown scheduler...")
        scheduler.shutdown(wait=True)


# -----------------------------------------------------------------------------
# Helpers for APScheduler -> asyncio bridge
# -----------------------------------------------------------------------------


def submit_async(coro: Awaitable[None]) -> None:
    """
    Submit an async Telegram task from a synchronous APScheduler job.
    """
    if application_loop is None:
        logging.error("Cannot submit async task: application loop is not available")
        return

    future = asyncio.run_coroutine_threadsafe(coro, application_loop)

    def log_exception(done_future) -> None:
        try:
            done_future.result()
        except Exception as err:
            logging.exception("Scheduled async task failed: %s", err)

    future.add_done_callback(log_exception)


# -----------------------------------------------------------------------------
# Scheduling
# -----------------------------------------------------------------------------


def schedule_notifications() -> None:
    """
    Schedules all time triggers with APScheduler.
    """
    if config_handler.config.linkDeletionSettings.start_DeleteLinkAtSubscriptionDeadline:
        schedule_util.schedule_delete_messages(
            delete_messages,
            config_handler.config.subscription_deadline,
            db_handler.query_and_delete_message_ids_by_type,
            SurveyType.SUBSCRIBE,
        )


def send_notification_broadcast(survey_type: SurveyType, job_id: str, date_str: str) -> None:
    """
    Synchronous wrapper used by APScheduler.
    """
    submit_async(send_notification_broadcast_async(survey_type, job_id, date_str))


def send_end_survey_reminder(chat_id_list: list[int], date_str: str) -> None:
    """
    Synchronous wrapper used by APScheduler.
    """
    submit_async(send_end_survey_reminder_async(chat_id_list, date_str))


def delete_messages(query_function: Callable, *func_args) -> None:
    """
    Synchronous wrapper used by APScheduler.
    """
    submit_async(delete_messages_async(query_function, *func_args))


def delete_message(chat_id: int, message_id: int) -> None:
    """
    Synchronous wrapper used by APScheduler.
    """
    submit_async(delete_message_async(chat_id, message_id))


# -----------------------------------------------------------------------------
# Telegram handlers
# -----------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /start.
    """
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text=config_handler.config.texts.welcome)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles /subscribe.
    """
    chat_id = update.effective_chat.id
    curr_date = datetime.now()

    if curr_date < config_handler.config.subscription_start_date:
        await subscribe_rejected(
            context,
            chat_id,
            SUBSCRIPTION_EARLY,
            config_handler.config.texts.subscribe_early,
        )
        return ConversationHandler.END

    if curr_date > config_handler.config.subscription_deadline:
        await subscribe_rejected(
            context,
            chat_id,
            SUBSCRIPTION_LATE,
            config_handler.config.texts.subscribe_late,
        )
        return ConversationHandler.END

    if db_handler.is_already_subscribed(chat_id):
        await subscribe_rejected(
            context,
            chat_id,
            SUBSCRIPTION_ALREADY_SUBSCRIBED,
            config_handler.config.texts.subscribe_already,
        )
        return ConversationHandler.END

    if config_handler.config.uniqueConditions and not schedule_util.assign_condition(chat_id):
        await subscribe_rejected(
            context,
            chat_id,
            SUBSCRIPTION_CONDITIONS_FULL,
            config_handler.config.texts.subscribe_max_participants,
        )
        return ConversationHandler.END

    logging.info(SUBSCRIPTION_HANDLE.format(chat_id))

    if (
        not config_handler.config.useTimeZoneCalculation
        and not config_handler.config.useTimeCalculation
        and not config_handler.config.participantsEnterCondition
    ):
        condition = db_handler.get_used_condition(chat_id) if config_handler.config.uniqueConditions else config_handler.get_condition()
        schedule_util.add_new_subscriber(chat_id, condition, send_notification_broadcast)
        await send_subscribe_message(context, chat_id, condition)
        return ConversationHandler.END

    if config_handler.config.useTimeZoneCalculation:
        context.user_data["subscribe_state"] = TIMEZONE_STATE
        await subscribe_ask(
            context,
            chat_id,
            SUBSCRIPTION_TIMEZONE,
            config_handler.config.texts.subscribe_timezone + " (YYYY.MM.DD-HH:MM)",
        )
        return TIMEZONE_STATE

    if config_handler.config.useTimeCalculation:
        context.user_data["subscribe_state"] = TIME_STATE
        await subscribe_ask(
            context,
            chat_id,
            SUBSCRIPTION_TIME_CALC,
            config_handler.config.texts.subscribe_wakeup_time + " (HH:MM)",
        )
        return TIME_STATE

    context.user_data["subscribe_state"] = CONDITION_STATE
    await subscribe_ask(
        context,
        chat_id,
        SUBSCRIPTION_CONDITION,
        config_handler.config.texts.subscribe_condition + " (0-%d)" % (config_handler.get_condition_count() - 1),
    )
    return CONDITION_STATE


async def subscribe_rejected(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    log_msg: str,
    usr_msg: str,
) -> None:
    """
    Tells the user that subscription was rejected.
    """
    logging.info(SUBSCRIPTION_REJECTED.format(chat_id, log_msg))
    msg = await context.bot.send_message(chat_id=chat_id, text=usr_msg)
    schedule_util.schedule_delete_message(delete_message, 1, chat_id, msg.message_id)


async def subscribe_ask(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    log_msg: str,
    usr_msg: str,
) -> None:
    """
    Sends the next subscription question.
    """
    logging.info(SUBSCRIPTION_ASK.format(chat_id, log_msg))
    msg = await context.bot.send_message(chat_id=chat_id, text=usr_msg)
    db_handler.insert_message_id(chat_id, msg.message_id, SurveyType.SUBSCRIBE)


async def error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Logs errors caused by updates.
    """
    logging.error("Update %s caused error %s", update, context.error)


async def subscribe_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the user's current local time and calculates the time offset.
    """
    chat_id = update.effective_chat.id
    offset = TimeUtil.get_time_offset(datetime.strptime(update.message.text, "%Y.%m.%d-%H:%M"))
    logging.info(SUBSCRIPTION_TIMEZONE_DELTA.format(chat_id, offset))
    db_handler.insert_time_offset(chat_id, offset)

    if not config_handler.config.participantsEnterCondition and not config_handler.config.useTimeCalculation:
        condition = db_handler.get_used_condition(chat_id) if config_handler.config.uniqueConditions else config_handler.get_condition()
        schedule_util.add_new_subscriber(chat_id, condition, send_notification_broadcast)
        await send_subscribe_message(context, chat_id, condition)
        context.user_data.pop("subscribe_state", None)
        return ConversationHandler.END

    if config_handler.config.useTimeCalculation:
        context.user_data["subscribe_state"] = TIME_STATE
        await subscribe_ask(
            context,
            chat_id,
            SUBSCRIPTION_TIME_CALC,
            config_handler.config.texts.subscribe_wakeup_time + " (HH:MM)",
        )
        return TIME_STATE

    context.user_data["subscribe_state"] = CONDITION_STATE
    await subscribe_ask(
        context,
        chat_id,
        SUBSCRIPTION_CONDITION,
        config_handler.config.texts.subscribe_condition + " (0-%d)" % (config_handler.get_condition_count() - 1),
    )
    return CONDITION_STATE


async def subscribe_wakeup_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the user's wakeup time.
    """
    chat_id = update.effective_chat.id

    if not config_handler.config.participantsEnterCondition:
        await delete_messages_async(db_handler.query_and_delete_message_ids, [chat_id], SurveyType.SUBSCRIBE)

    wakeup_time: time = TimeUtil.get_time_from_str(update.message.text)
    logging.info(SUBSCRIPTION_WAKEUP_TIME.format(chat_id, wakeup_time))

    condition = db_handler.get_used_condition(chat_id) if config_handler.config.uniqueConditions else config_handler.get_condition()
    schedule_util.add_new_subscriber(chat_id, condition, send_notification_broadcast, wakeup_time)

    if config_handler.config.participantsEnterCondition:
        context.user_data["subscribe_state"] = CONDITION_STATE
        await subscribe_ask(
            context,
            chat_id,
            SUBSCRIPTION_CONDITION,
            config_handler.config.texts.subscribe_condition + " (0-%d)" % (config_handler.get_condition_count() - 1),
        )
        return CONDITION_STATE

    await send_subscribe_message(context, chat_id, condition)
    context.user_data.pop("subscribe_state", None)
    return ConversationHandler.END


async def subscribe_condition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the condition number entered by the user.
    """
    chat_id = update.effective_chat.id

    await delete_messages_async(db_handler.query_and_delete_message_ids, [chat_id], SurveyType.SUBSCRIBE)

    condition = int(update.message.text)
    logging.info(SUBSCRIPTION_GOT_CONDITION.format(chat_id, condition))

    if config_handler.config.useTimeCalculation:
        db_handler.update_subscriber_condition(chat_id, condition)
    else:
        schedule_util.add_new_subscriber(chat_id, condition, send_notification_broadcast)

    await send_subscribe_message(context, chat_id, condition)
    context.user_data.pop("subscribe_state", None)
    return ConversationHandler.END


async def send_subscribe_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, condition: int) -> None:
    """
    Sends the start survey link to a new subscriber.
    """
    logging.info(SUBSCRIPTION_FINISHED.format(chat_id))
    markup = KeyboardBuilder.generate_link_markup(config_handler, SurveyType.SUBSCRIBE, condition)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=config_handler.config.texts.subscribe,
        reply_markup=markup,
    )

    if config_handler.config.linkDeletionSettings.start_DeleteLinkTimer:
        schedule_util.schedule_delete_message(
            delete_message,
            config_handler.config.linkDeletionSettings.start_DeleteDelayMinutes,
            chat_id,
            msg.message_id,
        )


async def subscribe_wakeup_time_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Fallback handler for invalid subscription conversation input.
    """
    chat_id = update.effective_chat.id
    db_handler.insert_message_id(chat_id, update.message.message_id, SurveyType.SUBSCRIBE)

    state_code = context.user_data.get("subscribe_state")

    if state_code == TIMEZONE_STATE:
        await subscribe_ask(
            context,
            chat_id,
            SUBSCRIPTION_TIMEZONE,
            config_handler.config.texts.subscribe_timezone + " (YYYY.MM.DD-HH:MM)",
        )
        return TIMEZONE_STATE

    if state_code == TIME_STATE:
        await subscribe_ask(
            context,
            chat_id,
            SUBSCRIPTION_TIME_CALC,
            config_handler.config.texts.subscribe_wakeup_time + " (HH:MM)",
        )
        return TIME_STATE

    await subscribe_ask(
        context,
        chat_id,
        SUBSCRIPTION_CONDITION,
        config_handler.config.texts.subscribe_condition + " (0-%d)" % (config_handler.get_condition_count() - 1),
    )
    return CONDITION_STATE


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /unsubscribe.
    """
    chat_id = update.effective_chat.id
    logging.info(UNSUBSCRIBE.format(chat_id))
    db_handler.remove_subscriber(chat_id)
    await context.bot.send_message(chat_id=chat_id, text=config_handler.config.texts.unsubscribe)


async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /help.
    """
    chat_id = update.effective_chat.id
    help_text = config_handler.config.help.help_text

    if config_handler.config.surveyCommandEnabled:
        help_text += config_handler.config.help.surveyCommandHelp

    await context.bot.send_message(chat_id=chat_id, text=help_text)


async def send_survey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /survey.
    """
    chat_id = update.effective_chat.id
    condition = db_handler.get_condition(chat_id)
    markup: InlineKeyboardMarkup = KeyboardBuilder.generate_link_markup(config_handler, SurveyType.DAILY, condition)

    logging.info(SEND_SURVEY.format(SurveyType.DAILY.name, chat_id))

    msg: Message = await context.bot.send_message(
        chat_id=chat_id,
        text=config_handler.config.texts.survey_reply,
        reply_markup=markup,
    )
    db_handler.insert_message_id(chat_id, msg.message_id, SurveyType.DAILY)

    if config_handler.config.linkDeletionSettings.daily_DeleteLinkTimer:
        schedule_util.schedule_delete_message(
            delete_message,
            config_handler.config.linkDeletionSettings.daily_DeleteDelayMinutes,
            chat_id,
            msg.message_id,
        )


async def handle_end_survey_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the end-survey-reminder button callback.
    """
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    callback_code = query.data.split("+")
    message_id = query.message.message_id

    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    if callback_code[0] == ER_NO:
        condition, end_index = db_handler.get_condition_and_end_index(chat_id, callback_code[1])
        markup = KeyboardBuilder.generate_link_markup(config_handler, SurveyType.END, condition, end_index)

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=config_handler.config.texts.endSurveyReminder,
            reply_markup=markup,
        )

        if config_handler.config.linkDeletionSettings.end_DeleteLinkAtNewLink:
            db_handler.insert_message_id(chat_id, msg.message_id, SurveyType.END)

        if config_handler.config.linkDeletionSettings.end_DeleteLinkTimer:
            schedule_util.schedule_delete_message(
                delete_messages,
                config_handler.config.linkDeletionSettings.end_DeleteDelayMinutes,
                db_handler.query_and_delete_message_ids,
                [chat_id],
                SurveyType.END,
            )


# -----------------------------------------------------------------------------
# Async implementations for scheduled/background actions
# -----------------------------------------------------------------------------


async def send_notification_broadcast_async(survey_type: SurveyType, job_id: str, date_str: str) -> None:
    """
    Sends a survey link and reminder message to all subscribers scheduled for a date.
    """
    remove_job_from_scheduler(job_id)

    subscriber_information: list[tuple[int, int, int]] = db_handler.query_subscribers_by_date_type(
        date_str,
        survey_type.name,
    )

    if (
        config_handler.config.linkDeletionSettings.daily_DeleteLinkAtNewLink
        or config_handler.config.linkDeletionSettings.end_DeleteLinkAtNewLink
    ):
        await delete_messages_async(
            db_handler.query_and_delete_message_ids,
            [x[0] for x in subscriber_information],
            survey_type,
        )

    msg_text: str = config_handler.get_message(survey_type)

    for chat_id, condition, end_index in subscriber_information:
        markup: InlineKeyboardMarkup = KeyboardBuilder.generate_link_markup(
            config_handler,
            survey_type,
            condition,
            end_index,
        )
        try:
            logging.info(SEND_SURVEY.format(survey_type.name, chat_id))
            msg = await application.bot.send_message(chat_id=chat_id, text=msg_text, reply_markup=markup)
            db_handler.insert_message_id(chat_id, msg.message_id, survey_type)
        except Forbidden as err:
            logging.error("Can't send survey to %d because the bot is blocked or forbidden: %s", chat_id, err)
        except NetworkError as err:
            logging.error("Network error while sending survey to %d: %s", chat_id, err)
        except TelegramError as err:
            logging.error("Telegram error while sending survey to %d: %s", chat_id, err)

    chat_id_list = [chat_id for chat_id, _, _ in subscriber_information]

    if survey_type == SurveyType.END and config_handler.config.endSurveyReminderEnabled:
        schedule_util.schedule_end_survey_reminder(send_end_survey_reminder, subscriber_information)

    if survey_type == SurveyType.DAILY and config_handler.config.linkDeletionSettings.daily_DeleteLinkTimer:
        schedule_util.schedule_delete_message(
            delete_messages,
            config_handler.config.linkDeletionSettings.daily_DeleteDelayMinutes,
            db_handler.query_and_delete_message_ids,
            chat_id_list,
            survey_type,
        )
    elif survey_type == SurveyType.END and config_handler.config.linkDeletionSettings.end_DeleteLinkTimer:
        schedule_util.schedule_delete_message(
            delete_messages,
            config_handler.config.linkDeletionSettings.end_DeleteDelayMinutes,
            db_handler.query_and_delete_message_ids,
            chat_id_list,
            survey_type,
        )


def remove_job_from_scheduler(job_id: str) -> None:
    """
    Removes a job from APScheduler if it still exists.
    """
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        logging.info("Job with id " + job_id + " not rescheduled")


async def send_end_survey_reminder_async(chat_id_list: list[int], date_str: str) -> None:
    """
    Sends the end-survey-reminder to users.
    """
    callback_yes = ER_YES + "+" + date_str
    callback_no = ER_NO + "+" + date_str

    button_list = [
        InlineKeyboardButton(text=config_handler.config.texts.endSurveyReminderYes, callback_data=callback_yes),
        InlineKeyboardButton(text=config_handler.config.texts.endSurveyReminderNo, callback_data=callback_no),
    ]
    markup: InlineKeyboardMarkup = InlineKeyboardMarkup(KeyboardBuilder.build_menu(button_list, n_cols=1))

    for chat_id in chat_id_list:
        try:
            logging.info(SEND_SURVEY.format("END REMINDER", chat_id))
            await application.bot.send_message(
                chat_id=chat_id,
                text=config_handler.config.texts.endSurveyReminder,
                reply_markup=markup,
            )
        except Forbidden as err:
            logging.error("Can't send end reminder to %d because the bot is blocked or forbidden: %s", chat_id, err)
        except TelegramError as err:
            logging.error("Telegram error while sending end reminder to %d: %s", chat_id, err)


async def delete_messages_async(query_function: Callable, *func_args) -> None:
    """
    Deletes multiple link messages.
    """
    id_list: list[tuple] = query_function(*func_args)

    for chat_id, message_id in id_list:
        await delete_message_async(chat_id, message_id)


async def delete_message_async(chat_id: int, message_id: int) -> None:
    """
    Deletes one Telegram message.
    """
    try:
        await application.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest as err:
        logging.error("Can't delete message %d in chat %d because: %s", message_id, chat_id, err)
    except TelegramError as err:
        logging.error("Telegram error while deleting message %d in chat %d: %s", message_id, chat_id, err)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    """
    Main method. Initializes all required objects and starts the bot.
    """
    global config_handler, schedule_util, db_handler, scheduler

    logging.info("Load Config...")
    try:
        config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        config_handler = ConfigHandler(config_file=config_path)

    except ConfigValidationException as err:
        for message in err.message_list:
            logging.error(message)
        raise SystemExit(-1)

    except (ValueError, TypeError, KeyError) as err:
        logging.error("%s: %s", type(err).__name__, err)
        raise SystemExit(-1)

    logging.info("Init...")

    executors = {
        "default": ThreadPoolExecutor(5),
    }
    scheduler = BackgroundScheduler(executors=executors)

    db_handler = DbHandler()
    schedule_util = ScheduleUtil(scheduler, config_handler.config, db_handler)

    try:
        app = init_application()
    except InvalidToken as err:
        logging.error(err)
        logging.info("Check your API token in the config file")
        raise SystemExit(-1)

    init_handlers(app)

    logging.info("Start polling...")
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logging.info("Shutdown requested by user...")


if __name__ == "__main__":
    main()
