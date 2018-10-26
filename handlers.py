import json
import random
import re
import socket
import subprocess
from datetime import datetime
from typing import Tuple

import pyperclip
import requests
from praw import Reddit
from twitch import TwitchClient

with open('botconfig.json') as config_file:
    config = json.load(config_file)

BOT_USERNAME = config['botChannelName']
MY_USERNAME = config['myChannelName']

# IRC
HOST = 'irc.chat.twitch.tv'
PORT = 6667
PASS = config['botChatOAuth']

# reddit
REDDIT_CLIENT_ID = config['redditClientID']
SECRET = config['redditSecret']
USERNAME = config['redditUsername']
PASSWORD = config['redditPassword']

# Twitch
CHANNEL_ID = config['myChannelID']
CLIENT_ID = config['clientID']
API_TOKEN = config['botAPIOAuth']


def pop_random_item(lst):
    return lst.pop(random.randrange(len(lst)))


class TwitchIRCHandler(object):

    def __init__(self):
        self._sock = socket.socket()
        self._ffz_emote_cache = []
        self._re_end = re.compile(r'^:\w+\.tmi\.twitch\.tv 366 \w+ #(?P<channel_name>\w+) :End of /NAMES list$')
        self._re_message = re.compile(r'^:(?P<user>\w+)!\1@\1\.tmi\.twitch\.tv '
                                      rf'PRIVMSG #{MY_USERNAME} :(?P<message>.+)$')

    def connect(self):
        try:
            self._sock.connect((HOST, PORT))
            self._sock.send(bytes(f'PASS {PASS}\r\n', 'utf-8'))
            self._sock.send(bytes(f'NICK {BOT_USERNAME}\r\n', 'utf-8'))
            self._sock.send(bytes(f'JOIN #{MY_USERNAME}\r\n', 'utf-8'))
            while True:
                received = self._sock.recv(1024).decode()
                if not received:
                    print('Connection error')
                    return False

                for line in received.splitlines():
                    end_msg = self._re_end.match(line)
                    if end_msg:
                        print(f"Connected to {end_msg['channel_name']}'s Twitch chat.")
                        return True
        except socket.error as err:
            print(f'Connection error: {err.strerror}')
            return False

    def disconnect(self):
        self._sock.close()

    def get_messages(self):
        try:
            received = self._sock.recv(1024).decode()
            if not received:
                print('Connection reset')
                return
            lines = received.splitlines()

            # Ping-pong
            pings = [line for line in lines if line == 'PING :tmi.twitch.tv']
            for ping in pings:
                self._sock.send(bytes(ping.replace('PING', 'PONG', 1) + '\r\n', 'utf-8'))

            return [(m['user'], m['message']) for m in map(self._re_message.match, lines) if m]
        except socket.error as err:
            print(f'Connection reset: {err.strerror}')
            return

    def say(self, msg: str):
        try:
            msg = msg.replace('\n', ' ')
            self._sock.send(bytes(f'PRIVMSG #{MY_USERNAME} :{msg}\r\n', 'utf-8'))
            print(f'> {msg}')
        except socket.error as err:
            print(f'Connection reset: {err.strerror}')

    def action(self, msg: str):
        self.say(msg if msg.startswith('/me ') else f'/me {msg}')


class TwitchAPIHandler(TwitchClient):

    def __init__(self):
        super(TwitchAPIHandler, self).__init__(CLIENT_ID, API_TOKEN)
        self._clip_cache = []

    def update_game(self, game: str):
        self.channels.update(CHANNEL_ID, game=game)

    def update_title(self, title: str):
        self.channels.update(CHANNEL_ID, status=title)

    # Commands
    def highlight(self):
        stream = self.streams.get_stream_by_user(CHANNEL_ID)
        if not stream:
            raise IOError
        delta = (datetime.utcnow() - stream['created_at']).seconds
        timestamp = '{}:{:02}'.format(delta // 60 ** 2, delta // 60 % 60)
        with open('timestamps.txt', 'a') as ts_file:
            ts_file.write(timestamp + '\n')
        return timestamp

    def random_clip(self):
        if not self._clip_cache:
            self._clip_cache = self.clips.get_top(channel=MY_USERNAME, limit=50, period='all')
        clip = pop_random_item(self._clip_cache)
        return clip['url']


class JokeHandler(object):

    def __init__(self):
        self._joke_cache = []
        self._reddit = Reddit(client_id=REDDIT_CLIENT_ID,
                              client_secret=SECRET,
                              password=PASSWORD,
                              user_agent=BOT_USERNAME,
                              username=USERNAME)

    def _fetch_jokes(self):
        r_jokes = self._reddit.subreddit('jokes').top('week')
        self._joke_cache = [(joke.title, joke.selftext) for joke in r_jokes if len(joke.selftext) < 150]

    # Commands
    def random_joke(self):
        if not self._joke_cache:
            self._fetch_jokes()
        joke = pop_random_item(self._joke_cache)
        return ' '.join(joke).replace('\n', ' ')


class CommandHandler(object):

    def __init__(self, _irc_client: TwitchIRCHandler):
        self._irc_client = _irc_client
        self._twitch_api_handler = TwitchAPIHandler()
        self._joke_handler = JokeHandler()
        self._ffz_emote_cache = []
        self._re = re.compile(r'^!(?P<cmd>\w+)( +(?P<args>\S.*))?')
        self._champ = ('PogChamp', 'ChampPog')

    def __call__(self, msg: str):
        if msg in self._champ:
            self._irc_client.say(self._champ[1 - self._champ.index(msg)])
            return
        m = self._re.match(msg)
        if not m:
            return
        cmd, args = m['cmd'], m['args'] or ''
        try:
            method = getattr(self, 'cmd_' + cmd)
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
        except IOError:
            # Something went wrong in some HTTP request
            self._irc_client.action('Unexpected error')

    def _parse_args_for_method(self, method, args: str) -> Tuple:
        if method in (self.cmd_game, self.cmd_title):
            if not args:
                method_str = self._cmd_method_to_str(method.__name__)
                raise CommandError(f'Usage: {method_str} <text>')
            return args,
        args = tuple(args.split())
        if method == self.cmd_pyramid:
            return self._parse_pyramid_args(*args)
        return args

    def cmd_help(self):
        cmd_list = [self._cmd_method_to_str(m) for m in dir(self) if m.startswith('cmd_')]
        self._irc_client.action(f"Commands: {', '.join(cmd_list)}")

    def cmd_game(self, game: str):
        self._twitch_api_handler.update_game(game)

    def cmd_title(self, title: str):
        self._twitch_api_handler.update_title(title)

    def cmd_highlight(self):
        timestamp = self._twitch_api_handler.highlight()
        self._irc_client.action(f'Timestamp saved! [{timestamp}]')

    def cmd_np(self):
        foobar2k = r'C:\Program Files (x86)\foobar2000\foobar2000.exe'

        # Verify that foobar2k is running
        tasks = subprocess.check_output(['tasklist', '/FO', 'CSV'], shell=True, universal_newlines=True)
        tasks = (s.split(',')[0] for s in tasks.splitlines())
        if '"foobar2000.exe"' not in tasks:
            self._irc_client.action('N/A')
            return

        # Run a foobar2k command that copies the currently playing track to clipboard
        prev_clip = pyperclip.paste()  # Save current clipboard content to restore later
        pyperclip.copy('')  # Clear clipboard first, so we can check for failure
        subprocess.run([foobar2k, '/runcmd-playlist=Copy name'])
        track = pyperclip.paste()
        pyperclip.copy(prev_clip)
        self._irc_client.action(f'Now playing: {track}' if track else 'N/A')

    def cmd_joke(self):
        joke = self._joke_handler.random_joke()
        self._irc_client.say(joke)

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

    def cmd_pyramid(self, text, size):
        pyramid = [' '.join([text] * (i + 1 if i < size else 2 * size - (i + 1)))
                   for i in range(2 * size - 1)]
        for block in pyramid:
            self._irc_client.say(block)

    @staticmethod
    def _parse_pyramid_args(*args) -> Tuple[str, int]:
        # !pyramid <size: number from 1 to 7> <text: string>
        # or !pyramid <text: string> (in this case, the pyramid will be of size 3)
        if not args:
            raise CommandError('Usage: !pyramid [<size>] <text>')
        size = 3
        if len(args) > 1 and str(args[0]).isnumeric():
            size = int(args[0])
            if size not in range(1, 8):
                raise CommandError('Pyramid size must be between 1 and 7.')
            args = args[1:]
        text = ' '.join(args)
        return text, size

    @staticmethod
    def _cmd_method_to_str(method_name):
        # Example: 'cmd_help' becomes '!help'
        return re.sub(r'cmd_(?P<cmd>\w+)', r'!\1', method_name)


class CommandError(ValueError):
    def __init__(self, *args, **kwargs):
        super(CommandError, self).__init__(*args, **kwargs)
