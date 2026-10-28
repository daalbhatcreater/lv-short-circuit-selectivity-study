"""The system under study: a 2000 kVA, 11/0.433 kV transformer feeding a main
LV switchboard (MSB), a mechanical distribution board (MDB-M) and a final
distribution board (DB-P).

    11 kV grid --T1-- busduct --MSB--Q3-- 2x240 --MDB-M--Q4-- 70 --DB-P--Q5-- 6 -- load
                                  |Q1 incomer, Q2 UPS feeder
"""

from .devices import ElectronicLSI, ThermalMagnetic, mcb
from .iec60909 import Branch, NetworkFeeder, Transformer

GRID = NetworkFeeder(un_kv=11.0, sk_mva=500.0, r_over_x=0.1, sk_min_mva=250.0)

T1 = Transformer(sr_kva=2000, ur_hv_kv=11.0, ur_lv_kv=0.433, uk_pct=6.25, pkr_kw=20.0)

# Series branches; each one ends at the named bus. Busduct impedance is a
# typical maker figure for a 3200 A copper busduct; cables are Cu XLPE with
# IEC 60228 resistances and 0.08 Ohm/km reactance.
BRANCHES = [
    Branch("MSB", r20_ohm_km=0.012, x_ohm_km=0.014, length_m=12, zero_seq_factor=3.0),
    Branch("MDB-M", r20_ohm_km=0.0754, x_ohm_km=0.08, length_m=60, runs=2),
    Branch("DB-P", r20_ohm_km=0.268, x_ohm_km=0.08, length_m=45),
    Branch("Final circuit end", r20_ohm_km=3.08, x_ohm_km=0.08, length_m=25),
]

# where each device sits (the bus on its supply side) and the circuit it feeds
LOCATION = {"Q1": "MSB", "Q2": "MSB", "Q3": "MSB", "Q4": "MDB-M", "Q5": "DB-P"}
FEEDS = {"Q3": "MDB-M", "Q4": "DB-P", "Q5": "Final circuit end"}


def devices(revised=True):
    """Protective devices. `revised=False` gives the first-pass settings."""
    q1 = ElectronicLSI("Q1", frame_a=3200, ir_a=2880, tr_s=12, isd_a=4 * 2880,
                       tsd_s=0.3, ii_a=None, icu_ka=65, icm_ka=143, icw_ka=65,
                       kind="ACB")
    q2 = ElectronicLSI("Q2", frame_a=2000, ir_a=1800, tr_s=12, isd_a=6 * 1800,
                       tsd_s=0.2, ii_a=None, icu_ka=65, icm_ka=143, icw_ka=65,
                       kind="ACB")
    q3 = ElectronicLSI("Q3", frame_a=630, ir_a=504, tr_s=8, isd_a=6 * 504,
                       tsd_s=0.1, ii_a=(15 if revised else 10) * 630,
                       icu_ka=50, icm_ka=105, kind="MCCB")
    q4 = ThermalMagnetic("Q4", in_a=160, im_a=10 * 160, icu_ka=36, icm_ka=75.6)
    q5 = mcb("Q5", 32, "C", icu_ka=15 if revised else 10)
    return {d.name: d for d in (q1, q2, q3, q4, q5)}


PAIRS = [("Q1", "Q3"), ("Q3", "Q4"), ("Q4", "Q5")]

# IEC 60364-4-41, TN system at 230 V to earth: 0.4 s for final circuits up
# to 32 A, 5 s for distribution circuits
DISCONNECTION_LIMIT_S = {"Q3": 5.0, "Q4": 5.0, "Q5": 0.4}
