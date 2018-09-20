from twitch import TwitchClient
from datetime import datetime
import praw
import socket
import requests
import random
import json

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


class TwitchIRCHandler(object):

    def __init__(self):
        self._sock = socket.socket()
        self._retry_count = 3
        self._ffz_emote_cache = []

    def connect(self):
        try:
            self._sock.connect((HOST, PORT))
            self._sock.send(bytes(f'PASS {PASS}\r\n', 'utf-8'))
            self._sock.send(bytes(f'NICK {BOT_USERNAME}\r\n', 'utf-8'))
            self._sock.send(bytes(f'JOIN #{MY_USERNAME}\r\n', 'utf-8'))
            while True:
                received = self._sock.recv(1024).decode()
                if not received:
                    self._retry_count -= 1
                    if not self._retry_count:
                        print('Connection error')
                        return False
                    print('Connection error, retrying')
                    self.connect()
                if 'End of /NAMES list' in received:
                    print(f"Connected to {MY_USERNAME}'s Twitch chat.")
                    return True
        except socket.error as err:
            self._retry_count -= 1
            if not self._retry_count:
                print(f'Connection error: {err.strerror}')
                return False
            print(f'Connection error: {err.strerror}. Retrying')
            self.connect()

    def disconnect(self):
        self._sock.close()

    def get_messages(self):
        try:
            received = self._sock.recv(1024).decode()
            if not received:
                print('Connection reset')
                return
            lines = received.split('\r\n')
            messages = [line for line in lines if 'PRIVMSG' in line]
            pings = [line for line in lines if 'PRIVMSG' not in line and 'PING' in line]
            for _ in pings:
                self._sock.send(bytes('PONG :tmi.twitch.tv\r\n', 'utf-8'))
            return list(map(TwitchIRCHandler._extract_username_message, messages))
        except socket.error as err:
            print(f'Connection reset: {err.strerror}')
            return

    def say(self, msg):
        try:
            msg = msg.replace('\n', ' ')
            print(f'> {msg}')
            self._sock.send(bytes(f'PRIVMSG #{MY_USERNAME} :{msg}\r\n', 'utf-8'))
        except socket.error as err:
            print(f'Connection reset: {err.strerror}')

    def action(self, msg):
        self.say(msg if msg.startswith('/me ') else f'/me {msg}')

    # Commands
    def _send_pyramid(self, text, size=3):
        if size not in range(1, 8):
            self.action('Pyramid size must be between 1 to 7.')
            return
        for i in range(2 * size - 1):
            block = [text] * (i + 1 if i < size else 2 * size - (i + 1))
            self.say(' '.join(block))

    def command_pyramid(self, msg):
        msg_parts = msg.split(' ')
        msg_parts = list(filter(None, msg_parts[1:]))
        if len(msg_parts) == 1 and msg_parts[0]:
            self._send_pyramid(msg_parts[0])
        elif len(msg_parts) > 1:
            if msg_parts[0].isdigit():
                self._send_pyramid(' '.join(msg_parts[1:]), int(msg_parts[0]))
            else:
                self._send_pyramid(' '.join(msg_parts))
        else:
            self.action('Usage: !pyramid [<size>] <text>')

    def send_random_emote(self):
        if not self._ffz_emote_cache:
            with requests.get(f'http://api.frankerfacez.com/v1/room/{MY_USERNAME}') as response:
                data = response.json()
            set_num = data['room']['set']
            emoticons = data['sets'][str(set_num)]['emoticons']
            self._ffz_emote_cache = [emote['name'] for emote in emoticons]
        
        self.say(random.choice(self._ffz_emote_cache))

    @staticmethod
    def _extract_username_message(line):
        head, _, message = line[line.find(':') + 1:].partition(':')
        username = head[:head.find('!')]
        return username, message


class TwitchAPIHandler(object):

    def __init__(self):
        self._twitch_client = TwitchClient(CLIENT_ID, API_TOKEN)

    def update_game(self, game):
        self._twitch_client.channels.update(CHANNEL_ID, game=game)

    def update_title(self, title):
        self._twitch_client.channels.update(CHANNEL_ID, status=title)

    # Commands
    def command_highlight(self, irc_client):
        stream = self._twitch_client.streams.get_stream_by_user(CHANNEL_ID)
        if not stream:
            return
        delta = (datetime.utcnow() - stream['created_at']).seconds
        timestamp = '{}:{:02}'.format(delta // 60 ** 2, delta // 60 % 60)
        with open('timestamps.txt', 'a') as ts_file:
            ts_file.write(timestamp + '\n')
        irc_client.action(f'Timestamp saved! [{timestamp}]')


class JokeHandler(object):

    def __init__(self):
        self._joke_cache = []
        self._reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID,
                                   client_secret=SECRET,
                                   password=PASSWORD,
                                   user_agent=BOT_USERNAME,
                                   username=USERNAME)

    def _fetch_jokes(self):
        r_jokes = self._reddit.subreddit('jokes').top('week')
        self._joke_cache = [(joke.title, joke.selftext) for joke in r_jokes if len(joke.selftext) < 150]

    def random_joke(self):
        if not self._joke_cache:
            self._fetch_jokes()
        joke = self._joke_cache.pop(random.randrange(len(self._joke_cache)))
        return ' '.join(joke).replace('\n', ' ')
