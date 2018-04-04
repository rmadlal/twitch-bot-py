from twitch import TwitchClient
import praw
import socket
import random
from datetime import datetime
import json

with open('botconfig.json') as config_file:
    config = json.load(config_file)

BOT_USERNAME = 'uncleronnybot'
MY_USERNAME = 'uncleronny'

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

    def connect(self):
        try:
            self._sock.connect((HOST, PORT))
            self._sock.send(bytes('PASS %s\r\n' % PASS, 'utf-8'))
            self._sock.send(bytes('NICK %s\r\n' % BOT_USERNAME, 'utf-8'))
            self._sock.send(bytes('JOIN #%s\r\n' % MY_USERNAME, 'utf-8'))
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
                    print("Connected to %s's Twitch chat." % MY_USERNAME)
                    return True
        except socket.error as err:
            self._retry_count -= 1
            if not self._retry_count:
                print('Connection error: %s' % err.strerror)
                return False
            print('Connection error: %s. Retrying' % err.strerror)
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
            print('Connection reset: %s' % err.strerror)
            return

    def say(self, msg):
        try:
            msg = msg.replace('\n', ' ')
            print('> %s' % msg)
            self._sock.send(bytes('PRIVMSG #%s :%s\r\n' % (MY_USERNAME, msg), 'utf-8'))
        except socket.error as err:
            print('Connection reset: %s' % err.strerror)

    def action(self, msg):
        self.say(msg if msg.startswith('/me ') else '/me %s' % msg)

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

    @staticmethod
    def _extract_username_message(line):
        head, sep, message = line[line.find(':') + 1:].partition(':')
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
        irc_client.action('Timestamp saved! [%s]' % timestamp)


class JokeHandler(object):

    def __init__(self):
        self._reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID,
                                   client_secret=SECRET,
                                   password=PASSWORD,
                                   user_agent=BOT_USERNAME,
                                   username=USERNAME)
        self._joke_cache = []

    def _fetch_jokes(self):
        r_jokes = self._reddit.subreddit('jokes').top('week')
        self._joke_cache = [(joke.title, joke.selftext) for joke in r_jokes if len(joke.selftext) < 150]

    def random_joke(self):
        if not self._joke_cache:
            self._fetch_jokes()
        joke = random.choice(self._joke_cache)
        self._joke_cache.remove(joke)
        return ' '.join(joke).replace('\n', ' ')
