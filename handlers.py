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
PASS = config["botChatOAuth"]

# reddit
REDDIT_CLIENT_ID = config["redditClientID"]
SECRET = config["redditSecret"]
USERNAME = config["redditUsername"]
PASSWORD = config["redditPassword"]

# Twitch
CHANNEL_ID = config["myChannelID"]
CLIENT_ID = config["clientID"]
API_TOKEN = config["botAPIOAuth"]


class TwitchIRCHandler(object):

    def __init__(self):
        self._sock = socket.socket()

    def connect(self):
        self._sock.connect((HOST, PORT))
        self._sock.send(bytes('PASS ' + PASS + '\r\n', 'UTF-8'))
        self._sock.send(bytes('NICK ' + BOT_USERNAME + '\r\n', 'UTF-8'))
        self._sock.send(bytes('JOIN #' + MY_USERNAME + '\r\n', 'UTF-8'))
        while True:
            received = self.receive()
            if not received:
                return False
            for line in received:
                if 'End of /NAMES list' in line:
                    print("Connected to " + MY_USERNAME + "'s Twitch chat.")
                    return True

    def disconnect(self):
        self._sock.close()

    def receive(self):
        received = str(self._sock.recv(1024))
        if not received:
            print('Connection reset')
            self._sock.close()
            return []
        return received.split('\\r\\n')

    def pong(self):
        self._sock.send(bytes('PONG :tmi.twitch.tv' + '\r\n', 'UTF-8'))

    def say(self, msg):
        msg = msg.replace('\n', ' ')
        print('> ' + msg)
        self._sock.send(bytes('PRIVMSG #' + MY_USERNAME + ' :' + msg + '\r\n', 'UTF-8'))

    def action(self, msg):
        self.say(msg if msg.startswith('/me ') else '/me ' + msg)

    # Commands
    def _send_pyramid(self, text, size=3):
        if size not in range(1, 8):
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
    def extract_message(line):
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
    def command_highlight(self):
        stream = self._twitch_client.streams.get_stream_by_user(CHANNEL_ID)
        if not stream:
            return
        delta = (datetime.utcnow() - stream.created_at).seconds
        timestamp = '{}:{:02}'.format(delta // 60 ** 2, delta // 60 % 60)
        with open('timestamps.txt', 'a') as ts_file:
            ts_file.write(timestamp + '\n')


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
        return ' '.join(joke).replace('\n', ' ')
