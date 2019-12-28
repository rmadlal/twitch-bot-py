import sys
import time
from handlers import BOT_USERNAME, TwitchIRCHandler, CommandHandler
from util import repeat_every, swallow_exceptions


class Bot:

    def __init__(self):
        self._irc_handler = TwitchIRCHandler()
        self._command_handler = CommandHandler(self._irc_handler)
        self._cancel_send_random_emotes = None

    def __enter__(self):
        self._irc_handler.connect()
        self._cancel_send_random_emotes = self._send_random_emotes()
        return self

    def __exit__(self, *args):
        if self._cancel_send_random_emotes:
            self._cancel_send_random_emotes()
        self._irc_handler.disconnect()

    @repeat_every(10 * 60)
    def _send_random_emotes(self):
        with swallow_exceptions():
            self._command_handler.cmd_emote()

    def main_loop(self):
        while True:
            for user, message in self._irc_handler.get_messages():
                if user == BOT_USERNAME:
                    continue
                self._command_handler(message)


def main():
    while True:
        try:
            with Bot() as bot:
                bot.main_loop()
        except Exception as e:
            print(repr(e), file=sys.stderr)
            time.sleep(10)


if __name__ == '__main__':
    main()
