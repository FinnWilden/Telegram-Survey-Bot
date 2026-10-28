Telegram Survey Bot
===================

This archive contains a precompiled Telegram Survey Bot for this operating
system. Python does not need to be installed. The editable config/config.yml
is a separate file next to the executable; it is not embedded in the EXE.

First-time setup
----------------

1. Keep the whole extracted folder together; do not move the executable out
   of its folder.
2. Edit config/config.yml, or prepare a different YAML/JSON config file and
   pass its path when starting the bot. The selected file must contain your
   bot token and study settings; the packaged file has only a placeholder
   token and example URLs. See the project wiki for configuration guidance:
   https://github.com/FinnWilden/Telegram-Survey-Bot/wiki/Configure
4. Keep the db and log folders. The bot stores its database and logs there.
   Back up the db folder regularly; it contains participant state.
5. Start the executable from the extracted Telegram-Survey-Bot folder.

Starting the bot
----------------

Windows:
  Double-click Survey-Bot.exe, or run it from PowerShell/Command Prompt.
  To use a different configuration file, pass its path as the first argument:
  .\Survey-Bot.exe "C:\path\to\config.yml"

Linux:
  Open a terminal in the extracted Telegram-Survey-Bot folder and run:
  chmod +x Survey-Bot
  ./Survey-Bot
  To use a different configuration file:
  ./Survey-Bot "/path/to/config.yml"

macOS:
  Open a terminal in the extracted Telegram-Survey-Bot folder and run:
  ./Survey-Bot
  To use a different configuration file:
  ./Survey-Bot "/path/to/config.yml"

If no configuration path is supplied, the bot reads config/config.yml from
the extracted folder beside the executable, regardless of the current
working directory. This is a normal, editable file, not a copy embedded in
the executable. Relative paths passed as arguments are resolved from the
current working directory. Start the bot from the extracted folder so its
database and logs are also stored there.

The macOS build is not code-signed or notarized. macOS may warn or block it.
Do not bypass security warnings unless you trust the source of the download.

Keep this folder in a stable location while the bot runs. Stop it with
Ctrl+C when running in a terminal. Do not share your config file or database:
the configuration contains your bot token and the database contains study
participant data.
