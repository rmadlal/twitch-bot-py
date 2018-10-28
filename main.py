import requests

from handlers import MY_USERNAME, BOT_USERNAME, TwitchIRCHandler, CommandHandler
from util import repeat_every


class Bot(object):

    def __init__(self):
        self._irc_handler = TwitchIRCHandler()
        self._command_handler = CommandHandler(self._irc_handler)
        self._viewers = set()

    @repeat_every(60)
    def _fetch_viewers(self):
        try:
            with requests.get(f'http://tmi.twitch.tv/group/user/{MY_USERNAME}/chatters') as response:
                response.raise_for_status()
                data = response.json()
            new_viewers = set((viewer for viewer in data['chatters']['viewers']
                               if viewer not in (MY_USERNAME, BOT_USERNAME)))
            if new_viewers != self._viewers:
                self._viewers = new_viewers
                print('> Viewers: ' + ', '.join(new_viewers))
        except requests.RequestException:
            pass

    @repeat_every(60 * 10)
    def _send_random_emotes(self):
        try:
            self._command_handler.cmd_emote()
        except IOError:
            pass

    def _cancel_repeating_tasks(self):
        self._fetch_viewers.cancel()
        self._send_random_emotes.cancel()

    def main_loop(self):
        if not self._irc_handler.connect():
            return

        # Repeating tasks
        self._fetch_viewers()
        self._send_random_emotes()

        while True:
            messages = self._irc_handler.get_messages()
            if messages is None:
                self._cancel_repeating_tasks()
                return
            for username, message in messages:
                print(f'{username}: {message}')
                if username == BOT_USERNAME:
                    continue
                self._command_handler(message)


def main():
    for _ in range(5):  # Stop after 5 connection failures
        bot = Bot()
        bot.main_loop()


if __name__ == '__main__':
    main()
