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
# ============================================================
# TABLE CREATION
# ============================================================

CREATE_TABLE_SUBSCRIBER = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    condition INTEGER NOT NULL,
    end_index INTEGER NOT NULL,
    PRIMARY KEY (chat_id, date, type)
);
"""

CREATE_TABLE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    PRIMARY KEY (chat_id, message_id, type)
);
"""

CREATE_TABLE_OFFSETS = """
CREATE TABLE IF NOT EXISTS offsets (
    chat_id INTEGER PRIMARY KEY,
    offset INTEGER NOT NULL
);
"""

CREATE_TABLE_CONDITIONS = """
CREATE TABLE IF NOT EXISTS conditions (
    chat_id INTEGER PRIMARY KEY,
    condition INTEGER NOT NULL
);
"""

CREATE_TABLE_PARTICIPANTS = """
CREATE TABLE IF NOT EXISTS participants (
    chat_id INTEGER PRIMARY KEY,
    first_registered_at TEXT,
    last_registered_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    unsubscribed_at TEXT,
    condition INTEGER,
    wakeup_time TEXT
);
"""

PARTICIPANT_MIGRATION_COLUMNS = {
    "condition": "ALTER TABLE participants ADD COLUMN condition INTEGER",
    "wakeup_time": "ALTER TABLE participants ADD COLUMN wakeup_time TEXT",
}

CREATE_TABLE_OUTBOUND_MESSAGES = """
CREATE TABLE IF NOT EXISTS outbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    sent_at TEXT NOT NULL
);
"""

CREATE_TABLE_PARTICIPANT_NUMBERS = """
CREATE TABLE IF NOT EXISTS participant_numbers (
    chat_id INTEGER PRIMARY KEY,
    number INTEGER NOT NULL UNIQUE,
    code TEXT NOT NULL,
    assigned_at TEXT NOT NULL
);
"""

CREATE_INDEX_OUTBOUND_MESSAGES_CHAT_ID = """
CREATE INDEX IF NOT EXISTS idx_outbound_messages_chat_id
ON outbound_messages (chat_id);
"""

BACKFILL_PARTICIPANTS = """
INSERT OR IGNORE INTO participants (chat_id, first_registered_at, last_registered_at, is_active, condition)
SELECT chat_id, NULL, NULL, 1, MIN(condition)
FROM subscribers
GROUP BY chat_id;
"""

BACKFILL_PARTICIPANT_CONDITIONS = """
UPDATE participants
SET condition=(
    SELECT MIN(subscribers.condition)
    FROM subscribers
    WHERE subscribers.chat_id=participants.chat_id
)
WHERE condition IS NULL;
"""


# ============================================================
# SUBSCRIBERS
# ============================================================

INSERT_SUBSCRIBER = """
INSERT INTO subscribers (chat_id, date, type, condition, end_index)
VALUES (?, ?, ?, ?, ?)
"""

SELECT_SUBSCRIBER_ALL = """
SELECT chat_id, date, type, condition, end_index
FROM subscribers
"""

SELECT_SUBSCRIBER_DATE_TYPE = """
SELECT chat_id, condition, end_index
FROM subscribers
WHERE date=?
AND type=?
"""

SELECT_SUBSCRIBER_ID_DATE = """
SELECT condition, end_index
FROM subscribers
WHERE chat_id=?
AND date=?
"""

SELECT_SUBSCRIBER_EMERGENCY = """
SELECT date, type
FROM subscribers
"""

SELECT_SUBSCRIBERS_BY_TYPE = """
SELECT chat_id, date
FROM subscribers
WHERE type=?
ORDER BY date, chat_id
"""

SELECT_SUBSCRIBER_CHAT_ID = """
SELECT chat_id, date, type, condition, end_index
FROM subscribers
WHERE chat_id=?
"""

UPDATE_SUBSCRIBER = """
UPDATE subscribers
SET condition=?
WHERE chat_id=?
"""

DELETE_SUBSCRIBER_CHAT_ID = """
DELETE FROM subscribers
WHERE chat_id=?
"""

DELETE_ALL_SUBSCRIBERS = """
DELETE FROM subscribers
"""


# ============================================================
# MESSAGES
# ============================================================

INSERT_MESSAGE = """
INSERT OR REPLACE INTO messages (chat_id, message_id, type, sent_at, delete_at)
VALUES (?, ?, ?, ?, ?)
"""

# Columns added after the first release. sent_at: when the message was sent (Telegram only
# lets bots delete messages for 48 hours); delete_at: when it is to be deleted (NULL = only
# when the next link of the same type is sent). Both are NULL for entries from older versions.
MESSAGE_MIGRATION_COLUMNS = {
    "sent_at": "ALTER TABLE messages ADD COLUMN sent_at TEXT",
    "delete_at": "ALTER TABLE messages ADD COLUMN delete_at TEXT",
}

SELECT_TRACKED_MESSAGES = """
SELECT chat_id, message_id, sent_at
FROM messages
WHERE chat_id=?
AND type=?
"""

SELECT_DUE_MESSAGE_DELETIONS = """
SELECT chat_id, message_id, sent_at
FROM messages
WHERE delete_at IS NOT NULL
AND delete_at<=?
ORDER BY delete_at
"""

DELETE_TRACKED_MESSAGE = """
DELETE FROM messages
WHERE chat_id=?
AND message_id=?
"""

SET_DELETE_AT_FOR_UNSCHEDULED_TYPE = """
UPDATE messages
SET delete_at=?
WHERE type=?
AND delete_at IS NULL
"""

# Keeps messages with a planned deletion, so links still disappear after unsubscribing.
DELETE_MESSAGE = """
DELETE FROM messages
WHERE chat_id=?
AND delete_at IS NULL
"""


# ============================================================
# OFFSETS
# ============================================================

INSERT_OFFSET = """
INSERT INTO offsets (chat_id, offset)
VALUES (?, ?)
"""

SELECT_OFFSET = """
SELECT offset
FROM offsets
WHERE chat_id=?
"""

DELETE_OFFSET = """
DELETE FROM offsets
WHERE chat_id=?
"""


# ============================================================
# CONDITIONS
# ============================================================

INSERT_CONDITION = """
INSERT INTO conditions (chat_id, condition)
VALUES (?, ?)
"""

SELECT_CONDITION = """
SELECT condition
FROM conditions
WHERE chat_id=?
"""

SELECT_CONDITIONS = """
SELECT condition
FROM conditions
"""

DELETE_CONDITION = """
DELETE FROM conditions
WHERE chat_id=?
"""

UPSERT_PARTICIPANT = """
INSERT INTO participants (
    chat_id,
    first_registered_at,
    last_registered_at,
    is_active,
    unsubscribed_at,
    condition,
    wakeup_time
)
VALUES (?, ?, ?, 1, NULL, ?, ?)
ON CONFLICT(chat_id) DO UPDATE SET
    last_registered_at=excluded.last_registered_at,
    is_active=1,
    unsubscribed_at=NULL,
    condition=excluded.condition,
    wakeup_time=excluded.wakeup_time
"""

MARK_PARTICIPANT_UNSUBSCRIBED = """
UPDATE participants
SET is_active=0, unsubscribed_at=?
WHERE chat_id=?
"""

MARK_ALL_PARTICIPANTS_UNSUBSCRIBED = """
UPDATE participants
SET is_active=0, unsubscribed_at=?
WHERE is_active=1
"""

INSERT_OUTBOUND_MESSAGE = """
INSERT INTO outbound_messages (chat_id, message_id, message_type, sent_at)
VALUES (?, ?, ?, ?)
"""

# True while a participant still has a survey or end reminder date after the given time
# (parameter: "%Y-%m-%d-%H:%M", the format of subscribers.date, which sorts like a date).
HAS_OPEN_SURVEY_DATES = """
EXISTS (
    SELECT 1
    FROM subscribers
    WHERE subscribers.chat_id=participants.chat_id
    AND subscribers.date>?
)
"""

SELECT_PARTICIPANT_SUMMARY = f"""
SELECT
    COUNT(*) AS total_participants,
    COALESCE(SUM(is_active AND {HAS_OPEN_SURVEY_DATES}), 0) AS active_participants,
    COALESCE(SUM(is_active AND NOT {HAS_OPEN_SURVEY_DATES}), 0) AS finished_participants,
    COALESCE(SUM(NOT is_active), 0) AS unsubscribed_participants,
    MIN(first_registered_at) AS first_registration,
    MAX(last_registered_at) AS last_registration
FROM participants
"""

SELECT_OUTBOUND_MESSAGE_COUNTS = """
SELECT message_type, COUNT(*) AS message_count
FROM outbound_messages
GROUP BY message_type
"""

SELECT_PARTICIPANT_OVERVIEW = f"""
SELECT
    participants.chat_id,
    participants.first_registered_at,
    participants.last_registered_at,
    participants.is_active,
    {HAS_OPEN_SURVEY_DATES} AS has_open_survey_dates,
    participants.condition,
    participants.wakeup_time,
    offsets.offset AS time_offset,
    participant_numbers.code AS participant_number,
    COUNT(outbound_messages.id) AS message_count,
    MAX(outbound_messages.sent_at) AS last_message_at
FROM participants
LEFT JOIN offsets ON participants.chat_id=offsets.chat_id
LEFT JOIN participant_numbers ON participants.chat_id=participant_numbers.chat_id
LEFT JOIN outbound_messages ON participants.chat_id=outbound_messages.chat_id
GROUP BY participants.chat_id
ORDER BY
    participants.first_registered_at IS NULL,
    participants.first_registered_at,
    participants.chat_id
"""

SELECT_RECENT_OUTBOUND_MESSAGES = """
SELECT chat_id, message_type, sent_at
FROM outbound_messages
ORDER BY id DESC
LIMIT 100
"""

# ============================================================
# PARTICIPANT NUMBERS
# ============================================================

SELECT_PARTICIPANT_NUMBER = """
SELECT code
FROM participant_numbers
WHERE chat_id=?
"""

COUNT_PARTICIPANT_NUMBERS = """
SELECT COUNT(*) AS used_count
FROM participant_numbers
"""

SELECT_PARTICIPANT_NUMBERS_IN_RANGE = """
SELECT number
FROM participant_numbers
WHERE number BETWEEN ? AND ?
"""

INSERT_PARTICIPANT_NUMBER = """
INSERT INTO participant_numbers (chat_id, number, code, assigned_at)
VALUES (?, ?, ?, ?)
"""
