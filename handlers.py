import os
import random
import re
import requests
import socket
import sys
from collections import namedtuple
from typing import Callable, Final, Iterable, Tuple
from twitch import TwitchClient
from util import pop_random_item

ChatMessage = namedtuple('ChatMessage', ['user', 'message'])

BOT_USERNAME: Final = os.getenv('BOT_CHANNEL_NAME')
MY_USERNAME: Final = os.getenv('CHANNEL_NAME')

# IRC
HOST: Final = 'irc.chat.twitch.tv'
PORT: Final = 6667
PASS: Final = os.getenv('CHAT_OAUTH')

# Twitch
CHANNEL_ID: Final = os.getenv('CHANNEL_ID')
CLIENT_ID: Final = os.getenv('CLIENT_ID')
API_TOKEN: Final = os.getenv('API_OAUTH')


class TwitchIRCHandler:

    def __init__(self):
        self._sock = socket.socket()
        self._ffz_emote_cache = []
        self._re_end = re.compile(r'^:\w+\.tmi\.twitch\.tv 366 \w+ #(?P<channel_name>\w+) :End of /NAMES list$')
        self._re_message = re.compile(r'^:(?P<user>\w+)!\1@\1\.tmi\.twitch\.tv '
                                      rf'PRIVMSG #{MY_USERNAME} :(?P<message>.+)$')

    def connect(self):
        self._sock.connect((HOST, PORT))
        self._sock.send(bytes(f'PASS {PASS}\r\n', 'utf-8'))
        self._sock.send(bytes(f'NICK {BOT_USERNAME}\r\n', 'utf-8'))
        self._sock.send(bytes(f'JOIN #{MY_USERNAME}\r\n', 'utf-8'))
        while received := self._sock.recv(1024).decode():
            for line in received.splitlines():
                if end_msg := self._re_end.match(line):
                    print(f"Connected to {end_msg['channel_name']}'s Twitch chat.")
                    return True
        raise Exception('Failed to connect')

    def disconnect(self):
        self._sock.close()

    def _process_lines(self, lines) -> Iterable[ChatMessage]:
        for line in lines:
            if line == 'PING :tmi.twitch.tv':
                self._sock.send(bytes(line.replace('PING', 'PONG', 1) + '\r\n', 'utf-8'))
                continue
            if msg := self._re_message.match(line):
                yield ChatMessage(**msg.groupdict())

    def get_messages(self) -> Iterable[ChatMessage]:
        if not (received := self._sock.recv(1024).decode()):
            raise Exception('Connection reset')
        yield from self._process_lines(received.splitlines())

    def say(self, msg: str):
        msg = msg.replace('\n', ' ')
        self._sock.send(bytes(f'PRIVMSG #{MY_USERNAME} :{msg}\r\n', 'utf-8'))

    def action(self, msg: str):
        self.say(msg if msg.startswith('/me ') else f'/me {msg}')


class TwitchAPIHandler(TwitchClient):

    def __init__(self):
        super().__init__(CLIENT_ID, API_TOKEN)
        self._clip_cache = []

    def update_game(self, game: str):
        self.channels.update(CHANNEL_ID, game=game)

    def update_title(self, title: str):
        self.channels.update(CHANNEL_ID, status=title)

    def random_clip(self) -> str:
        if not self._clip_cache:
            self._clip_cache = self.clips.get_top(channel=MY_USERNAME, limit=50, period='all')
        clip = pop_random_item(self._clip_cache)
        return clip['url']


class CommandError(ValueError):
    pass


class CommandHandler:

    def __init__(self, _irc_client: TwitchIRCHandler):
        self.should_exit = False
        self._irc_client = _irc_client
        self._twitch_api_handler = TwitchAPIHandler()
        self._ffz_emote_cache = []
        self._re_cmd_call: Final = re.compile(r'!(?P<cmd>\w+)( +(?P<args>\S.*))?')
        self._re_cmd_method: Final = re.compile(r'cmd_(\w+)')
        self._champ: Final = 'PogChamp', 'ChampPog'
        # Commands that take the whole rest of the text as one str argument
        self._str_arg_commands: Final = self.cmd_game, self.cmd_title, self.cmd_dab
        self._private_commands: Final = self.cmd_exit,

    def __call__(self, user: str, message: str):
        if message in self._champ:
            self._irc_client.say(self._champ[1 - self._champ.index(message)])
            return
        if not (m := self._re_cmd_call.match(message)):
            return
        cmd, args = m['cmd'], m['args'] or ''
        try:
            method = getattr(self, 'cmd_' + cmd)
            if method in self._private_commands and user != MY_USERNAME:
                raise AttributeError()
            method(*self._parse_args_for_method(method, args))
        except AttributeError:
            # Unknown command, show help instead
            self.cmd_help()
        except TypeError:
            # Invalid number of arguments for command
            pass
        except CommandError as e:
            # Invalid arguments for command
            self._irc_client.action(str(e))
        except Exception as e:
            print(f'Unexpected error: {e!r}', file=sys.stderr)

    @staticmethod
    def _parse_pyramid_args(*args: str) -> Tuple[str, int]:
        # !pyramid <size: number from 1 to 7> <text: string>
        # or !pyramid <text: string> (in this case, the pyramid will be of size 3)
        if not args:
            raise CommandError('Usage: !pyramid [<size>] <text>')
        size = 3
        if len(args) > 1 and args[0].isnumeric():
            size = int(args[0])
            if size not in range(1, 8):
                raise CommandError('Pyramid size must be between 1 and 7.')
            args = args[1:]
        text = ' '.join(args)
        return text, size

    def _cmd_method_to_str(self, method_name: str) -> str:
        # Example: 'cmd_help' becomes '!help'
        return self._re_cmd_method.sub(r'!\1', method_name)

    def _parse_args_for_method(self, method: Callable, args: str) -> Tuple:
        if method in self._str_arg_commands:
            if not args:
                method_str = self._cmd_method_to_str(method.__name__)
                raise CommandError(f'Usage: {method_str} <text>')
            return args,
        args = tuple(args.split())
        if method == self.cmd_pyramid:
            return self._parse_pyramid_args(*args)
        return args

    def cmd_help(self):
        cmd_list = [self._cmd_method_to_str(m) for m in dir(self)
                    if m.startswith('cmd_') and getattr(self, m) not in self._private_commands]
        self._irc_client.action(f"Commands: {', '.join(cmd_list)}")

    def cmd_game(self, game: str):
        self._twitch_api_handler.update_game(game)

    def cmd_title(self, title: str):
        self._twitch_api_handler.update_title(title)

    def cmd_emote(self):
        if not self._ffz_emote_cache:
            with requests.get(f'http://api.frankerfacez.com/v1/room/{MY_USERNAME}') as response:
                response.raise_for_status()
                data = response.json()
            set_num = data['room']['set']
            emoticons = data['sets'][str(set_num)]['emoticons']
            self._ffz_emote_cache = [emote['name'] for emote in emoticons]
        self._irc_client.say(random.choice(self._ffz_emote_cache))

    def cmd_clip(self):
        clip = self._twitch_api_handler.random_clip()
        self._irc_client.say(clip)

    def cmd_pyramid(self, text: str, size: int):
        for i in range(1, size * 2):
            self._irc_client.say(' '.join([text] * (i if i <= size else 2 * size - i)))

    def cmd_dab(self, who: str):
        del who
        self._irc_client.say('No.')

    def cmd_exit(self):
        self.should_exit = True
