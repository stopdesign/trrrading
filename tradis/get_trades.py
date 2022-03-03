import json
import logging
import multiprocessing as mp
import sys
import time
import queue
import redis
import yaml
import websocket
from os.path import abspath
from datetime import datetime
from termcolor import cprint
from ibkr_web_api import IbApi

log = logging.getLogger(__name__)


logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


URL = "wss://ndcdyn.interactivebrokers.com/portal.proxy/v1/portal/ws"


def send_message(data, instruments, redis_client):
    if price := data.get("31"):
        conid = data.get("conid")
        instruments_by_conid = {i["conid"]: i for i in instruments}
        symbol = "{symbol}.{exchange}".format(**instruments_by_conid[conid])
        msg = {
            "dt": data.get("updated"),
            "price": price,
            "conid": conid,
            "symbol": symbol,
        }
        # print(json.dumps(msg, indent=None, default=str))
        json_str = json.dumps(msg, indent=None, default=str)
        redis_client.publish(f"{symbol}:TRADES", json_str)


def parse_data(d, instruments, redis_client):
    try:
        j = json.loads(d)
        if "_updated" in j:
            j["updated"] = datetime.utcfromtimestamp(j["_updated"] / 1000)
        if "hb" in j:
            j["dt"] = datetime.utcfromtimestamp(j["hb"] / 1000)

        # Тут что-то поделать с сообщениями
        if j.get("topic") != "tic":
            cprint(json.dumps(j, indent=None, default=str), "white")
            if "31" in j:
                send_message(j, instruments, redis_client)

    except Exception as e:
        cprint(f"Bad JSON? {d}, {e}", "red")
    # print()


def worker(config, hb_queue, data_queue):

    username = config["username"]
    password = config["password"]
    paper = config["paper"]
    secret = config["secret"]
    redis_config = config["redis"]

    instruments = config["instruments"]

    ib = IbApi(
        username,
        password,
        paper,
        secret=secret,
        debug=False,
        redis_host=redis_config["host"],
        redis_port=redis_config["port"],
        redis_db=redis_config["db"],
        redis_password=redis_config["password"],
    )

    # ib.load_session()
    ib.load_redis_session()
    cp = ib.session.cookies.get("cp")

    print("CP", cp)

    cprint("CONNECT", "green")
    ws = websocket.create_connection(URL, cookie=f"cp={cp}")

    time.sleep(1)

    cprint("SUBSCRIBE", "green")
    for instrument in instruments:
        conid = instrument["conid"]
        ws.send(f"smd+{conid}+" + '{"fields":["31"]}')

    last_echo = datetime.now()
    last_tic = datetime.now()

    try:
        while d := ws.recv():
            try:
                d = d.decode()
                data_queue.put(d)
                hb_queue.put("ALIVE")
            except Exception as e:
                cprint(f"Unknown decoding exception {e}", "red")

            # recv прерывается не реже, чем таймаут watchdog
            # Здесь можно проверить, не пора ли подергать сокет

            delay = (datetime.now() - last_echo).total_seconds()
            if delay > 27:
                cprint(f"NEW ECHO", "yellow")
                ws.send("ech+hb")
                last_echo = datetime.now()

            delay = (datetime.now() - last_tic).total_seconds()
            if delay > 57:
                cprint(f"NEW TIC", "yellow")
                ws.send("tic")
                last_tic = datetime.now()

    except websocket.WebSocketConnectionClosedException:
        data_queue.put("CLOSED")

    except KeyboardInterrupt:
        for instrument in instruments:
            conid = instrument["conid"]
            ws.send(f"umd+{conid}" + '{}')
        cprint(f"STOPPED", "red")
        data_queue.put("STOPPED")

    except Exception as e:
        cprint(f"Unknown exception {e}", "red")
        data_queue.put("EXCEPTION")


def watchdog(hb_queue, data_queue):
    """
    This check the queue for updates and send a signal to it
    when the child process isn't sending anything for too long
    """
    while True:
        try:
            hb_queue.get(timeout=15)
        except queue.Empty as e:
            cprint(f"[WATCHDOG]: Maybe WORKER is slacking {e}", "red")
            data_queue.put("KILL WORKER")


def start_process(worker, config, hb_queue, data_queue):
    process = mp.Process(
        target=worker,
        args=(config, hb_queue, data_queue),
    )
    process.start()
    return process


def main(config):
    """The main process"""
    hb_queue = mp.Queue()
    data_queue = mp.Queue()

    redis_config = config["redis"]
    redis_client = redis.Redis(
        host=redis_config["host"],
        port=redis_config["port"],
        db=redis_config["db"],
        password=redis_config["password"],
    )

    instruments = config["instruments"]

    watchdog_process = mp.Process(
        target=watchdog,
        args=(hb_queue, data_queue),
    )
    watchdog_process.daemon = True
    watchdog_process.start()

    workr = start_process(worker, config, hb_queue, data_queue)

    while True:
        msg = data_queue.get()

        if msg and '"authenticated": false' in msg:
            cprint(f"[MAIN]: unauthenticated, {msg}", "red")
            time.sleep(10)
            msg = "KILL WORKER"

        if msg and msg[0] == "{":
            # Сообщение от IBKR
            parse_data(msg, instruments, redis_client)

        elif msg == "KILL WORKER":
            cprint("[MAIN]: Terminating slacking WORKER", "yellow")
            workr.terminate()
            time.sleep(0.1)
            if not workr.is_alive():
                cprint("[MAIN]: WORKER is a goner", "yellow")
                workr.join(timeout=1.0)
                cprint("[MAIN]: Joined WORKER successfully!", "yellow")

                cprint("\n\nSTART AGAIN", "green")
                workr = start_process(worker, config, hb_queue, data_queue)
            else:
                cprint("[MAIN] что-то пошло не так", "red")
                pass

        elif msg == "STOPPED":
            data_queue.close()
            hb_queue.close()
            break

        else:
            cprint(msg, "blue")


if __name__ == "__main__":

    # Загрузка конфига
    config_path = abspath("config_local.yaml")
    config = yaml.full_load(open(config_path))

    try:
        main(config)
    except KeyboardInterrupt:
        print("DONE")
