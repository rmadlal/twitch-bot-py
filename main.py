import sys
import threading

import requests

from handlers import MY_USERNAME, BOT_USERNAME, TwitchIRCHandler, TwitchAPIHandler, JokeHandler


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
    twitch_api_handler = TwitchAPIHandler()
    joke_handler = JokeHandler()

    cancel_fetch_viewers = fetch_viewers(60)
    cancel_send_random_emotes = send_random_emotes(irc_client, 60*10)

    def cancel_repeating_threads():
        cancel_fetch_viewers()
        cancel_send_random_emotes()

    commands = {
        'PogChamp': lambda: irc_client.say('ChampPog'),
        'ChampPog': lambda: irc_client.say('PogChamp'),
        '!help': lambda: irc_client.action(f"Commands: {' '.join(list(commands.keys())[3:])}"),
        '!highlight': lambda: irc_client.action(twitch_api_handler.highlight()),
        '!np': lambda: irc_client.now_playing(),
        '!pyramid': lambda: irc_client.action('Usage: !pyramid [<size>] <text>'),
        '!joke': lambda: irc_client.say(joke_handler.random_joke()),
        '!emote': lambda: irc_client.random_emote(),
        '!clip': lambda: irc_client.action(twitch_api_handler.random_clip())
    }

    def other_command(msg):
        # Commands with arguments (e.g !pyramid) and owner-only commands are handled here
        if msg.startswith('!pyramid '):
            irc_client.pyramid(msg)
            return
        if username != MY_USERNAME:
            if msg.startswith('!'):
                commands['!help']()
            return
        # Channel owner only
        if msg.startswith('!game '):
            twitch_api_handler.update_game(msg[len('!game '):])
        elif msg.startswith('!title '):
            twitch_api_handler.update_title(msg[len('!title '):])
        elif msg == '!goaway':
            irc_client.action('Bye')
            irc_client.disconnect()
            cancel_repeating_threads()
            sys.exit(0)

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
            commands.get(message, lambda: other_command(message))()


if __name__ == '__main__':
    while True:
        main()
