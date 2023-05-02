import os

import pandas as pd

"""
Преобразование формата IBKR в формат Polygon.
Для каждого дня посмотреть, какой контракт самый мощный в этот день.
Добавить данные этого контракта в общий список.
"""

BASE = "/Users/gregory/projects/trading/data/ib"


def get_contracts(data_folder, sid):
    """
    Get a list of contract names for this sid.
    """
    res = []
    for f in os.scandir(data_folder):
        if not f.is_dir() and f.name.startswith(sid):
            res.append(f.name)
    return sorted(res)


def read_data_file(file_path):
    """
    Read a single data file.
    """
    df = pd.read_csv(file_path, parse_dates=True)
    df.columns = "t,o,h,l,c,vw,v,n".split(",")
    return df


def process_sid(sid):
    print(f"Combine files for {sid}")
    exchange = sid.split("_")[0]

    # Define the folder where the data files are stored
    data_folder = os.path.join(BASE, exchange)

    # Get a list of all the data files for this sid
    contracts = get_contracts(data_folder, sid)

    # Read all the data files into a list of DataFrames
    con_dfs = {}
    groups = []
    for contract in contracts:
        exp_month = (contract.split("-")[0]).split("_")[-1]
        if exp_month.isnumeric():
            file_name = f"{data_folder}/{contract}"
            print(contract)
            con_df = read_data_file(file_name)
            con_df["exp"] = exp_month
            con_df["day"] = pd.to_datetime(con_df["t"], unit="s").dt.date
            grouped = con_df.groupby([con_df.day]).agg({"v": "sum"})
            con_dfs[exp_month] = con_df
            grouped.columns = [exp_month]
            groups.append(grouped)

    print("Processing...")

    # Concatenate all the DataFrames into a single DataFrame
    df = pd.concat(groups, join="outer", axis=1).fillna(0)

    # Find the column with the maximum value for each row
    continuous = df.idxmax(axis=1).cummax()

    res = []
    for day, contract in continuous.to_dict().items():
        df = con_dfs[contract]
        res.append(df[df["day"] == day])

    res = pd.concat(res, axis=0)
    del res["day"]

    res.to_csv(f"{data_folder}/{sid}_CONT-trades.csv", index=False)

    print(f"Done {sid}\n")


def main():
    for sid in [
        "CME_NQ", "CME_MES", "NYMEX_NG", "CBOT_MYM", "CBOT_ZL",
        "CBOT_ZS", "CBOT_ZO", "CBOT_ZR", "CBOT_ZC", "CBOT_ZW", "CBOT_KE"
    ]:
        process_sid(sid)


if __name__ == "__main__":
    main()
