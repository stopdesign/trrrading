"""
Тестовый http-stream, изображающий события биржи при нажатии на кнопки.

— запустить скрипт
— подключиться к нему: curl http://127.0.0.1:8080/trades/
— понажимать в скрипте кнопки

Right: повторить trade с той же ценой
Up: повысить цену
Down: понизить цену
Esc: выход
"""

import asyncio
import json
import sys
import tty
import os
import termios
from datetime import datetime
from decimal import Decimal
from aiohttp import web

key_mapping = {
    127: "backspace",
    10: "return",
    32: "space",
    9: "tab",
    27: "esc",
    65: "up",
    66: "down",
    67: "right",
    68: "left",
}


key = None


def getkey():
    global key
    old = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    try:
        while True:
            b = os.read(sys.stdin.fileno(), 3).decode()
            if len(b) == 3:
                k = ord(b[2])
            else:
                k = ord(b)
            key = key_mapping.get(k, chr(k))
            print("key:", key)
            if key == "esc":
                raise KeyboardInterrupt
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)


async def handle_quotes(request):
    """
    {
      'timestamp': 1622584805370,
      'symbolId': 'COPX.ARCA',
      'bid': [{'price': '41.89', 'size': '100.0'}],
      'ask': [{'price': '42.47', 'size': '500.0'}],
    }
    """
    pass


async def handle_trades(request):
    global key

    response = web.StreamResponse(status=200, reason="OK")
    await response.prepare(request)

    price = Decimal("39.60")

    print("Connection:", dict(request.headers))

    while True:
        if key == "esc":
            sys.exit()
        if key:
            now = datetime.utcnow()
            ts = int(now.timestamp()) * 1000
            ts += + now.microsecond // 1000
            if key == "up":
                price += 1
            if key == "down":
                price -= 1
            msg = {
                "timestamp": ts,
                "price": price,
                "size": "100.00",
                "symbolId": "COPX.ARCA",
            }
            msg = json.dumps(msg, default=str)
            print(key)
            await response.write(msg.encode() + b"\n")
            key = None
        await asyncio.sleep(0.01)


def main():
    task = asyncio.to_thread(getkey)
    asyncio.gather(task, return_exceptions=True)

    app = web.Application()
    # app.add_routes([web.get("/quotes/", handle_quotes)])
    app.add_routes([web.get("/trades/", handle_trades)])
    web.run_app(app, host="127.0.0.1", print=lambda x: None)


if __name__ == "__main__":
    main()
