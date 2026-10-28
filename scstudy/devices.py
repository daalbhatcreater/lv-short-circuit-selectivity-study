"""Time-current models of LV protective devices.

Every device gives two curves:
  t_min(I)  no-trip time: the device will not have tripped before this
  t_max(I)  total clearing time: the device has cleared by this
Both return inf where the device does not (or not certainly) operate. The
spread between them stands in for the tolerance band printed on maker curves.
"""

import math
from dataclasses import dataclass

INF = math.inf


@dataclass
class ElectronicLSI:
    """ACB or MCCB with an electronic long-time / short-time / instantaneous unit.

    Long time follows the usual I2t law t = tr * (6 Ir / I)^2, with tr the
    setting at 6 x Ir. Ir, Isd and Ii are in amps.
    """
    name: str
    frame_a: float
    ir_a: float
    tr_s: float
    isd_a: float
    tsd_s: float
    ii_a: float = None            # None = instantaneous switched off
    icu_ka: float = 0.0
    icm_ka: float = 0.0
    icw_ka: float = 0.0           # rated short-time withstand, 1 s
    kind: str = "ACB"

    def _lt(self, i):
        return self.tr_s * (6 * self.ir_a / i) ** 2

    def t_min(self, i):
        t = INF
        if i > 1.05 * self.ir_a:
            t = min(t, 0.8 * self._lt(i))
        if i >= 0.9 * self.isd_a:
            t = min(t, 0.8 * self.tsd_s)
        if self.ii_a and i >= 0.9 * self.ii_a:
            t = min(t, 0.01)
        return t

    def t_max(self, i):
        t = INF
        if i >= 1.2 * self.ir_a:
            t = min(t, self._lt(i))
        if i >= 1.1 * self.isd_a:
            t = min(t, 1.2 * self.tsd_s + 0.02)
        if self.ii_a and i >= 1.1 * self.ii_a:
            t = min(t, 0.03 if self.kind == "ACB" else 0.02)
        return t

    @property
    def label(self):
        ii = f"Ii {self.ii_a / 1e3:.1f} kA" if self.ii_a else "Ii off"
        return (f"{self.name}: {self.kind} {self.frame_a:g} A, Ir {self.ir_a:g} A, "
                f"Isd {self.isd_a / 1e3:.2f} kA / {self.tsd_s:g} s, {ii}")


@dataclass
class ThermalMagnetic:
    """Thermal-magnetic MCCB (IEC 60947-2) or MCB (IEC 60898-1).

    Thermal element modelled as a heated bimetal,
        t = tau * ln(x^2 / (x^2 - x0^2)),  x = I / In,
    with x0 between the conventional non-tripping and tripping currents.
    """
    name: str
    in_a: float
    im_a: float                   # magnetic setting (nominal)
    im_tol: float = 0.2           # +/- on the magnetic threshold
    tau_s: float = 300.0
    x0: float = 1.15
    band: float = 0.3             # +/- on thermal times
    i_conv_trip: float = 1.30     # conventional tripping current / In
    t_magnetic_s: float = 0.02
    icu_ka: float = 0.0
    icm_ka: float = 0.0
    kind: str = "MCCB TM"

    def _thermal(self, i):
        x = i / self.in_a
        if x <= self.x0:
            return INF
        return self.tau_s * math.log(x * x / (x * x - self.x0 ** 2))

    def t_min(self, i):
        if i >= (1 - self.im_tol) * self.im_a:
            return 0.005
        return (1 - self.band) * self._thermal(i)

    def t_max(self, i):
        # above the magnetic threshold the release opens the contacts; the
        # thermal element cannot make it faster than that
        if i >= (1 + self.im_tol) * self.im_a:
            return self.t_magnetic_s
        if i >= self.i_conv_trip * self.in_a:
            return (1 + self.band) * self._thermal(i)
        return INF

    @property
    def label(self):
        return f"{self.name}: {self.kind} {self.in_a:g} A, Im {self.im_a / 1e3:.2f} kA"


def mcb(name, in_a, curve="C", icu_ka=10.0):
    """IEC 60898-1 MCB: B 3-5 In, C 5-10 In, D 10-20 In instantaneous."""
    lo, hi = {"B": (3, 5), "C": (5, 10), "D": (10, 20)}[curve]
    mid = (lo + hi) / 2
    return ThermalMagnetic(
        name=name, in_a=in_a, im_a=mid * in_a, im_tol=(hi - mid) / mid,
        tau_s=100.0, x0=1.13, band=0.4, i_conv_trip=1.45, t_magnetic_s=0.01,
        icu_ka=icu_ka, kind=f"MCB {curve}",
    )


def current_for_time(device, t_limit, i_hi=200e3):
    """Smallest current the device is certain to clear within t_limit."""
    lo, hi = 1.0, i_hi
    if device.t_max(hi) > t_limit:
        return INF
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if device.t_max(mid) <= t_limit:
            hi = mid
        else:
            lo = mid
    return hi
