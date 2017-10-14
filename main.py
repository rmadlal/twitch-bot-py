from handlers import TwitchIRCHandler, TwitchAPIHandler, JokeHandler
import sys
import requests
import threading
import random

BOT_USERNAME = 'uncleronnybot'
MY_USERNAME = 'uncleronny'


def fetch_viewers(interval):
    stopped = threading.Event()

    def loop():
        viewers = []
        while not stopped.wait(interval):
            with requests.get('http://tmi.twitch.tv/group/user/' + MY_USERNAME + '/chatters') as response:
                data = response.json()
            new_viewers = [viewer for viewer in data['chatters']['viewers'] if viewer not in (MY_USERNAME, BOT_USERNAME)]
            if new_viewers != viewers:
                viewers = new_viewers
                print('> Viewers: ' + ', '.join(viewers))

    threading.Thread(target=loop).start()
    return stopped.set


def send_random_emote(irc_client, interval):
    stopped = threading.Event()

    def loop():
        with requests.get('http://api.frankerfacez.com/v1/room/' + MY_USERNAME) as response:
            data = response.json()
        set = data['room']['set']
        emoticons = data['sets'][str(set)]['emoticons']
        emote_names = [emote['name'] for emote in emoticons]
        while not stopped.wait(interval):
            irc_client.say(random.choice(emote_names))

    threading.Thread(target=loop).start()
    return stopped.set


def now_playing(irc_client):
    if sys.argv[1:] and sys.argv[1] == '-m':
        with open(r'C:\Users\RonMad\Documents\foobar2000_now_playing\now_playing.txt',
                  encoding='utf-8-sig') as np_file:
            irc_client.action('Now playing: ' + np_file.readline())
    else:
        irc_client.action('N/A')


def main():

    def cancel_repeating_threads():
        cancel_fetch_viewers()
        cancel_send_random_emote()

    irc_client = TwitchIRCHandler()
    twitch_api_handler = TwitchAPIHandler()
    joke_handler = JokeHandler()

    commands = {
        'PogChamp': lambda: irc_client.say('ChampPog'),
        'ChampPog': lambda: irc_client.say('PogChamp'),
        '!help': lambda: irc_client.action('Commands: ' + ' '.join(list(commands.keys())[3:])),
        '!highlight': lambda: twitch_api_handler.command_highlight(irc_client),
        '!np': lambda: now_playing(irc_client),
        '!pyramid': lambda: irc_client.action('Usage: !pyramid [<size>] <text>'),
        '!joke': lambda: irc_client.say(joke_handler.random_joke())
    }

    def other_command(msg):
        if msg.startswith('!pyramid '):
            irc_client.command_pyramid(msg)
        elif msg.startswith('!') and username != MY_USERNAME:
            commands['!help']()
        elif username == MY_USERNAME:
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
        sys.exit(1)

    cancel_fetch_viewers = fetch_viewers(60)
    cancel_send_random_emote = send_random_emote(irc_client, 60*5)

    irc_client.say('Hi!')
    while True:
        messages = irc_client.get_messages()
        if messages is None:
            cancel_repeating_threads()
            sys.exit(1)
        for username, message in messages:
            print(username + ': ' + message)
            if username == BOT_USERNAME:
                continue
            commands.get(message, lambda: other_command(message))()


if __name__ == '__main__':
    main()
