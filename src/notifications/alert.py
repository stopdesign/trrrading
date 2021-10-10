import re
import json
import requests
from datetime import datetime, timedelta

from settings import (
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_TOKEN,
    # MAILGUN_DOMAIN,
    # MAILGUN_API_KEY,
    # MAILGUN_ALERT_FROM,
    # MAILGUN_ALERT_TO,
)


# def send_email(subject, text):
#     return requests.post(
#         f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
#         auth=("api", MAILGUN_API_KEY),
#         data={
#             "from": MAILGUN_ALERT_FROM,
#             "to": MAILGUN_ALERT_TO,
#             "subject": subject,
#             "text": text or subject,
#         },
#     )


ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def send_telegram(text: str):
    """
    send_telegram("message text")
    """

    token = TELEGRAM_TOKEN

    if not token:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "text": ansi_escape.sub("", text),
        "chat_id": TELEGRAM_CHANNEL_ID,
        "parse_mode": "html",
    }
    r = requests.post(url, data=data, timeout=3)

    if r.status_code != 200:
        raise requests.exceptions.HTTPError("post_text error")


class Alert:

    skip_duplicates_for = timedelta(days=1)

    def __init__(self, cache_path):
        self.results = []
        self.cache_path = cache_path
        self.cache = {}
        self.load_cache()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.send()

    def load_cache(self):
        try:
            self.cache = json.load(open(self.cache_path, "r"))
        except OSError:
            # No file or can't read it
            return
        # Remove outdated records
        for key, val in list(self.cache.items()):
            debut = datetime.fromisoformat(val["debut"])
            if debut + self.skip_duplicates_for < datetime.utcnow():
                self.cache.pop(key)

    def dump_cache(self):
        with open(self.cache_path, "w") as f:
            json.dump(self.cache, f, indent=2, default=str)

    def result(self, item_type, item_id, note=None):
        self.results.append(f"OK: {item_type} {item_id}, {note}")
        self.cache.pop(f"{item_type}_{item_id}", None)
        self.dump_cache()

    def error(self, item_type, item_id, exception=None, note=None):
        key = f"{item_type}_{item_id}"
        if key in self.cache:
            return

        subject = "Concur-NS integration ERROR"
        message = f"ERROR: {item_type} {item_id}"
        if note:
            message += f"\n{note}\n"
        if exception:
            message += f"\n{exception}\n"
        send_telegram(message)
        # send_email(subject, message)
        self.cache[key] = {"debut": datetime.utcnow().isoformat()}
        self.dump_cache()

    def send(self):
        if not self.results:
            return

        subject = "Concur-NS integration report"
        message = "\n".join(self.results)
        send_telegram(message)
        # send_email(subject, message)
