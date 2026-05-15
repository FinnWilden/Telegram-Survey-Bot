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
* Optional timezone support
* Automatic survey reminder scheduling
* Automatic deletion of expired survey links
* SQLite-based lightweight persistence
* Logging and emergency restart handling
* Fully configurable through a single JSON configuration file

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

Tests are automatically executed on every push and pull request using multiple Python versions.

The current test suite includes:

* Time and scheduling utilities
* Database handling
* Configuration parsing and validation
* Scheduling logic
* Telegram bot handlers using mocks
* Keyboard generation

This helps detect regressions early and improves long-term maintainability and reliability.

---

# Installation

See the Wiki for installation instructions:

➡ https://github.com/FinnWilden/Telegram-Survey-Bot/wiki

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
