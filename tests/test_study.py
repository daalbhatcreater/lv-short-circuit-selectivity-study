import math
import warnings

import pytest

from scstudy import pp_check, selectivity
from scstudy.devices import mcb, current_for_time
from scstudy.iec60909 import fault_levels, kappa, transformer_impedance
from scstudy.system import BRANCHES, GRID, LOCATION, PAIRS, T1, devices


def test_transformer_impedance_by_hand():
    # ZT = 0.0625 * 433^2 / 2e6 = 5.859 mOhm, RT = 20e3 * 433^2 / 2e6^2 = 0.937 mOhm
    zt, kt = transformer_impedance(T1)
    assert kt == pytest.approx(0.9619, abs=1e-4)
    assert abs(zt) / kt == pytest.approx(5.859e-3, rel=1e-3)
    assert zt.real / kt == pytest.approx(0.9374e-3, rel=1e-3)


def test_kappa_limits():
    assert kappa(complex(0, 1)) == pytest.approx(2.0)
    assert kappa(complex(100, 1)) == pytest.approx(1.02)


def test_fault_levels_fall_along_the_feeder():
    res, _ = fault_levels(GRID, T1, BRANCHES)
    ik = [r.ik3_ka for r in res]
    assert ik == sorted(ik, reverse=True)
    assert all(r.ik3_min_ka < r.ik3_ka for r in res)


def test_agrees_with_pandapower():
    res, _ = fault_levels(GRID, T1, BRANCHES)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pp = pp_check.run(GRID, T1, BRANCHES)
    for r in res:
        ik3, ip, ik1, ik3_min = pp[r.bus]
        assert r.ik3_ka == pytest.approx(ik3, rel=0.01)
        assert r.ip_ka == pytest.approx(ip, rel=0.01)
        assert r.ik1_ka == pytest.approx(ik1, rel=0.01)
        assert r.ik3_min_ka == pytest.approx(ik3_min, rel=0.01)


def test_mcb_c_curve_matches_iec_60898():
    d = mcb("x", 32, "C")
    assert d.t_min(4.9 * 32) > 0.1      # no trip below 5 In
    assert d.t_max(10 * 32) <= 0.1      # trips at 10 In
    assert d.t_max(1.13 * 32) == math.inf
    assert 1 < d.t_min(2.55 * 32) and d.t_max(2.55 * 32) < 60   # 1-60 s band


def test_revised_settings_pass_all_duties():
    res, _ = fault_levels(GRID, T1, BRANCHES)
    faults = {r.bus: r for r in res}
    for name, d in devices(revised=True).items():
        f = faults[LOCATION[name]]
        assert max(f.ik3_ka, f.ik1_ka) <= d.icu_ka, name
        if d.icm_ka:
            assert f.ip_ka <= d.icm_ka, name


def test_revision_improves_selectivity():
    res, _ = fault_levels(GRID, T1, BRANCHES)
    faults = {r.bus: r for r in res}

    def limits(devs):
        return [selectivity.check(devs[u], devs[d], faults[LOCATION[d]].ik3_ka).limit_ka
                for u, d in PAIRS]

    first, revised = limits(devices(False)), limits(devices(True))
    assert math.isinf(revised[0])               # ACB over MCCB fully selective
    assert all(r >= f for r, f in zip(revised, first))
    assert revised[1] > first[1]


def test_current_for_time_inverts_curve():
    d = devices()["Q4"]
    i = current_for_time(d, 5.0)
    assert d.t_max(i) <= 5.0 < d.t_max(i * 0.99)
