import os
from datetime import datetime, timezone

"""
Преобразование формата IBKR в формат Polygon.
Для каждого дня посмотреть, какой контракт самый мощный в этот день.
Добавить данные этого контракта в общий список.
"""

BASE = "/Users/gregory/projects/life/trrrading/data/COMEX"


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def get_contracts(symbol):
    path = f"{BASE}/{symbol}/"
    return [f.name for f in os.scandir(path) if (f.is_dir() and f.name.isnumeric())]


def get_days(symbol, contracts):
    res = []
    for contract in contracts:
        path = f"{BASE}/{symbol}/{contract}/TRADES/"
        res += [f[:10] for f in os.listdir(path)]
    return list(set(res))


def get_best_contract_data(symbol, contracts):

    days = get_days(symbol, contracts)

    best_contract = ""

    data = []

    for day in sorted(days):

        options = []
        for contract in contracts:
            path = f"{BASE}/{symbol}/{contract}/TRADES/{day}.txt"
            total_v = 0
            if os.path.isfile(path):
                for line in open(path).readlines():
                    try:
                        vol = line.strip().split("\t")[5]
                        total_v += float(vol)
                    except:
                        pass
                options.append([total_v, contract, path])
        options = sorted(options, reverse=True)

        # следующий контракт должен быть новее текущего
        if options[0][1] > best_contract:
            best_contract = options[0][1]

        best_path = path = f"{BASE}/{symbol}/{best_contract}/TRADES/{day}.txt"

        print(best_path)

        for line in open(best_path).readlines()[:15000]:
            dt_str, o, h, l, c, v, vw, n, _ = line.strip().split("\t")
            if dt_str == "date":
                continue
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            t = str(dt_to_ts(dt))
            data.append([t,o,h,l,c,vw,v,n])

    return data

def save_data(symbol, data):
    data = sorted(data)
    path = f"{BASE}/{symbol}.csv"

    res = "t,o,h,l,c,vw,v,n\n"
    for row in data:
        res += ",".join(row) + "\n"

    with open(path, "w") as f:
        f.write(res)
    

def main():

    # for symbol in ["ZO", "ZR", "ZS", "ZW"]:
    for symbol in ["HG"]:

        print(symbol)

        contracts = get_contracts(symbol)

        data = get_best_contract_data(symbol, contracts)

        save_data(symbol, data)

    print("DONE\n")


if __name__ == "__main__":
    main()


