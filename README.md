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
* Automatic deletion of expired survey links
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
| `d` | **Dashboard**: participant totals, active subscriptions, first and latest registration, and counts of sent messages (start, daily and end links, other messages); with participant numbers also how many numbers are assigned and still free |
| `p` | **Participants**: one row per participant with Telegram chat ID, participant number (when enabled), first and latest registration, status (active/unsubscribed), the answers given during subscription (condition, wake-up time, time offset to the server), number of messages received and the latest delivery |
| `v` | **Delivery history**: the 100 most recent messages sent by the bot with time, chat ID and message type |
| `n` / `b` | Next / previous page in the participant and delivery views |

Long tables are split into pages that fit the terminal height. On narrow
terminals, less important participant columns are hidden; the participant's
own answers always stay visible. The dashboard is not started when the bot
runs without an interactive terminal (e.g. as a service); the log file is
written in both cases.

Unsubscribed participants and their delivery history remain in the database.
For database entries that existed before this feature, Telegram IDs and
conditions are recovered from the subscriber table, but historical
registration and message-delivery times cannot be; those are shown as
unknown. The database contains pseudonymous Telegram IDs, study conditions
and delivery metadata, so protect it accordingly.

---

# Participant numbers in survey links

Survey tools often identify participants by a number in the link, e.g.
`https://survey.example/start?id=1`, `...?id=2`, and so on. Instead of listing
one full link per participant, you can enter only the fixed part of each link
(the *stem*) and let the bot add a participant number:

```yaml
useParticipantNumbers: true
participantNumberSettings:
  minNumber: 1      # smallest number that may be drawn
  maxNumber: 500    # largest number that may be drawn
  padToDigits: 3    # optional leading zeros: 7 -> 007 (0 = none)

urls:
  start_url:
    - "https://survey.example/start?group=a&id="
    - "https://survey.example/start?group=b&id="
  daily_url:
    - "https://survey.example/daily?id={participant}&lang=de"
    - "https://survey.example/daily?id={participant}&lang=en"
  end_url:
    - ["https://survey.example/end-a/"]
    - ["https://survey.example/end-b/"]
  end_url_distribution: "NONE"
```

* Each participant gets a **random number** from `minNumber`..`maxNumber`
  when they first send `/subscribe`. No two participants get the same number.
* The number is **stored permanently** and used for **all** of that
  participant's links: start, daily, end, `/survey` and the end-survey
  reminder. It stays the same after unsubscribing and subscribing again and
  across bot restarts.
* The number replaces `{participant}` in a stem; stems without the
  placeholder get the number appended at the end. Keep the quotes around
  stems in YAML.
* The `urls` section keeps its structure: one stem per condition (and per end
  link), so different surveys and conditions still have different stems.
* When every number of the range is taken, new subscriptions are rejected
  with the `subscribe_max_participants` text. Participants who already have a
  number can still re-subscribe.
* Participants who subscribed before the option was enabled get their number
  with their next link.
* With `useParticipantNumbers: false` (the default) the links are used exactly
  as written, as before. Configs without these keys keep working unchanged.

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
