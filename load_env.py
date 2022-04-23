import os

try:
    from dotenv import load_dotenv  # pylint: disable=import-outside-toplevel
    load_dotenv()
except (ImportError, IOError):
    pass

required_env = {'BOT_CHANNEL_NAME', 'CHANNEL_NAME', 'USER_ID', 'CHAT_OAUTH', 'API_CLIENT_ID', 'API_OAUTH'}
if missing_env := required_env - set(os.environ):
    raise Exception('Missing required environment variables ' + ', '.join(missing_env))
