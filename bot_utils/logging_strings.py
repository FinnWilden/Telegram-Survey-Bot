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
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Telegram Survey Bot.  If not, see <http://www.gnu.org/licenses/>.
"""
SUBSCRIPTION_REJECTED = "Subscription rejected for {} because: {}"
SUBSCRIPTION_EARLY = "Early"
SUBSCRIPTION_LATE = "Late"
SUBSCRIPTION_ALREADY_SUBSCRIBED = "Already subscribed"
SUBSCRIPTION_CONDITIONS_FULL = "Conditions full"
PARTICIPANT_NUMBER_ASSIGNED = "Assigned participant number to {}: {}"
PARTICIPANT_NUMBERS_LENGTH_FULL = "All {}-digit participant numbers are taken, using {} digits"
SUBSCRIPTION_HANDLE = "Handle Subscription of: {}"
SUBSCRIPTION_ASK = "Subscription ask {}: {}"
SUBSCRIPTION_TIMEZONE = "Timezone"
SUBSCRIPTION_TIME_CALC = "Wakeup time"
SUBSCRIPTION_CONDITION = "Condition"
SUBSCRIPTION_TIMEZONE_DELTA = "Got timezone delta for {}: {}"
SUBSCRIPTION_WAKEUP_TIME = "Got wakeup time for {}: {}"
SUBSCRIPTION_GOT_CONDITION = "Got condition for {}: {}"
SUBSCRIPTION_FINISHED = "Send subscribe survey to {}"
UNSUBSCRIBE = "Got unsubscribe command from {}"
SEND_SURVEY = "Send survey of type {} to {}"
SU_ADD_JOB = "Add job with id: {}"
DB_UPDATE_CONDITION = "Update condition for {}: {}"
DB_INSERT_SUBSCRIBER_ENTRY = "Insert subscriber entries:"
DB_INSERT_SUBSCRIBER_ENTRY_DATA = "chat_id: {}, date_str: {}, survey_type: {}, condition: {}, end_distribution: {}"
EMERGENCY_DATES_FOUND = (
    "\n"
    "--------------!!!!!!!     WARNING      !!!!!!!--------------\n\n"
    "Found {} future survey dates. Do you want to reschedule them?"
)
EMERGENCY_DATES_WARN = (
    "\n"
    "--------------!!!!!!!     WARNING      !!!!!!!--------------\n\n"
    "Should the date entries be removed from the database?\n"
    "If not, all previously subscribed users cannot subscribe to the bot again."
)
EMERGENCY_DATES_RESCHEDULE = "Reschedule {} survey dates:"
EMERGENCY_REMINDERS_RESCHEDULE = "Reschedule {} end survey reminder dates"
EMERGENCY_NO_TERMINAL = "No terminal to answer in (e.g. bot running as a background service). Answering '{}' automatically."
EMERGENCY_DATES_IGNORE = "Ignore {} survey dates"
EMERGENCY_DATES_IGNORE_DELETE = "Ignore and delete {} survey dates"
LINKS_TOO_OLD_TO_DELETE = (
    "{} message(s) could not be deleted because they were sent more than 48 hours ago. "
    "Telegram only allows bots to delete messages within 48 hours, so participants still see them."
)
LINK_DELETE_DELAY_TOO_LONG = (
    "'linkDeletionSettings.{0}_DeleteDelayMinutes' is {1} minutes (48 hours) or more. Telegram only allows "
    "bots to delete messages within 48 hours, so these links will not be deleted."
)
LINK_DELETE_DEADLINE_FAR = (
    "Start links sent more than 48 hours before the subscription deadline ({}) cannot be deleted at the "
    "deadline, because Telegram only allows bots to delete messages within 48 hours."
)
