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
INSERT INTO messages (chat_id, message_id, type)
VALUES (?, ?, ?)
"""

SELECT_MESSAGE = """
SELECT chat_id, message_id, type
FROM messages
WHERE chat_id=?
AND message_id=?
AND type=?
"""

SELECT_MESSAGE_TYPE = """
SELECT chat_id, message_id
FROM messages
WHERE type=?
"""

SELECT_MESSAGE_ID = """
SELECT chat_id, message_id
FROM messages
WHERE chat_id=?
AND type=?
"""

DELETE_MESSAGE = """
DELETE FROM messages
WHERE chat_id=?
"""

DELETE_MESSAGE_TYPE = """
DELETE FROM messages
WHERE type=?
"""

DELETE_MESSAGE_ID = """
DELETE FROM messages
WHERE chat_id=?
AND type=?
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