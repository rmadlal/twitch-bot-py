import os
import sys
import time
from contextlib import suppress
from traceback import print_exc
from typing import Final

try:
    from dotenv import load_dotenv
    load_dotenv()
except (ImportError, IOError):
    pass

required_env = {'BOT_CHANNEL_NAME', 'CHANNEL_NAME', 'USER_ID', 'CHAT_OAUTH', 'API_CLIENT_ID', 'API_OAUTH'}
if missing_env := required_env - set(os.environ):
    sys.exit('Missing required environment variables ' + ', '.join(missing_env))

from handlers import TwitchIRCHandler, CommandHandler
from util import repeat_every

EMOTE_FREQ_MINUTES: Final = float(os.getenv('EMOTE_FREQ_MINUTES', '0'))


class Bot:

    def __init__(self):
        self._irc_handler = TwitchIRCHandler()
        self._command_handler = CommandHandler(self._irc_handler)
        self._cancel_send_random_emotes = None

    def __enter__(self):
        self._irc_handler.connect()
        if EMOTE_FREQ_MINUTES:
            self._cancel_send_random_emotes = self._send_random_emotes()
        return self

    def __exit__(self, *_):
        if self._cancel_send_random_emotes:
            self._cancel_send_random_emotes()
        self._irc_handler.disconnect()

    @repeat_every(EMOTE_FREQ_MINUTES * 60)
    def _send_random_emotes(self):
        with suppress(Exception):
            self._command_handler.emote()

    def main_loop(self):
        while True:
            for message in self._irc_handler.get_messages():
                self._command_handler(message)


def main():
    while True:
        try:
            with Bot() as bot:
                bot.main_loop()
        except Exception:
            print_exc()
            time.sleep(1)


if __name__ == '__main__':
    main()
