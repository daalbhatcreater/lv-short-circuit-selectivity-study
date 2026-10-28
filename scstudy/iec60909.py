"""Short-circuit currents in a radial LV system by the IEC 60909-0:2016 method
of the equivalent voltage source at the fault location.

All impedances are referred to the LV side and expressed in ohms. The system
is a chain: network feeder -> transformer -> series branches (busduct, cables),
with a fault bus after every branch.
"""

import math
from dataclasses import dataclass

C_MAX_LV = 1.05   # LV system with +6 % voltage tolerance (Table 1)
C_MIN_LV = 0.95


@dataclass
class NetworkFeeder:
    un_kv: float          # nominal voltage at the connection point
    sk_mva: float         # initial symmetrical short-circuit power S"kQ (max)
    r_over_x: float = 0.1
    sk_min_mva: float = None   # weakest source condition, defaults to sk_mva


@dataclass
class Transformer:
    sr_kva: float
    ur_hv_kv: float
    ur_lv_kv: float
    uk_pct: float
    pkr_kw: float         # load losses at rated current


@dataclass
class Branch:
    name: str             # name of the bus at the far end
    r20_ohm_km: float     # per conductor, at 20 degC
    x_ohm_km: float
    length_m: float
    runs: int = 1
    zero_seq_factor: float = 4.0   # Z0 = factor x Z1 for the cable return path

    def z1(self, theta_c=20.0):
        r = self.r20_ohm_km * (1 + 0.004 * (theta_c - 20))
        return complex(r, self.x_ohm_km) * self.length_m / 1000 / self.runs


def feeder_impedance(q: NetworkFeeder, t: Transformer, c=C_MAX_LV, sk_mva=None) -> complex:
    """Eq. (1)-(3), referred to the LV side through the rated ratio."""
    tr = t.ur_hv_kv / t.ur_lv_kv
    sk = sk_mva or q.sk_mva
    zq = c * (q.un_kv * 1e3) ** 2 / (sk * 1e6) / tr ** 2
    xq = zq / math.sqrt(1 + q.r_over_x ** 2)
    return complex(q.r_over_x * xq, xq)


def transformer_impedance(t: Transformer, c_max=C_MAX_LV):
    """Eq. (7)-(9) and the correction factor KT of eq. (12a)."""
    ur = t.ur_lv_kv * 1e3
    sr = t.sr_kva * 1e3
    zt = t.uk_pct / 100 * ur ** 2 / sr
    rt = t.pkr_kw * 1e3 * ur ** 2 / sr ** 2
    xt = math.sqrt(zt ** 2 - rt ** 2)
    x_pu = xt / (ur ** 2 / sr)
    kt = 0.95 * c_max / (1 + 0.6 * x_pu)
    return complex(rt, xt) * kt, kt


def kappa(z: complex) -> float:
    """Peak factor, eq. (55); radial network so no 1.15 factor."""
    return 1.02 + 0.98 * math.exp(-3 * z.real / z.imag)


@dataclass
class FaultResult:
    bus: str
    z1: complex
    ik3_ka: float
    ip_ka: float
    kappa: float
    ik1_ka: float
    ik3_min_ka: float
    ik1_min_ka: float

    @property
    def r_over_x(self):
        return self.z1.real / self.z1.imag


def fault_levels(q: NetworkFeeder, t: Transformer, branches, un_lv_v=415.0,
                 theta_min_c=80.0):
    """Max and min three-phase and line-to-earth currents at every bus.

    Maximum currents use cmax and conductors at 20 degC; minimum currents use
    cmin and conductors at theta_min_c (end-of-fault temperature).
    """
    zt, kt = transformer_impedance(t)
    # KT applies to maximum currents only (6.3.3)
    zt_min = zt / kt
    # Dyn transformer: zero sequence of the HV network does not pass through,
    # and Z0T is taken equal to Z1T (core type, delta primary)
    z0t, z0t_min = zt, zt_min

    results = []
    lv_terminal = Branch("LV terminals", 0.0, 0.0, 0.0)
    z_series_max = 0j
    z_series_min = 0j
    z0_series_max = 0j
    z0_series_min = 0j
    for b in [lv_terminal] + list(branches):
        z_series_max += b.z1(20.0)
        z_series_min += b.z1(theta_min_c)
        z0_series_max += b.z1(20.0) * b.zero_seq_factor
        z0_series_min += b.z1(theta_min_c) * b.zero_seq_factor

        z1_max = feeder_impedance(q, t, C_MAX_LV) + zt + z_series_max
        z1_min = feeder_impedance(q, t, C_MIN_LV, q.sk_min_mva) + zt_min + z_series_min
        z0_max = z0t + z0_series_max
        z0_min = z0t_min + z0_series_min

        ik3 = C_MAX_LV * un_lv_v / (math.sqrt(3) * abs(z1_max))
        ik3_min = C_MIN_LV * un_lv_v / (math.sqrt(3) * abs(z1_min))
        ik1 = math.sqrt(3) * C_MAX_LV * un_lv_v / abs(2 * z1_max + z0_max)
        ik1_min = math.sqrt(3) * C_MIN_LV * un_lv_v / abs(2 * z1_min + z0_min)
        k = kappa(z1_max)
        results.append(FaultResult(
            bus=b.name, z1=z1_max, ik3_ka=ik3 / 1e3,
            ip_ka=k * math.sqrt(2) * ik3 / 1e3, kappa=k,
            ik1_ka=ik1 / 1e3, ik3_min_ka=ik3_min / 1e3, ik1_min_ka=ik1_min / 1e3,
        ))
    return results, kt
