import requests

from handlers import MY_USERNAME, BOT_USERNAME, TwitchIRCHandler, CommandHandler
from util import repeat_every

viewers = set()  # Needs to be global to work with the `repeat` decorator


@repeat_every(60)
def fetch_viewers():
    global viewers
    try:
        with requests.get(f'http://tmi.twitch.tv/group/user/{MY_USERNAME}/chatters') as response:
            response.raise_for_status()
            data = response.json()
        new_viewers = set((viewer for viewer in data['chatters']['viewers']
                           if viewer not in (MY_USERNAME, BOT_USERNAME)))
        if new_viewers != viewers:
            viewers = new_viewers
            print('> Viewers: ' + ', '.join(viewers))
    except requests.RequestException:
        pass


@repeat_every(60 * 10)
def send_random_emotes(command_handler: CommandHandler):
    try:
        command_handler.cmd_emote()
    except IOError:
        pass


def main():
    irc_client = TwitchIRCHandler()
    command_handler = CommandHandler(irc_client)

    cancel_fetch_viewers = fetch_viewers()
    cancel_send_random_emotes = send_random_emotes(command_handler)

    def cancel_repeating_threads():
        cancel_fetch_viewers()
        cancel_send_random_emotes()

    if not irc_client.connect():
        cancel_repeating_threads()
        return

    while True:
        messages = irc_client.get_messages()
        if messages is None:
            cancel_repeating_threads()
            return
        for username, message in messages:
            print(f'{username}: {message}')
            if username == BOT_USERNAME:
                continue
            command_handler(message)


if __name__ == '__main__':
    while True:
        main()
