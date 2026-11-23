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

import asyncio, json, logging, os, shutil, sqlite3, sys
from asyncio import AbstractEventLoop
from datetime import datetime, time, timedelta
from pathlib import Path
from collections.abc import Awaitable, Callable

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

import yaml

from rich.console import Console
from rich.highlighter import NullHighlighter
from rich.logging import RichHandler
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
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
from bot_utils.console_dashboard import ConsoleDashboard
from bot_utils.db_handler import DbHandler, TrackedMessage
from bot_utils.emergency_start import EmergencyStart
from bot_utils.overview_export import EXPORT_FOLDER, OverviewExporter
from bot_utils.schedule_util import ScheduleUtil
from bot_utils.startup_errors import (
    HideBootstrapTracebacks,
    StartupError,
    check_api_token,
    config_file_not_found,
    config_incomplete,
    config_syntax_error,
    invalid_token_error,
    network_error,
    report,
)
from bot_utils.time_util import TimeUtil
from bot_utils.logging_strings import *


console = Console()
# RichHandler already renders time and level, so the console only needs the message.
# NullHighlighter: Rich would otherwise colour every number and date part inside the
# messages (e.g. job ids like 2026-11-22-20:17DAILY) in a different colour.
console_handler = RichHandler(console=console, show_path=False, highlighter=NullHighlighter())
console_handler.setFormatter(logging.Formatter("%(message)s"))
# startup login errors are reported readably by main(), without PTB's traceback and token
console_handler.addFilter(HideBootstrapTracebacks())
logging.basicConfig(level=logging.INFO, handlers=[console_handler])

LOG_FOLDER = Path("log")
LOG_FORMAT = "%(asctime)s-%(name)s-%(levelname)s: %(message)s"
file_handler: logging.FileHandler | None = None


def start_file_logging() -> None:
    """
    Writes the log of this run to log/log_<start time>.log as well.

    Called when the bot starts, not when bot.py is imported, so importing it (e.g. in the
    tests) creates no log files.
    """
    global file_handler
    if file_handler is not None:
        return
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        LOG_FOLDER / "log_{}.log".format(datetime.now().strftime("%Y%m%d-%H%M%S")),
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler.addFilter(HideBootstrapTracebacks())
    logging.getLogger().addHandler(file_handler)

DEBUG_OPTION = "--debug"


def configure_log_levels(debug: bool) -> None:
    """
    Normal mode shows what happens in the study (subscriptions, sent surveys, errors).
    Debug mode (start option --debug) adds the bot's internal steps and the scheduler's
    job runs.

    Telegram and HTTP libraries stay quiet in both modes: their debug output can contain
    the bot token.
    """
    logging.getLogger().setLevel(logging.DEBUG if debug else logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.INFO if debug else logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


configure_log_levels(debug=False)

# Link deletion: planned deletions are stored in the database and checked regularly, so they
# also happen after a restart or crash. Telegram only lets bots delete messages for 48 hours.
DELETION_CHECK_SECONDS = 30
EXPORT_INTERVAL_SECONDS = 60
overview_exporter: OverviewExporter | None = None
EXPORT_JOB_ID = "overview-export"
DELETION_JOB_ID = "link-deletion"
BACKGROUND_JOB_IDS = {EXPORT_JOB_ID, DELETION_JOB_ID}  # kept when a new survey is started
TELEGRAM_DELETE_LIMIT = timedelta(hours=48)
START_LINK_TYPE = "START_LINK"   # start survey link; SUBSCRIBE is used for the subscription questions
NOTICE_TYPE = "NOTICE"           # short notices such as "already subscribed", deleted after a minute
NOTICE_DELETE_MINUTES = 1
deletion_lock = asyncio.Lock()

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
dashboard_task: asyncio.Task[None] | None = None
dashboard_stop_event: asyncio.Event | None = None


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
    global application, application_loop, dashboard_task, dashboard_stop_event

    application = app
    application_loop = asyncio.get_running_loop()

    dashboard = ConsoleDashboard(
        db_handler,
        console,
        participant_number_digits=(
            config_handler.config.participantNumberDigits
            if config_handler.config.useParticipantNumbers else None
        ),
        new_survey=start_new_survey,
    )
    if dashboard.is_available(console):
        dashboard_stop_event = asyncio.Event()
        dashboard_task = asyncio.create_task(
            dashboard.run(dashboard_stop_event),
            name="console-dashboard",
        )

    EmergencyStart(
        schedule_util,
        db_handler,
        send_notification_broadcast,
        send_end_survey_reminder if config_handler.config.endSurveyReminderEnabled else None,
    )
    schedule_notifications()

    logging.info("Start scheduler...")
    scheduler.start()
    logging.info(BOT_RUNNING)


async def post_shutdown(_: Application) -> None:
    """
    Called by PTB during shutdown.
    """
    if dashboard_stop_event is not None:
        dashboard_stop_event.set()
    if dashboard_task is not None:
        try:
            await dashboard_task
        except Exception as err:  # the dashboard must never block a clean shutdown
            logging.error("Console dashboard stopped with an error: %s", err)

    if scheduler.running:
        logging.info("Shutdown scheduler...")
        scheduler.shutdown(wait=True)

    export_overview()  # the files show the final state after the bot was stopped


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
    settings = config_handler.config.linkDeletionSettings
    if settings.start_DeleteLinkAtSubscriptionDeadline:
        # subscription questions remembered by older versions get the deadline as deletion time
        db_handler.schedule_deletion_for_type(SurveyType.SUBSCRIBE, config_handler.config.subscription_deadline)

    warn_about_telegram_delete_limit()

    # readable copies of the operator console in the export folder, written at startup and every minute
    global overview_exporter
    overview_exporter = OverviewExporter(
        db_handler,
        participant_number_digits=(
            config_handler.config.participantNumberDigits if config_handler.config.useParticipantNumbers else None
        ),
    )
    scheduler.add_job(
        export_overview,
        "interval",
        seconds=EXPORT_INTERVAL_SECONDS,
        id=EXPORT_JOB_ID,
        next_run_time=datetime.now(),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # the first check runs right at startup and deletes everything that became due meanwhile
    scheduler.add_job(
        delete_due_messages,
        "interval",
        seconds=DELETION_CHECK_SECONDS,
        id=DELETION_JOB_ID,
        next_run_time=datetime.now(),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def export_overview() -> None:
    """
    Updates the overview files. Called by APScheduler and once more at shutdown.
    """
    if overview_exporter is None:
        return
    try:
        overview_exporter.export()
    except Exception as err:  # the files are a convenience; problems must never stop the bot
        logging.error("Could not update the overview files in '%s': %s", overview_exporter.folder, err)


def start_new_survey() -> str:
    """
    Closes the running survey and starts a new one with the same config (key u in the console).

    The database is saved as db/userIdDb_abgeschlossen_<date>.db and the overview files as
    export/abgeschlossen_<date>/; then the bot continues with an empty database, so everyone
    can subscribe again. Planned survey dates and reminders of the old survey are removed,
    planned link deletions are kept.

    Runs in the event loop without awaiting, so no Telegram update is handled in between.

    :return: a short German note for the console where the old survey was saved
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    label = f"abgeschlossen_{stamp}"
    counter = 2
    while db_handler.archive_file(label).exists() or (EXPORT_FOLDER / label).exists():
        label = f"abgeschlossen_{stamp}_{counter}"
        counter += 1

    archive_file = db_handler.archive_file(label)
    export_folder = EXPORT_FOLDER / label

    try:
        # final overview of the old survey; the database copy below is the complete record
        OverviewExporter(
            db_handler,
            folder=export_folder,
            participant_number_digits=overview_exporter.participant_number_digits if overview_exporter else None,
        ).export()
        db_handler.archive_and_reset(archive_file)
    except Exception:
        # the old survey continues unchanged, so no half-finished copy is left behind
        shutil.rmtree(export_folder, ignore_errors=True)
        raise

    removed = remove_survey_jobs()
    logging.info(NEW_SURVEY_STARTED.format(archive_file, export_folder, removed))
    export_overview()

    return f"Gesichert als {archive_file} (Übersicht: {export_folder}{os.sep})"


def remove_survey_jobs() -> int:
    """
    Removes the planned survey dates and end reminders from the scheduler, keeping the
    regular background jobs (overview export, link deletion).

    :return: number of removed jobs
    """
    removed = 0
    for job in scheduler.get_jobs():
        if job.id in BACKGROUND_JOB_IDS:
            continue
        try:
            scheduler.remove_job(job.id)
            removed += 1
        except JobLookupError:
            pass  # ran just now
    return removed


def warn_about_telegram_delete_limit() -> None:
    """
    Warn about deletion settings that cannot work because of Telegram's 48-hour limit.
    """
    settings = config_handler.config.linkDeletionSettings
    limit_minutes = int(TELEGRAM_DELETE_LIMIT.total_seconds() // 60)
    for prefix in ("start", "daily", "end"):
        if getattr(settings, f"{prefix}_DeleteLinkTimer") and getattr(settings, f"{prefix}_DeleteDelayMinutes") >= limit_minutes:
            logging.warning(LINK_DELETE_DELAY_TOO_LONG.format(prefix, limit_minutes))

    deadline = config_handler.config.subscription_deadline
    if settings.start_DeleteLinkAtSubscriptionDeadline and deadline - datetime.now() > TELEGRAM_DELETE_LIMIT:
        logging.warning(LINK_DELETE_DEADLINE_FAR.format(deadline.strftime("%Y-%m-%d %H:%M")))


def minutes_from_now(minutes: int) -> datetime:
    return datetime.now() + timedelta(minutes=minutes)


def subscription_question_delete_time() -> datetime | None:
    """
    Deletion time of subscription questions and answers: the subscription deadline, if enabled.
    """
    if config_handler.config.linkDeletionSettings.start_DeleteLinkAtSubscriptionDeadline:
        return config_handler.config.subscription_deadline
    return None


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


def delete_due_messages() -> None:
    """
    Synchronous wrapper used by APScheduler.
    """
    submit_async(delete_due_messages_async())


# -----------------------------------------------------------------------------
# Telegram handlers
# -----------------------------------------------------------------------------


def get_link_participant_number(chat_id: int) -> str | None:
    """
    Return the number that completes this participant's survey links, or None when the
    feature is disabled.

    The number is drawn with the participant's first link and then reused for every
    later link. Participants who subscribed before the feature was enabled get theirs
    with their next link.
    """
    if not config_handler.config.useParticipantNumbers:
        return None

    return db_handler.assign_participant_number(chat_id, config_handler.config.participantNumberDigits)


async def send_tracked_message(
    bot: Bot,
    chat_id: int,
    text: str,
    message_type: str = "MESSAGE",
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """
    Send a message and persist its delivery for the operator dashboard.
    """
    if reply_markup is None:
        message = await bot.send_message(chat_id=chat_id, text=text)
    else:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )

    try:
        db_handler.record_outbound_message(chat_id, message.message_id, message_type)
    except sqlite3.Error as err:
        # Tracking is only for the operator dashboard; never let it abort a delivery flow.
        logging.error("Could not record sent message for %d: %s", chat_id, err)
    return message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /start.
    """
    chat_id = update.effective_chat.id
    await send_tracked_message(context.bot, chat_id, config_handler.config.texts.welcome)


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
    msg = await send_tracked_message(context.bot, chat_id, usr_msg)
    db_handler.insert_message_id(chat_id, msg.message_id, NOTICE_TYPE, minutes_from_now(NOTICE_DELETE_MINUTES))


async def subscribe_ask(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    log_msg: str,
    usr_msg: str,
) -> None:
    """
    Sends the next subscription question.
    """
    logging.debug(SUBSCRIPTION_ASK.format(chat_id, log_msg))
    msg = await send_tracked_message(context.bot, chat_id, usr_msg)
    db_handler.insert_message_id(chat_id, msg.message_id, SurveyType.SUBSCRIBE, subscription_question_delete_time())


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

    if (
    not config_handler.config.participantsEnterCondition
    and config_handler.config.linkDeletionSettings.deleteSubscriptionSetupMessages
    ):
        await delete_tracked_messages(db_handler.get_tracked_messages([chat_id], SurveyType.SUBSCRIBE))

    wakeup_time: time = TimeUtil.get_time_from_str(update.message.text)
    logging.info(SUBSCRIPTION_WAKEUP_TIME.format(chat_id, wakeup_time))
    context.user_data["wakeup_time"] = wakeup_time.strftime("%H:%M")

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

    if config_handler.config.linkDeletionSettings.deleteSubscriptionSetupMessages:
        await delete_tracked_messages(db_handler.get_tracked_messages([chat_id], SurveyType.SUBSCRIBE))

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
    markup = KeyboardBuilder.generate_link_markup(
        config_handler,
        SurveyType.SUBSCRIBE,
        condition,
        participant_number=get_link_participant_number(chat_id),
    )

    db_handler.register_participant(chat_id, condition, context.user_data.pop("wakeup_time", None))
    msg = await send_tracked_message(
        context.bot,
        chat_id,
        config_handler.config.texts.subscribe,
        SurveyType.SUBSCRIBE.name,
        markup,
    )

    settings = config_handler.config.linkDeletionSettings
    delete_times = []
    if settings.start_DeleteLinkTimer:
        delete_times.append(minutes_from_now(settings.start_DeleteDelayMinutes))
    if settings.start_DeleteLinkAtSubscriptionDeadline:
        delete_times.append(config_handler.config.subscription_deadline)
    if delete_times:
        db_handler.insert_message_id(chat_id, msg.message_id, START_LINK_TYPE, min(delete_times))


async def subscribe_wakeup_time_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Fallback handler for invalid subscription conversation input.
    """
    chat_id = update.effective_chat.id
    db_handler.insert_message_id(
        chat_id, update.message.message_id, SurveyType.SUBSCRIBE, subscription_question_delete_time()
    )

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
    await send_tracked_message(context.bot, chat_id, config_handler.config.texts.unsubscribe)


async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /help.
    """
    chat_id = update.effective_chat.id
    help_text = config_handler.config.help.help_text

    if config_handler.config.surveyCommandEnabled:
        help_text += config_handler.config.help.surveyCommandHelp

    await send_tracked_message(context.bot, chat_id, help_text)


async def send_survey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /survey.
    Sends the survey_reply message from the config file and the daily survey link to the user.
    """
    chat_id = update.effective_chat.id

    try:
        condition = db_handler.get_condition(chat_id)
    except LookupError:
        await send_tracked_message(
            context.bot,
            chat_id,
            config_handler.config.texts.survey_not_subscribed,
        )
        return

    markup: InlineKeyboardMarkup = KeyboardBuilder.generate_link_markup(
        config_handler,
        SurveyType.DAILY,
        condition,
        participant_number=get_link_participant_number(chat_id),
    )

    logging.info(SEND_SURVEY.format(SurveyType.DAILY.name, chat_id))

    msg: Message = await send_tracked_message(
        context.bot,
        chat_id,
        config_handler.config.texts.survey_reply,
        SurveyType.DAILY.name,
        markup,
    )

    db_handler.insert_message_id(chat_id, msg.message_id, SurveyType.DAILY, link_delete_time(SurveyType.DAILY))


async def handle_end_survey_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the end-survey-reminder button callback.
    """
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    callback_code = query.data.split("+")
    message_id = query.message.message_id

    # the answer must still work when the question can no longer be deleted (e.g. after 48 hours)
    await delete_tracked_messages([(chat_id, message_id, None)], bot=context.bot)

    if callback_code[0] == ER_NO:
        condition, end_index = db_handler.get_condition_and_end_index(chat_id, callback_code[1])
        markup = KeyboardBuilder.generate_link_markup(
            config_handler,
            SurveyType.END,
            condition,
            end_index,
            get_link_participant_number(chat_id),
        )

        msg = await send_tracked_message(
            context.bot,
            chat_id,
            config_handler.config.texts.endSurveyReminder,
            SurveyType.END.name,
            markup,
        )

        db_handler.insert_message_id(chat_id, msg.message_id, SurveyType.END, link_delete_time(SurveyType.END))


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

    if delete_link_at_new_link(survey_type):
        await delete_tracked_messages(
            db_handler.get_tracked_messages([x[0] for x in subscriber_information], survey_type)
        )

    msg_text: str = config_handler.get_message(survey_type)

    for chat_id, condition, end_index in subscriber_information:
        try:
            participant_number = get_link_participant_number(chat_id)
        except (sqlite3.Error, RuntimeError) as err:
            # one participant's database problem must not stop the broadcast for everyone else
            logging.error("Can't send survey to %d, no participant number: %s", chat_id, err)
            continue

        markup: InlineKeyboardMarkup = KeyboardBuilder.generate_link_markup(
            config_handler,
            survey_type,
            condition,
            end_index,
            participant_number,
        )
        try:
            logging.info(SEND_SURVEY.format(survey_type.name, chat_id))
            msg = await send_tracked_message(
                application.bot,
                chat_id,
                msg_text,
                survey_type.name,
                markup,
            )
            db_handler.insert_message_id(chat_id, msg.message_id, survey_type, link_delete_time(survey_type))
        except Forbidden as err:
            logging.error("Can't send survey to %d because the bot is blocked or forbidden: %s", chat_id, err)
        except NetworkError as err:
            logging.error("Network error while sending survey to %d: %s", chat_id, err)
        except TelegramError as err:
            logging.error("Telegram error while sending survey to %d: %s", chat_id, err)

    if survey_type == SurveyType.END and config_handler.config.endSurveyReminderEnabled:
        schedule_util.schedule_end_survey_reminder(send_end_survey_reminder, subscriber_information)


def delete_link_at_new_link(survey_type: SurveyType) -> bool:
    settings = config_handler.config.linkDeletionSettings
    if survey_type == SurveyType.DAILY:
        return settings.daily_DeleteLinkAtNewLink
    if survey_type == SurveyType.END:
        return settings.end_DeleteLinkAtNewLink
    return False


def link_delete_time(survey_type: SurveyType) -> datetime | None:
    """
    When a daily or end survey link sent now is to be deleted by its timer, or None.
    """
    settings = config_handler.config.linkDeletionSettings
    if survey_type == SurveyType.DAILY and settings.daily_DeleteLinkTimer:
        return minutes_from_now(settings.daily_DeleteDelayMinutes)
    if survey_type == SurveyType.END and settings.end_DeleteLinkTimer:
        return minutes_from_now(settings.end_DeleteDelayMinutes)
    return None


def remove_job_from_scheduler(job_id: str) -> None:
    """
    Removes a job from APScheduler if it still exists.
    """
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        logging.debug("Job with id " + job_id + " not rescheduled")


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
            await send_tracked_message(
                application.bot,
                chat_id,
                config_handler.config.texts.endSurveyReminder,
                "END_REMINDER",
                markup,
            )
        except Forbidden as err:
            logging.error("Can't send end reminder to %d because the bot is blocked or forbidden: %s", chat_id, err)
        except TelegramError as err:
            logging.error("Telegram error while sending end reminder to %d: %s", chat_id, err)


async def delete_due_messages_async() -> None:
    """
    Deletes all messages whose planned deletion time has come.
    """
    async with deletion_lock:  # a slow run must not overlap with the next check
        await delete_tracked_messages(db_handler.get_due_message_deletions(datetime.now()))


async def delete_tracked_messages(messages: list[TrackedMessage], bot: Bot | None = None) -> None:
    """
    Deletes remembered messages in Telegram and forgets them afterwards.

    Messages older than 48 hours are not sent to Telegram, which would refuse them; they are
    reported together in one warning. Messages that failed because of a network problem are
    kept and tried again at the next check.
    """
    bot = bot or application.bot
    now = datetime.now()
    too_old = 0

    for chat_id, message_id, sent_at in messages:
        if sent_at is not None and now - sent_at >= TELEGRAM_DELETE_LIMIT:
            too_old += 1
            db_handler.remove_tracked_message(chat_id, message_id)
            continue

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except BadRequest as err:
            if "can't be deleted" in str(err).lower():
                too_old += 1  # entries from older versions have no send time to check beforehand
            else:
                logging.debug("Message %d in chat %d was not deleted: %s", message_id, chat_id, err)
        except Forbidden as err:
            logging.info("Can't delete message %d in chat %d, the bot was blocked: %s", message_id, chat_id, err)
        except NetworkError as err:
            logging.warning("Network error while deleting message %d in chat %d, trying again later: %s",
                            message_id, chat_id, err)
            continue
        except TelegramError as err:
            logging.error("Telegram error while deleting message %d in chat %d: %s", message_id, chat_id, err)

        db_handler.remove_tracked_message(chat_id, message_id)

    if too_old:
        logging.warning(LINKS_TOO_OLD_TO_DELETE.format(too_old))


def _start_arguments() -> list[str]:
    """
    The start arguments without options such as --debug.
    """
    return [argument for argument in sys.argv[1:] if not argument.startswith("--")]


def _debug_requested() -> bool:
    return DEBUG_OPTION in sys.argv[1:]


def _get_config_path() -> Path | None:
    arguments = _start_arguments()
    if arguments:
        return Path(arguments[0])

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "config.yml"

    return None


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    """
    Main method. Initializes all required objects and starts the bot.
    """
    global config_handler, schedule_util, db_handler, scheduler

    start_file_logging()
    if _debug_requested():
        configure_log_levels(debug=True)
        logging.info("Debug mode: detailed log messages are shown.")
    for option in sys.argv[1:]:
        if option.startswith("--") and option != DEBUG_OPTION:
            logging.warning("Unknown start option '%s' is ignored. Available: %s", option, DEBUG_OPTION)

    logging.info("Load Config...")
    config_path: Path | None = None
    try:
        config_path = _get_config_path() or ConfigHandler.find_config_file()
        config_handler = ConfigHandler(config_file=config_path)
        config_handler.config.api_token = check_api_token(config_handler.config.api_token, config_path)

    except StartupError as err:
        report(err)
        raise SystemExit(1)

    except ConfigValidationException as err:
        logging.error("The bot could not be started because the config file %s contains errors:", config_path)
        for message in err.message_list:
            logging.error("  - %s", message)
        raise SystemExit(1)

    except FileNotFoundError as err:
        report(config_file_not_found(err))
        raise SystemExit(1)

    except (yaml.YAMLError, json.JSONDecodeError) as err:
        report(config_syntax_error(err, config_path))
        raise SystemExit(1)

    except TypeError as err:
        report(config_incomplete(err, config_path))
        raise SystemExit(1)

    except (ValueError, KeyError) as err:
        logging.error("The config file %s contains an invalid value: %s", config_path, err)
        raise SystemExit(1)

    logging.info("Init...")

    executors = {
        "default": ThreadPoolExecutor(5),
    }
    scheduler = BackgroundScheduler(executors=executors)

    db_handler = DbHandler()
    schedule_util = ScheduleUtil(scheduler, config_handler.config, db_handler)

    try:
        app = init_application()
        init_handlers(app)

        logging.info("Start polling...")
        app.run_polling()
    except KeyboardInterrupt:
        logging.info("Shutdown requested by user...")
    except InvalidToken:
        report(invalid_token_error(config_path))
        raise SystemExit(1)
    except NetworkError as err:
        report(network_error(err))
        raise SystemExit(1)

if __name__ == "__main__":
    main()
