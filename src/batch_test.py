import os
import re
from statistics import mean

import plotext as plt
from datetime import datetime
from termcolor import cprint
from advisor import Advisor
from tester import Tester


def main() -> None:
    dt = datetime.now()

    # symbols = []
    # for file_name in os.listdir("./history/"):
    #     if mtc := re.search(r"^live-([A-Z.]+)-trades-60\.jsonl$", file_name):
    #         symbols.append(mtc[1])

    symbols = ["URA.ARCA", "COPX.ARCA"]

    strategy = "ChannelBreakout"

    for symbol in sorted(symbols):
        net_vals = []
        max_dds = []
        pfs = []
        # for length in [100, 120, 140, 160, 180, 200, 250, 300, 350, 400, 450, 500]:
        for length in [500, 550, 600, 650, 700, 750, 800]:
            advisors = [
                Advisor(strategy=strategy, length=length, instrument=symbol),
            ]
            tester = Tester(advisors)
            tester.start()
            tester.stop()
            net_val, max_dd, gp, gl, tc = tester.get_stats()
            pf = gp / abs(gl) if gl else 0
            cnt = tc["buy"] + tc["sell"]
            if max_dd > -1:
                res = (
                    f"{symbol}\t{strategy}\t{length}\t"
                    f"{net_val:+0.0f}\t{max_dd:0.2f}\t"
                    f"{gp:+0.0f}\t{gl:+0.0f}\t"
                    f"{cnt}\t{pf:0.2f}\n"
                )
                with open("batch.csv", "a") as batch:
                    batch.write(res)
            else:
                max_dd = 0
            net_vals.append(net_val)
            max_dds.append(float(max_dd))
            pfs.append(float(pf))

            if len(net_vals) > 5 and mean(net_vals) < 8000:
                break

        m_net_vals = mean(net_vals)
        m_max_dds = mean(max_dds)
        m_pfs = mean(pfs)

        if m_net_vals > 10000 and m_pfs > 0.85 and m_max_dds < 50:
            print()
            print(f"{symbol}\t{m_net_vals:10.0f}\t{m_max_dds:5.1f}\t{m_pfs:5.2f}")

            plt.clf()
            plt.subplots(1, 3)
            plt.colorless()

            plt.subplot(1, 1)
            plt.canvas_color("none")
            plt.axes_color("none")
            plt.scatter(net_vals, marker="⚈")
            plt.plotsize(45, 12)

            plt.subplot(1, 2)
            plt.canvas_color("none")
            plt.axes_color("none")
            plt.scatter(max_dds, marker="⚈")
            plt.plotsize(45, 12)

            plt.subplot(1, 3)
            plt.canvas_color("none")
            plt.axes_color("none")
            plt.scatter(pfs, marker="⚈")
            plt.plotsize(45, 12)

            plt.show()

    total_time = (datetime.now() - dt).total_seconds()
    cprint(f"\nDone in {total_time:0.2f} s", attrs=['bold'])


if __name__ == "__main__":
    main()
