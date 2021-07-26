"""
Получение исторических данных из API Exante.
"""
import os
import sys
import json
import re
import jwt
import requests
from time import sleep
from datetime import datetime, timezone
from settings import keys
from termcolor import cprint


env = "live"
api_keys = getattr(keys, env)


interval_size = "60"
data_type = "trades"


def interval_dt(interval):
    return datetime.fromtimestamp(interval["timestamp"] // 1000)


def get_next_headers():
    global api_keys
    api_keys = api_keys[1:] + [api_keys[0]]
    key = api_keys[0]
    payload = {"iss": key[0], "sub": key[1], "aud": ["ohlc", "feed", "symbols"]}
    token = jwt.encode(payload, key[2], algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def main(ticker="URNM.ARCA"):

    url = f"https://api-{env}.exante.eu/md/3.0/ohlc/{ticker}/{interval_size}"

    all_data = []
    size = 5000

    from_dt = datetime(year=2021, month=1, day=1)
    from_dt = from_dt.replace(tzinfo=timezone.utc).timestamp()
    from_dt = int(from_dt) * 1000

    while True:
        params = {"from": from_dt, "type": data_type, "size": size}
        try:
            res = requests.get(
                url, params=params, headers=get_next_headers(), timeout=20,
            )
        except requests.exceptions.RequestException as e:
            cprint(f"{e!s}", color="red")
            sleep(3)
            continue

        if res.status_code == 200:
            data = res.json()

            if not data:
                print("EMPTY RESPONSE")
                break

            from_dt = data[0]["timestamp"] + 1

            print(datetime.now(), len(data), interval_dt(data[0]))

            all_data += sorted(data, key=lambda x: x["timestamp"])

            with open(f"{env}-{ticker}-{data_type}-{interval_size}.jsonl", "w") as f:
                res = ""
                for interval in all_data:
                    res += json.dumps(interval, indent=None, default=str) + "\n"
                f.write(res)

            if len(data) < size:
                print("ALL DONE")
                break

            sleep(3)

        elif res.status_code == 429:
            print("429")
            sleep(10)

        else:
            print(res.status_code)
            print(res.text)
            break


if __name__ == "__main__":
    url = "https://api-live.exante.eu/md/3.0/exchanges/ARCA"
    res = requests.get(url, headers=get_next_headers())
    # print(json.dumps(res.json()[:10], indent=2, default=str))

    descriptions = {}
    for stock in res.json():
        descriptions[stock["symbolId"]] = stock["description"]

    # base_dir = "../../data/arca/"
    base_dir = "./"

    done = []
    for file_name in os.listdir(base_dir):
        if mtc := re.search(r"^live-([A-Z.]+)-trades-60\.jsonl$", file_name):
            size = os.path.getsize(base_dir + file_name) / (1024 * 1024)
            if size > 2:
                done.append(mtc[1])

    symbols = []

    # Качать по списку из файла
    # for line in open("../../data/liquid-arca.txt"):
    #     symbol = line.split(" ")[0]
    #     d = descriptions.get(symbol, "").lower()
    #     if "leverage" in d or "1x" in d or "2x" in d or "3x" in d or "5x" in d:
    #         continue
    #     if symbol in done:
    #         continue
    #     symbols.append(symbol)

    # Качать все
    # for el in res.json():
    #     if el["symbolId"] not in done:
    #         symbols.append(el["symbolId"])

    # symbols = ["TNA.ARCA", "EDV.ARCA", "URNM.ARCA", "SRVR.ARCA", "ROM.ARCA", "XES.ARCA", "VCR.ARCA", "ONLN.ARCA", "XSD.ARCA", "CWI.ARCA", "GNR.ARCA", "EPOL.ARCA", "IRBO.ARCA", "SLYG.ARCA", "USRT.ARCA", "FXD.ARCA", "MDYV.ARCA", "FUTY.ARCA", "IHAK.ARCA", "IWV.ARCA", "VOOV.ARCA", "IWY.ARCA", "DIAL.ARCA", "PTBD.ARCA", "PBD.ARCA", "AMZA.ARCA", "DSI.ARCA", "INFL.ARCA", "VOOG.ARCA", "HEDJ.ARCA", "PSK.ARCA", "FMAT.ARCA", "THD.ARCA", "MOO.ARCA", "IBDM.ARCA", "NUSI.ARCA", "SCHK.ARCA", "PFXF.ARCA", "IBDN.ARCA", "JHMM.ARCA", "KBA.ARCA", "DIG.ARCA", "FXL.ARCA", "MGC.ARCA", "PCEF.ARCA", "ERUS.ARCA", "KRBN.ARCA", "SLX.ARCA", "SPAK.ARCA", "HYEM.ARCA", "SWAN.ARCA", "IDEV.ARCA", "FXR.ARCA", "FPX.ARCA", "AOM.ARCA", "IBDP.ARCA", "MLPX.ARCA", "FIDU.ARCA", "DGS.ARCA", "TLH.ARCA", "TTT.ARCA", "IBDO.ARCA", "EBND.ARCA", "PFFA.ARCA", "VDC.ARCA", "SUB.ARCA", "AOR.ARCA", "QLTA.ARCA", "DIVO.ARCA", "RWX.ARCA", "DJP.ARCA", "HEZU.ARCA", "FSTA.ARCA", "EWN.ARCA", "RWR.ARCA", "DVYE.ARCA", "EWD.ARCA"]
    # symbols = ['AMZA.ARCA', 'ARKK.ARCA', 'ARKW.ARCA', 'BLOK.ARCA', 'CHIQ.ARCA', 'COPX.ARCA', 'CQQQ.ARCA', 'EMQQ.ARCA', 'EPOL.ARCA', 'FDN.ARCA', 'GUNR.ARCA', 'IRBO.ARCA', 'ITOT.ARCA', 'IWP.ARCA', 'IXC.ARCA', 'JNK.ARCA', 'LIT.ARCA', 'MLPA.ARCA', 'MSOS.ARCA', 'OIH.ARCA', 'PBD.ARCA', 'ROBO.ARCA', 'SSO.ARCA', 'TAN.ARCA', 'URA.ARCA', 'VCR.ARCA', 'VDE.ARCA', 'XSD.ARCA']
    symbols = ["COPX.ARCA"]

    print(f"Done: {len(done)}, todo: {len(symbols)}")

    for symbol in sorted(symbols):
        print()
        print(symbol)
        main(symbol)
