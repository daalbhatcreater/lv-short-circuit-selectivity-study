"""Current/time selectivity between an upstream and a downstream device.

The pair is selective at a current I if the upstream device's no-trip time is
longer than the downstream device's total clearing time. The selectivity limit
Is is the lowest overcurrent where that fails (IEC 60947-2, Annex A). Above Is
the curves alone cannot prove selectivity; energy-based selectivity needs the
maker's tested tables.
"""

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class SelectivityResult:
    upstream: str
    downstream: str
    ik_max_ka: float      # maximum fault at the downstream device
    limit_ka: float       # selectivity limit, inf if none found below ik_max

    @property
    def total(self):
        return math.isinf(self.limit_ka)

    @property
    def verdict(self):
        if self.total:
            return f"total (up to {self.ik_max_ka:.1f} kA)"
        return f"partial, Is = {self.limit_ka:.2f} kA"


def check(upstream, downstream, ik_max_ka, i_start=None, points=4000):
    i_start = i_start or 1.0
    currents = np.geomspace(i_start, ik_max_ka * 1e3, points)
    for i in currents:
        t_up = upstream.t_min(i)
        if math.isinf(t_up):
            continue
        if not t_up > downstream.t_max(i):
            return SelectivityResult(upstream.name, downstream.name, ik_max_ka, i / 1e3)
    return SelectivityResult(upstream.name, downstream.name, ik_max_ka, math.inf)
