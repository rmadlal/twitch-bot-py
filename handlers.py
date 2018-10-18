import json
import random
import re
import socket
import subprocess
from datetime import datetime

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
        self._init_regexes()

    def _init_regexes(self):
        self._re_end = re.compile(r'^:\w+\.tmi\.twitch\.tv 366 \w+ #(?P<channel_name>\w+) :End of /NAMES list$')
        self._re_message = re.compile(r'^:(?P<user>\w+)!\1@\1\.tmi\.twitch\.tv '
                                      rf'PRIVMSG #{MY_USERNAME} :(?P<message>.+)$')

        # Pyramid command
        part_cmd = r'!pyramid'
        part_text = r'(?P<text>\S(.*\S)?)'
        # !pyramid <text>
        self._re_pyramid_def = re.compile(rf'^{part_cmd} +{part_text}.*$')
        # !pyramid <size> <text>
        self._re_pyramid_with_size = re.compile(rf'^{part_cmd} +(?P<size>\d+) +{part_text}.*$')

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

    def say(self, msg):
        try:
            msg = msg.replace('\n', ' ')
            self._sock.send(bytes(f'PRIVMSG #{MY_USERNAME} :{msg}\r\n', 'utf-8'))
            print(f'> {msg}')
        except socket.error as err:
            print(f'Connection reset: {err.strerror}')

    def action(self, msg):
        self.say(msg if msg.startswith('/me ') else f'/me {msg}')

    # Commands
    def _send_pyramid(self, text, size=3):
        if size not in range(1, 8):
            self.action('Pyramid size must be between 1 and 7.')
            return
        for i in range(2 * size - 1):
            block = [text] * (i + 1 if i < size else 2 * size - (i + 1))
            self.say(' '.join(block))

    def pyramid(self, msg):
        command = self._re_pyramid_with_size.match(msg) or self._re_pyramid_def.match(msg)
        if not command:
            self.action('Usage: !pyramid [<size>] <text>')
            return
        if 'size' in command.groupdict():   # Pyramid size was specified
            self._send_pyramid(command['text'], int(command['size']))
            return
        self._send_pyramid(command['text'])

    def random_emote(self):
        if not self._ffz_emote_cache:
            with requests.get(f'http://api.frankerfacez.com/v1/room/{MY_USERNAME}') as response:
                data = response.json()
            set_num = data['room']['set']
            emoticons = data['sets'][str(set_num)]['emoticons']
            self._ffz_emote_cache = [emote['name'] for emote in emoticons]

        self.say(random.choice(self._ffz_emote_cache))

    def now_playing(self):
        foobar2k = r'C:\Program Files (x86)\foobar2000\foobar2000.exe'
        message = 'N/A'

        # Verify that foobar2k is running
        tasks = subprocess.check_output(['tasklist', '/FO', 'CSV'], shell=True, universal_newlines=True)
        tasks = (s.split(',')[0] for s in tasks.splitlines())
        if '"foobar2000.exe"' not in tasks:
            self.action(message)
            return

        # Run a foobar2k command that copies the currently playing track to clipboard
        prev_clip = pyperclip.paste()   # Save current clipboard content to restore later
        pyperclip.copy('')              # Clear clipboard first, so we can check for failure
        subprocess.run([foobar2k, '/runcmd-playlist=Copy name'])
        track = pyperclip.paste()
        pyperclip.copy(prev_clip)
        message = f'Now playing: {track}' if track else message
        self.action(message)


class TwitchAPIHandler(TwitchClient):

    def __init__(self):
        super(TwitchAPIHandler, self).__init__(CLIENT_ID, API_TOKEN)
        self._clip_cache = []

    def update_game(self, game):
        self.channels.update(CHANNEL_ID, game=game)

    def update_title(self, title):
        self.channels.update(CHANNEL_ID, status=title)

    # Commands
    def highlight(self):
        stream = self.streams.get_stream_by_user(CHANNEL_ID)
        if not stream:
            return 'Unexpected error'
        delta = (datetime.utcnow() - stream['created_at']).seconds
        timestamp = '{}:{:02}'.format(delta // 60 ** 2, delta // 60 % 60)
        with open('timestamps.txt', 'a') as ts_file:
            ts_file.write(timestamp + '\n')
        return f'Timestamp saved! [{timestamp}]'

    def random_clip(self):
        if not self._clip_cache:
            try:
                self._clip_cache = self.clips.get_top(channel=MY_USERNAME, limit=50, period='all')
            except requests.RequestException:
                return 'Unexpected error'
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
