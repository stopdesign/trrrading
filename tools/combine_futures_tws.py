import os
from datetime import datetime, timezone

import pandas as pd

"""
Преобразование формата IBKR в формат Polygon.
Для каждого дня посмотреть, какой контракт самый мощный в этот день.
Добавить данные этого контракта в общий список.
"""

BASE = "/Users/gregory/projects/life/trrrading/data/ib"


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def get_contracts(sid):
    exchange, symbol = sid.split("_")
    path = f"{BASE}/{exchange}/"
    res = []
    for f in os.scandir(path):
        if not f.is_dir() and f.name.startswith(sid):
            res.append(f.name)
    return sorted(res)


def main():
    import pandas as pd

    sid = "CBOT_ZR"

    # Define the folder where the data files are stored
    data_folder = BASE + "/CBOT"

    # Get a list of all the data files in the folder
    # data_files = os.listdir(data_folder)
    contracts = get_contracts(sid)

    # Define a function to read a single data file and return a DataFrame with the OHLC data
    def read_data_file(file_path):
        df = pd.read_csv(file_path, parse_dates=True)
        df.columns = "t,o,h,l,c,vw,v,n".split(",")
        return df

    # Read all the data files into a list of DataFrames
    con_dfs = {}
    groups = []
    for contract in contracts:
        exp_month = (contract.split("-")[0]).split("_")[-1]
        if exp_month.isnumeric():
            file_name = f"{data_folder}/{contract}"
            con_df = read_data_file(file_name)
            con_df["exp"] = exp_month
            con_df["day"] = pd.to_datetime(con_df["t"], unit="s").dt.date
            grouped = con_df.groupby([con_df.day]).agg({"v": "sum"})
            con_dfs[exp_month] = con_df
            grouped.columns = [exp_month]
            groups.append(grouped)

    # Concatenate all the DataFrames into a single DataFrame
    df = pd.concat(groups, join="outer", axis=1).fillna(0)

    # Find the column with the maximum value for each row
    continuous = df.idxmax(axis=1).cummax()

    res = []
    for day, contract in continuous.to_dict().items():
        df = con_dfs[contract]
        res.append(df[df["day"] == day])

    roll_forward = pd.concat(res, axis=0)
    del roll_forward["day"]

    roll_forward.to_csv(f"{data_folder}/{sid}_CONT-trades.csv", index=False)


if __name__ == "__main__":
    main()
