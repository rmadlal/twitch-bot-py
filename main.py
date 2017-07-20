import sys
from handlers import TwitchIRCHandler, TwitchAPIHandler, JokeHandler

# constants
BOT_USERNAME = 'uncleronnybot'
MY_USERNAME = 'uncleronny'

PUBLIC_COMMANDS = [
    '!help',
    '!highlight',
    '!pyramid',
    '!joke'
]
#


def main():
    twitch_irc = TwitchIRCHandler()
    twitch_api_handler = TwitchAPIHandler()
    joke_handler = JokeHandler()

    # default case for 'switch' statement later
    def default(msg):
        if msg.startswith('!pyramid '):
            twitch_irc.command_pyramid(msg)
        elif msg.startswith('!') and username != MY_USERNAME:
            twitch_irc.action('Commands: ' + ' '.join(PUBLIC_COMMANDS[1:]))
        elif username == MY_USERNAME:
            if msg.startswith('!game '):
                twitch_api_handler.update_game(msg[len('!game '):])
            elif msg.startswith('!title '):
                twitch_api_handler.update_title(msg[len('!title '):])
            elif msg == '!goaway':
                twitch_irc.action('Bye')
                twitch_irc.disconnect()
                sys.exit(0)

    if not twitch_irc.connect():
        return
    twitch_irc.say('Hi!')

    while True:
        received = twitch_irc.receive()
        if not received:
            return
        for line in received:
            if 'PRIVMSG' not in line:
                if 'PING' in line:
                    twitch_irc.pong()
                continue
            username, message = TwitchIRCHandler.extract_message(line)
            print(username + ': ' + message)
            if username == BOT_USERNAME:
                continue
            # switch(message)
            {
                'PogChamp': lambda: twitch_irc.say('ChampPog'),
                'ChampPog': lambda: twitch_irc.say('PogChamp'),
                '!help': lambda: twitch_irc.action('Commands: ' + ' '.join(PUBLIC_COMMANDS[1:])),
                '!highlight': lambda: twitch_api_handler.command_highlight(),
                '!pyramid': lambda: twitch_irc.action('Usage: !pyramid [<size>] <text>'),
                '!joke': lambda: twitch_irc.say(joke_handler.random_joke())
            }.get(message, lambda: default(message))()


if __name__ == '__main__':
    main()
