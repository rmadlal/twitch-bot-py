from handlers import TwitchIRCHandler, TwitchAPIHandler, JokeHandler
import sys
import urllib.request
import threading
import json

# constants
BOT_USERNAME = 'uncleronnybot'
MY_USERNAME = 'uncleronny'


def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()

    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t


def print_viewers():
    with urllib.request.urlopen('http://tmi.twitch.tv/group/user/' + MY_USERNAME + '/chatters') as response:
        data = json.load(response)
        print(data['chatters']['viewers'])


def main():
    set_interval(print_viewers(), 2*60)

    irc_client = TwitchIRCHandler()
    twitch_api_handler = TwitchAPIHandler()
    joke_handler = JokeHandler()

    commands = {
        'PogChamp': lambda: irc_client.say('ChampPog'),
        'ChampPog': lambda: irc_client.say('PogChamp'),
        '!help': lambda: irc_client.action('Commands: ' + ' '.join(list(commands.keys())[3:])),
        '!highlight': lambda: twitch_api_handler.command_highlight(irc_client),
        '!pyramid': lambda: irc_client.action('Usage: !pyramid [<size>] <text>'),
        '!joke': lambda: irc_client.say(joke_handler.random_joke())
    }

    def other_command(msg):
        if msg.startswith('!pyramid '):
            irc_client.command_pyramid(msg)
        elif msg.startswith('!') and username != MY_USERNAME:
            irc_client.action(commands['!help']())
        elif username == MY_USERNAME:
            if msg.startswith('!game '):
                twitch_api_handler.update_game(msg[len('!game '):])
            elif msg.startswith('!title '):
                twitch_api_handler.update_title(msg[len('!title '):])
            elif msg == '!goaway':
                irc_client.action('Bye')
                irc_client.disconnect()
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
