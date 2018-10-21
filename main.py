import threading

import requests

from handlers import MY_USERNAME, BOT_USERNAME, TwitchIRCHandler, CommandHandler


def fetch_viewers(interval):
    stopped = threading.Event()

    def loop():
        viewers = set()
        while not stopped.wait(interval):
            with requests.get(f'http://tmi.twitch.tv/group/user/{MY_USERNAME}/chatters') as response:
                try:
                    response.raise_for_status()
                    data = response.json()
                    new_viewers = set((viewer for viewer in data['chatters']['viewers']
                                       if viewer not in (MY_USERNAME, BOT_USERNAME)))
                    if new_viewers != viewers:
                        viewers = new_viewers
                        print('> Viewers: ' + ', '.join(viewers))
                except requests.RequestException:
                    continue

    threading.Thread(target=loop).start()
    return stopped.set


def send_random_emotes(irc_client, interval):
    stopped = threading.Event()

    def loop():
        while not stopped.wait(interval):
            irc_client.random_emote()

    threading.Thread(target=loop).start()
    return stopped.set


def main():
    irc_client = TwitchIRCHandler()
    command_handler = CommandHandler(irc_client)

    cancel_fetch_viewers = fetch_viewers(60)
    cancel_send_random_emotes = send_random_emotes(irc_client, 60*10)

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
