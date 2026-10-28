"""Run the full study and write everything to results/.

    python study.py
"""

import math
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scstudy import pp_check, selectivity
from scstudy.devices import current_for_time
from scstudy.iec60909 import fault_levels
from scstudy.system import (BRANCHES, DISCONNECTION_LIMIT_S, FEEDS, GRID,
                            LOCATION, PAIRS, T1, devices)

OUT = Path(__file__).parent / "results"


def fault_table():
    res, kt = fault_levels(GRID, T1, BRANCHES)
    rows = [{
        "Bus": r.bus,
        "R/X": round(r.r_over_x, 3),
        "Ik3 max (kA)": round(r.ik3_ka, 2),
        "kappa": round(r.kappa, 3),
        "ip (kA)": round(r.ip_ka, 2),
        "Ik1 max (kA)": round(r.ik1_ka, 2),
        "Ik3 min (kA)": round(r.ik3_min_ka, 2),
        "Ik1 min (kA)": round(r.ik1_min_ka, 2),
    } for r in res]
    return pd.DataFrame(rows), {r.bus: r for r in res}, kt


def pandapower_table(faults):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pp = pp_check.run(GRID, T1, BRANCHES)
    rows = []
    for bus, (ik3, ip, ik1, ik3_min) in pp.items():
        r = faults[bus]
        rows.append({
            "Bus": bus,
            "Ik3 hand (kA)": round(r.ik3_ka, 2), "Ik3 pandapower (kA)": round(ik3, 2),
            "ip hand (kA)": round(r.ip_ka, 2), "ip pandapower (kA)": round(ip, 2),
            "Ik1 hand (kA)": round(r.ik1_ka, 2), "Ik1 pandapower (kA)": round(ik1, 2),
            "Ik3 min hand (kA)": round(r.ik3_min_ka, 2),
            "Ik3 min pandapower (kA)": round(ik3_min, 2),
            "max deviation (%)": round(100 * max(
                abs(r.ik3_ka - ik3) / ik3, abs(r.ip_ka - ip) / ip,
                abs(r.ik1_ka - ik1) / ik1, abs(r.ik3_min_ka - ik3_min) / ik3_min), 2),
        })
    return pd.DataFrame(rows)


def duty_table(devs, faults):
    """Breaking (Icu) and making (Icm) capacity against the fault at each device."""
    rows = []
    for name, d in devs.items():
        f = faults[LOCATION[name]]
        ik = max(f.ik3_ka, f.ik1_ka)
        row = {
            "Device": d.label, "Bus": f.bus, "Ik max (kA)": round(ik, 2),
            "Icu (kA)": d.icu_ka, "ip (kA)": round(f.ip_ka, 2),
            "Icm (kA)": d.icm_ka or "",
            "Breaking OK": ik <= d.icu_ka,
            "Making OK": (f.ip_ka <= d.icm_ka) if d.icm_ka else "",
        }
        if getattr(d, "icw_ka", 0):
            # short-time withstand, I^2 t equivalence with the longest delay
            t = 1.2 * d.tsd_s + 0.02
            row["Icw check"] = f"{ik:.1f} kA for {t:.2f} s vs {d.icw_ka:g} kA 1 s: " + (
                "OK" if ik ** 2 * t <= d.icw_ka ** 2 * 1.0 else "FAIL")
        rows.append(row)
    return pd.DataFrame(rows)


def selectivity_table(devs, faults):
    rows = []
    for up, down in PAIRS:
        ik = faults[LOCATION[down]].ik3_ka
        r = selectivity.check(devs[up], devs[down], ik)
        rows.append({"Upstream": up, "Downstream": down,
                     "Ik at downstream (kA)": round(ik, 2),
                     "Selectivity limit (kA)": "-" if r.total else round(r.limit_ka, 2),
                     "Result": r.verdict})
    return pd.DataFrame(rows)


def disconnection_table(devs, faults):
    """IEC 60364-4-41 automatic disconnection with the minimum earth fault at
    the far end of each circuit."""
    rows = []
    for name, limit in DISCONNECTION_LIMIT_S.items():
        d = devs[name]
        ik1 = faults[FEEDS[name]].ik1_min_ka * 1e3
        needed = current_for_time(d, limit)
        t = d.t_max(ik1)
        rows.append({"Device": name, "Circuit end": FEEDS[name],
                     "Ik1 min (kA)": round(ik1 / 1e3, 2),
                     "Current to clear in limit (kA)": round(needed / 1e3, 3),
                     "Clearing time (s)": round(t, 3), "Limit (s)": limit,
                     "OK": t <= limit})
    return pd.DataFrame(rows)


def plot_tcc(devs, faults, path):
    fig, ax = plt.subplots(figsize=(9, 7.5))
    colours = {"Q1": "tab:blue", "Q3": "tab:green", "Q4": "tab:orange", "Q5": "tab:red"}
    for name, colour in colours.items():
        d = devs[name]
        # each curve stops at the maximum fault the device can see
        i = np.geomspace(20, faults[LOCATION[name]].ik3_ka * 1e3, 1500)
        tmin = np.array([d.t_min(x) for x in i])
        tmax = np.array([d.t_max(x) for x in i])
        tmin[np.isinf(tmin)] = np.nan
        tmax[np.isinf(tmax)] = np.nan
        ax.plot(i, tmin, color=colour, lw=1.2)
        ax.plot(i, tmax, color=colour, lw=1.2, ls="--")
        ax.fill_between(i, tmin, tmax, color=colour, alpha=0.15, label=d.label)
    for k, bus in enumerate(("DB-P", "MDB-M", "MSB")):
        ik = faults[bus].ik3_ka * 1e3
        ax.axvline(ik, color="grey", lw=0.8, ls=":")
        ax.text(ik * 0.97, 4000 / 4 ** k, f"Ik {bus} {ik / 1e3:.1f} kA", fontsize=8,
                color="dimgrey", ha="right")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(20, 60e3)
    ax.set_ylim(0.004, 10000)
    ax.set_xlabel("Current at 415 V (A)")
    ax.set_ylabel("Time (s)")
    ax.set_title("Time-current curves, revised settings (solid: no-trip, dashed: clearing)")
    ax.grid(True, which="both", lw=0.3)
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    faults_df, faults, kt = fault_table()
    pp_df = pandapower_table(faults)
    first, revised = devices(revised=False), devices(revised=True)
    duty_first, duty = duty_table(first, faults), duty_table(revised, faults)
    sel_first, sel = selectivity_table(first, faults), selectivity_table(revised, faults)
    disc = disconnection_table(revised, faults)

    with pd.ExcelWriter(OUT / "study_results.xlsx") as xl:
        faults_df.to_excel(xl, "Fault levels", index=False)
        pp_df.to_excel(xl, "pandapower check", index=False)
        duty_first.to_excel(xl, "Duty - first pass", index=False)
        duty.to_excel(xl, "Duty - revised", index=False)
        sel_first.to_excel(xl, "Selectivity - first pass", index=False)
        sel.to_excel(xl, "Selectivity - revised", index=False)
        disc.to_excel(xl, "Disconnection", index=False)
    faults_df.to_csv(OUT / "fault_levels.csv", index=False)
    plot_tcc(revised, faults, OUT / "tcc.png")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(f"Transformer correction factor KT = {kt:.4f}\n")
    for title, df in [("Fault levels (IEC 60909)", faults_df),
                      ("Cross-check with pandapower", pp_df),
                      ("Device duty, first pass", duty_first),
                      ("Device duty, revised", duty),
                      ("Selectivity, first pass", sel_first),
                      ("Selectivity, revised", sel),
                      ("Automatic disconnection (TN, IEC 60364-4-41)", disc)]:
        print(title)
        print(df.to_string(index=False))
        print()


if __name__ == "__main__":
    main()
