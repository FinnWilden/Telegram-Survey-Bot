# Telegram Survey Bot

[![Tests](https://github.com/FinnWilden/Telegram-Survey-Bot/actions/workflows/tests.yml/badge.svg)](https://github.com/FinnWilden/Telegram-Survey-Bot/actions)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Made with Python](https://img.shields.io/badge/Made%20with-Python-blue.svg)](https://www.python.org/)

![Logo](https://github.com/Raze97/Telegram-Survey-Bot-Logos/blob/master/logo/logo_text.png?raw=true)

A configurable [Telegram](https://telegram.org/) bot for conducting ambulatory assessment, experience sampling (ESM), diary, and longitudinal survey studies via smartphones.

The bot automatically distributes survey links to participants using predefined schedules, individualized wake-up based timing, randomized prompts, and condition assignment. It is designed to provide a lightweight and easy-to-deploy solution for researchers without requiring dedicated server infrastructure or app development.

The project is written in Python and supports Windows, Linux, and macOS.

---

# Features

* Fixed survey schedules using predefined dates and times
* Relative scheduling based on participant wake-up times
* Day-based scheduling relative to subscription date
* Randomized survey time shifts
* Multiple survey types:

  * Start surveys
  * Daily surveys
  * End surveys
* Flexible end survey link distribution strategies
* Participant condition assignment and randomization
* Random, permanent participant numbers that complete survey link stems
* Optional timezone support
* Automatic survey reminder scheduling
* Automatic deletion of expired survey links, optionally so that only the newest link is visible (`deleteOldLinksBeforeNewLink`)
* SQLite-based lightweight persistence
* Logging and emergency restart handling
* Fully configurable through a single PyYaml configuration file

---

# Documentation

The technical repository overview is provided in this README.

Detailed setup instructions, configuration examples, and user guides are available in the Wiki:

➡ **Wiki:**
https://github.com/FinnWilden/Telegram-Survey-Bot/wiki

The Wiki includes:

* Installation instructions
* Bot setup with Telegram BotFather
* Configuration explanations
* Running studies

---

# Project Status

Recent improvements include:

* Python modernization and refactoring
* Type hint updates
* Improved SQLite handling
* Automated unit testing
* GitHub Actions continuous integration
* Improved scheduling reliability
* Code cleanup and restructuring
* Expanded documentation

---

# Automated Testing & Continuous Integration

The project uses automated unit tests and GitHub Actions based continuous integration (CI).

Tests are automatically executed on every push and pull request using Python 3.10 through 3.14.

The current test suite includes:

* Time and scheduling utilities
* Database handling
* Configuration parsing and validation
* Scheduling logic
* Telegram bot handlers using mocks
* Keyboard generation

This helps detect regressions early and improves long-term maintainability and reliability.

---

# Operator console

When the bot is started in an interactive terminal, a live dashboard is shown
below the log output. It refreshes every two seconds and is controlled with
single key presses (no Enter needed):

| Key | View |
|-----|------|
| `d` | **Dashboard**: participant totals split into active, finished and unsubscribed, first and latest registration, and counts of sent messages (start, daily and end links, other messages); with participant numbers also how many numbers are assigned |
| `p` | **Participants**: one row per participant with Telegram chat ID, participant number (when enabled), first and latest registration, status (active, finished = registered but all survey dates are over, or unsubscribed), the answers given during subscription (condition, wake-up time, time offset to the server), number of messages received and the latest delivery |
| `v` | **Delivery history**: the 100 most recent messages sent by the bot with time, chat ID and message type |
| `n` / `b` | Next / previous page in the participant and delivery views |
| `u` | **New survey**: after a confirmation with `j`, closes the running survey and starts a new one with the same config (see below) |
| `Ctrl+C` | Stop the bot |

Long tables are split into pages that fit the terminal height. On narrow
terminals, less important participant columns are hidden; the participant's
own answers always stay visible. The dashboard is not started when the bot
runs without an interactive terminal (e.g. as a service); the log file is
written in both cases.

The log shows what happens in the study: subscriptions, sent surveys, warnings
and errors. Start the bot with `--debug` (e.g. `python bot.py config/local-test.yml --debug`)
to also see internal steps such as every scheduled job and its execution.

The same information is also written to the `export` folder every minute (and at
start and stop), so it can be read without the terminal or the database:
`overview.txt` (the dashboard), `participants.csv` (all participants) and
`deliveries.csv` (every sent message). The CSV files use `;` and open directly in Excel.

**Starting a new survey** (`u`, e.g. after a test run): the database is saved as
`db/userIdDb_abgeschlossen_<date>_<time>.db` and the overview files as
`export/abgeschlossen_<date>_<time>/`. The bot then continues with an empty
database: planned survey dates and end reminders of the old survey are removed,
everyone can subscribe again and participant numbers are assigned anew. Links of
the old survey that are planned for deletion are still deleted on time. Without
a terminal, stop the bot and move `db/userIdDb.db` away instead.

Unsubscribed participants and their delivery history remain in the database.
For database entries that existed before this feature, Telegram IDs and
conditions are recovered from the subscriber table, but historical
registration and message-delivery times cannot be; those are shown as
unknown. The database contains pseudonymous Telegram IDs, study conditions
and delivery metadata, so protect it accordingly.

---

# Participant numbers in survey links

Survey tools often identify participants by a number in the link. Instead of
listing one full link per participant, you write each link once with the
placeholder `{participant}`, and the bot fills in a number for every
participant:

```yaml
useParticipantNumbers: true
participantNumberDigits: 5    # 5 -> numbers like 04711 (default: 5)

urls:
  start_url:
    - "https://survey.example/start?id={participant}&lang=de"   # placeholder in the middle ...
  daily_url:
    - "https://survey.example/daily/{participant}"               # ... or at the end
  end_url:
    - "https://survey.example/end?id={participant}"
  end_url_distribution: "NONE"
```

* Every participant gets a **random number** with `participantNumberDigits`
  digits (leading zeros included) when they receive their first link. No two
  participants get the same number.
* There is **no limit on participants**: when all numbers of that length are
  taken, the next participants automatically get one digit more.
* The number is **stored permanently** and used for **all** of that
  participant's links: start, daily, end, `/survey` and the end-survey
  reminder. It stays the same after unsubscribing and subscribing again,
  across bot restarts, and even if `participantNumberDigits` is changed later.
* While `useParticipantNumbers` is `true`, **every url must contain
  `{participant}`**, anywhere in the url. The bot refuses to start otherwise
  and names the url. Keep the quotes around urls in YAML.
* One url per survey type is enough. Several urls (the same count in
  `start_url`, `daily_url` and `end_url`) define several conditions.
* `end_url` entries are plain urls. A list per entry is only needed for the
  `DAY`, `TIME`, `MIXED` and `RANDOM` distributions, which send a different end
  url per end day or time.
* Participants who subscribed before the option was enabled get their number
  with their next link.
* With `useParticipantNumbers: false` the urls are sent exactly as written and
  must not contain `{participant}`. Configs without these keys behave as before.

---

# Installation

See the Wiki for installation instructions:

➡ https://github.com/FinnWilden/Telegram-Survey-Bot/wiki

---

# Precompiled releases

Maintainer instructions for preparing and publishing precompiled builds are in [docs/precompiled-releases.md](docs/precompiled-releases.md).

---

# Contributing

Bug reports, ideas, feature requests, and pull requests are very welcome.

If you encounter problems or have suggestions for improvements, please open an issue:

➡ https://github.com/FinnWilden/Telegram-Survey-Bot/issues

Contributions are especially welcome regarding:

* Additional scheduling strategies
* Improved Telegram interaction flows
* Better timezone handling
* UI/UX improvements
* Documentation
* Testing
* Refactoring and modernization

---

# Technologies Used

* [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
* [APScheduler](https://github.com/agronholm/apscheduler)
* SQLite
* pytest
* GitHub Actions

---

# License

Copyright (c) 2020
Michael Barthelmäs, Marcel Killinger, Johannes Keller

Licensed under the GNU General Public License v3.0.

See:

* LICENSE
* https://www.gnu.org/licenses/gpl-3.0.txt

---

# Citation

If you use this software in scientific work, please cite:

```text
Barthelmäs, M., Killinger, M., & Keller, J. (2020).
Telegram-Survey-Bot (Version 1.0) [Computer software].
https://github.com/Raze97/Telegram-Survey-Bot
```

---

# Acknowledgements

Originally developed by Marcel Killinger and Michael Barthelmäs under supervision of Johannes Keller at the Department of Social Psychology, Ulm University.

The project is currently being further modernized and extended by Finn Wilden.
