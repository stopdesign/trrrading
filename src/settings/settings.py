import pathlib
from settings import keys

CAN_SHORT = True

DATA_API_KEYS = getattr(keys, "demo")
BASE_URL_DATA = "https://api-live.exante.eu"
BASE_URL_TRADE = "https://api-demo.exante.eu"

# DEMO
CLIENT_ID = "18ac3b58-d602-4b5a-a7c3-19259d12f51b"
APP_ID = "6a3dd20c-0156-44e5-af49-33070159454e"
SHARED_KEY = "JPrfr4vxhQc7DkpEe4mG+HhzLlR1yIf1"

ACCOUNT_ID = "HUYHUY.001"

# Alerts
TELEGRAM_TOKEN = None
TELEGRAM_CHANNEL_ID = "*****"
TELEGRAM_USERNAME = ""

BASE_DIR = pathlib.Path(__file__).parents[2].absolute()
