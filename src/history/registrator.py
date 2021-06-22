import json
import re
from time import sleep

import requests
import names
import random


def random_num_str(length):
    return "".join(map(str, random.sample(range(0, 10), length)))


def create():
    with requests.Session() as s:

        accounts = {
            "live": {},
            "demo": {},
        }

        s.get("https://exante.eu/technology/")

        fn = names.get_first_name()
        ln = names.get_last_name()
        full_name = f"{fn} {ln}"
        mls = ["google.com", "mail.ru", "yandex.ru", "ya.ru", "list.bk"]
        email = f"{fn}.{ln}.19" + random_num_str(2) + "@" + random.choice(mls)
        phone = "90" + random_num_str(8)
        password = "joa.jsHIdf-" + random_num_str(5)
        comment = "Sorry, API limits... :-)"

        url = "https://exante.eu/en/clientsarea/rest/signup/"
        data = {
            "email": email.lower(),
            "full_name": full_name,
            "country_code": "7",
            "phone": phone,
            "first_name": fn,
            "last_name": ln,
            "company": "",
            "signup_purpose": "trading",
            "legal_entity": "Cyprus",
            "comment": comment,
        }
        # print()
        # print(f"Signup: {email} | {password}")
        # # print(json.dumps(data, indent=2, default=str))
        res = s.post(url, data=data)
        # print(res.status_code)

        sleep(0.3)

        j = res.json()

        # print()
        # print("Auth")
        res = s.get(j["redirect"])
        # print(res.status_code)

        sleep(0.3)

        # print()
        # print("Password")
        url = "https://exante.eu/clientsarea/rest/set-password/"
        data = {"new_password": password}
        res = s.patch(url, json=data)
        # print(res.status_code)
        # print(res.text)

        sleep(0.3)

        # print()
        # print("Auth")
        url = "https://exante.eu/clientsarea/dashboard/"
        res = s.get(url)
        mtc = re.search(r'csrfToken = "([^"]+)"', res.text)
        csrftoken = mtc[1]
        # print("CSRF:", csrftoken)

        headers = {
            "referer": "https://exante.eu/clientsarea/dashboard/",
            "x-requested-with": "XMLHttpRequest",
            "x-csrftoken": csrftoken,
        }

        sleep(0.3)

        # print()
        # print("Account Live")
        url = "https://exante.eu/clientsarea/dashboard/create-account/"
        res = s.post(url, data={"env": 0}, headers=headers)
        # print(res.status_code)
        # print(res.json())
        accounts["live"]["client_id"] = res.json()["clientId"]

        sleep(0.3)

        # print()
        # print("Account Demo")
        url = "https://exante.eu/clientsarea/dashboard/create-account/"
        res = s.post(url, data={"env": 1}, headers=headers)
        # print(res.status_code)
        # print(res.json())
        accounts["demo"]["client_id"] = res.json()["clientId"]

        sleep(0.3)

        # 0 — live, 1 — demo
        # print()
        # print("Applications")
        url = "https://exante.eu/clientsarea/dashboard/application/"
        data = {"environment": 0, "description": comment, "password": password}
        res = s.post(url, data=data, headers=headers)
        # print(res.status_code, res.text)
        data = {"environment": 1, "description": comment, "password": password}
        res = s.post(url, data=data, headers=headers)
        # print(res.status_code, res.text)

        sleep(0.3)

        url = "https://exante.eu/clientsarea/dashboard/application/"
        res = s.get(url, headers=headers)
        # print(res.status_code)
        applications = res.json()

        accounts["live"]["app_id"] = applications["applications"][0]["id"]
        accounts["live"]["app_key"] = applications["applications"][0]["key"]
        accounts["live"]["env"] = applications["applications"][0]["environment"]
        accounts["demo"]["app_id"] = applications["applications"][1]["id"]
        accounts["demo"]["app_key"] = applications["applications"][1]["key"]
        accounts["demo"]["env"] = applications["applications"][1]["environment"]

        # print(json.dumps(accounts, indent=2, default=str))

        return accounts


def main():
    users = []

    for i in range(20):
        print(f"User {i}")
        try:
            users.append(create())
        except Exception as e:
            print("ERROR:", e)
        sleep(5)

    print("\nLive")
    for user in users:
        print('["{client_id}", "{app_id}", "{app_key}"]'.format(**user["live"]))

    print("\nDemo")
    for user in users:
        print('["{client_id}", "{app_id}", "{app_key}"]'.format(**user["demo"]))


if __name__ == "__main__":
    main()
