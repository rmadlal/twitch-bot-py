from handlers import TwitchIRCHandler, TwitchAPIHandler, JokeHandler
import sys
import urllib.request
import threading
import json

BOT_USERNAME = 'uncleronnybot'
MY_USERNAME = 'uncleronny'


def fetch_viewers(interval):
    stopped = threading.Event()

    def loop():
        viewers = []
        while not stopped.wait(interval):
            with urllib.request.urlopen('http://tmi.twitch.tv/group/user/' + MY_USERNAME + '/chatters') as response:
                data = json.load(response)
            new_viewers = data['chatters']['viewers']
            if new_viewers != viewers:
                viewers = new_viewers
                print('> Viewers: ' + ', '.join(viewers))

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
    cancel_fetch_viewers = fetch_viewers(60)

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
                cancel_fetch_viewers()
                sys.exit(0)

    if not irc_client.connect():
        return
    irc_client.say('Hi!')

    while True:
        messages = irc_client.get_messages()
        if messages is None:
            return
        for username, message in messages:
            print(username + ': ' + message)
            if username == BOT_USERNAME:
                continue
            commands.get(message, lambda: other_command(message))()


if __name__ == '__main__':
    main()
