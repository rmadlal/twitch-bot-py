import os
import random
import re
import requests
import socket
import sys
from dataclasses import dataclass
from enum import Enum, auto
from traceback import print_exc
from typing import Any, Callable, Final, Iterable, Optional, Union

BOT_USERNAME: Final = os.getenv('BOT_CHANNEL_NAME')
MY_USERNAME: Final = os.getenv('CHANNEL_NAME')

# IRC
HOST: Final = 'irc.chat.twitch.tv'
PORT: Final = 6667
PASS: Final = os.getenv('CHAT_OAUTH')

# Twitch API
USER_ID: Final = os.getenv('USER_ID')
API_CLIENT_ID: Final = os.getenv('API_CLIENT_ID')
API_OAUTH: Final = os.getenv('API_OAUTH')
API_AUTH_HEADERS: Final = {'Authorization': f'Bearer {API_OAUTH}', 'Client-Id': API_CLIENT_ID}
API_URL_BASE: Final = 'https://api.twitch.tv/helix'


@dataclass
class ChatMessage:
    user: str
    message: str
    user_type: Optional[str]

    @property
    def is_mod(self):
        return self.user_type == 'mod' or self.user == MY_USERNAME


class TwitchIRCHandler:

    def __init__(self):
        self._sock = socket.socket()
        self._re_end = re.compile(r'^:\w+\.tmi\.twitch\.tv 366 \w+ #(?P<channel_name>\w+) :End of /NAMES list$')
        self._re_message = re.compile(r'^@\S*user-type=(?P<user_type>\w+)?\S* :(?P<user>\w+)!\2@\2\.tmi\.twitch\.tv '
                                      rf'PRIVMSG #{MY_USERNAME} :(?P<message>.+)$')

    def connect(self):
        self._sock.connect((HOST, PORT))
        self._sock.send(bytes(f'PASS oauth:{PASS}\r\n', 'utf-8'))
        self._sock.send(bytes(f'NICK {BOT_USERNAME}\r\n', 'utf-8'))
        self._sock.send(bytes('CAP REQ :twitch.tv/tags\r\n', 'utf-8'))  # request tags for user-type
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


class CommandError(Exception):
    pass


class CommandArgsFormat(Enum):
    IGNORE = auto()
    AS_IS = auto()
    SPLIT = auto()


class Command:

    command_handler: Optional['CommandHandler'] = None

    def __init__(self, cmd: Callable, mod_only: bool, args_format: Union[Callable, CommandArgsFormat]):
        self.__cmd = cmd
        self.__mod_only = mod_only
        self.__args_format = args_format

    def __call__(self, rest: str = ''):
        args = tuple()
        if self.__args_format == CommandArgsFormat.IGNORE:
            pass
        if self.__args_format == CommandArgsFormat.AS_IS:
            args = (rest,) if rest else tuple()
        elif self.__args_format == CommandArgsFormat.SPLIT:
            args = tuple(rest.split())
        elif callable(self.__args_format):
            args = self.__args_format(rest)

        return self.__cmd(type(self).command_handler, *args)

    @property
    def is_mod_only(self) -> bool:
        return self.__mod_only


class CommandHandler:

    def __init__(self, _irc_client: TwitchIRCHandler):
        self._irc_client = _irc_client
        self._emote_cache = []
        self._re_cmd_call: Final = re.compile(r'!(?P<cmd>\w+)( +(?P<rest>\S.*))?')
        self._cmd_list: Final = [f'!{cmd_name} (mod only)' if cmd.is_mod_only else f'!{cmd_name}'
                                 for cmd_name in dir(self) if isinstance(cmd := getattr(self, cmd_name), Command)]
        Command.command_handler = self

    def __call__(self, message: ChatMessage):
        if message.user == BOT_USERNAME or not (m := self._re_cmd_call.match(message.message)):
            return

        cmd, rest = m['cmd'], m['rest'] or ''
        cmd_method = getattr(self, cmd, None)
        if not (cmd_method or isinstance(cmd_method, Command)):
            # Unknown command, show help instead
            self.help()
            return

        try:
            if not cmd_method.is_mod_only or message.is_mod:
                cmd_method(rest)
        except CommandError as e:
            self._irc_client.action(str(e))

    # decorator
    def command(cmd_method=None, *, mod_only: bool = False, args_format: Union[Callable, CommandArgsFormat] = CommandArgsFormat.IGNORE):
        if cmd_method:
            # decorator without arguments
            return Command(cmd_method, mod_only, args_format)
        else:
            def wrapper(cmd_method):
                return Command(cmd_method, mod_only, args_format)
            return wrapper

    def _parse_pyramid_args(args: str) -> tuple[str, int]:
        # !pyramid <size: number from 1 to 7> <text: string>
        # or !pyramid <text: string> (in this case, the pyramid will be of size 3)
        args = args.split()
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

    @command
    def help(self):
        self._irc_client.action('Commands: ' + ', '.join(self._cmd_list))

    @command
    def emote(self):
        def get_emotes(url: str, get_from_json: Callable[[Any], list[str]]) -> list[str]:
            try:
                with requests.get(url) as resp:
                    resp.raise_for_status()
                    return get_from_json(resp.json())
            except requests.HTTPError:
                print_exc()
                return []

        if not self._emote_cache:
            self._emote_cache = \
                get_emotes(f'http://api.frankerfacez.com/v1/room/{MY_USERNAME}',
                           lambda data: [emote['name'] for emote in data['sets'][str(data['room']['set'])]['emoticons']]) + \
                get_emotes(f'https://api.betterttv.net/3/cached/users/twitch/{USER_ID}',
                           lambda data: [emote['code'] for emote in data['sharedEmotes']])

        if self._emote_cache:
            self._irc_client.say(random.choice(self._emote_cache))

    @command(args_format=_parse_pyramid_args)
    def pyramid(self, text: str, size: int):
        for i in range(1, size * 2):
            self._irc_client.say(' '.join([text] * (i if i <= size else 2 * size - i)))

    @command(mod_only=True, args_format=CommandArgsFormat.AS_IS)
    def title(self, title: str):
        try:
            with requests.patch(f'{API_URL_BASE}/channels',
                                params={'broadcaster_id': USER_ID},
                                headers=API_AUTH_HEADERS | {'Content-Type': 'application/json'},
                                json={'title': title}) as resp:
                resp.raise_for_status()
        except requests.HTTPError:
            print_exc()
            raise CommandError('Failed to change title')

    @command(mod_only=True, args_format=CommandArgsFormat.AS_IS)
    def game(self, game: str):
        # lookup game ID first
        try:
            with requests.get(f'{API_URL_BASE}/games',
                              params={'name': game},
                              headers=API_AUTH_HEADERS) as resp:
                resp.raise_for_status()
                games = resp.json()['data']

            if not games:
                raise CommandError('Game not found')

            with requests.patch(f'{API_URL_BASE}/channels',
                                params={'broadcaster_id': USER_ID},
                                headers=API_AUTH_HEADERS | {'Content-Type': 'application/json'},
                                json={'game_id': games[0]['id']}) as resp:
                resp.raise_for_status()
        except requests.HTTPError:
            print_exc()
            raise CommandError('Failed to change game')
