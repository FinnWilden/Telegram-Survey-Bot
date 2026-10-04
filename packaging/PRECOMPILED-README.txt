Telegram Survey Bot
===================

This archive contains a precompiled Telegram Survey Bot for this operating
system. Python does not need to be installed.

First-time setup
----------------

1. Keep the whole extracted folder together; do not move the executable out
   of its folder.
2. Open config/config.json in a text editor and replace
   "your_api_token_here" with your Telegram bot token.
3. Complete the study settings in config/config.json. See the project wiki
   for configuration guidance:
   https://github.com/FinnWilden/Telegram-Survey-Bot/wiki/Configure
4. Keep the db and log folders. The bot stores its database and logs there.
   Back up the db folder regularly; it contains participant state.
5. Start the executable from the extracted Telegram-Survey-Bot folder.

Starting the bot
----------------

Windows:
  Double-click Survey-Bot.exe, or run it from PowerShell/Command Prompt.

Linux:
  Open a terminal in the extracted Telegram-Survey-Bot folder and run:
  chmod +x Survey-Bot
  ./Survey-Bot

macOS:
  Open a terminal in the extracted Telegram-Survey-Bot folder and run:
  ./Survey-Bot

The macOS build is not code-signed or notarized. macOS may warn or block it.
Do not bypass security warnings unless you trust the source of the download.

Keep this folder in a stable location while the bot runs. Stop it with
Ctrl+C when running in a terminal. Do not share your config file or database:
the configuration contains your bot token and the database contains study
participant data.
