"""Independent check of the hand method with pandapower's IEC 60909 solver."""

import pandapower as pp
import pandapower.shortcircuit as sc


def build_net(grid, t, branches, un_lv_kv=0.415, theta_min_c=80.0):
    net = pp.create_empty_network(sn_mva=1.0)
    hv = pp.create_bus(net, vn_kv=grid.un_kv, name="11 kV")
    lv = pp.create_bus(net, vn_kv=un_lv_kv, name="LV terminals")
    pp.create_ext_grid(net, hv, s_sc_max_mva=grid.sk_mva, rx_max=grid.r_over_x,
                       s_sc_min_mva=grid.sk_min_mva or grid.sk_mva, rx_min=grid.r_over_x,
                       x0x_max=1.0, r0x0_max=0.1, x0x_min=1.0, r0x0_min=0.1)
    pp.create_transformer_from_parameters(
        net, hv, lv, sn_mva=t.sr_kva / 1e3, vn_hv_kv=t.ur_hv_kv, vn_lv_kv=t.ur_lv_kv,
        vk_percent=t.uk_pct, vkr_percent=t.pkr_kw / t.sr_kva * 100,
        pfe_kw=0.0, i0_percent=0.0, shift_degree=150, vector_group="Dyn",
        vk0_percent=t.uk_pct, vkr0_percent=t.pkr_kw / t.sr_kva * 100,
        mag0_percent=100.0, mag0_rx=0.0, si0_hv_partial=0.9, name="T1")
    prev = lv
    for b in branches:
        bus = pp.create_bus(net, vn_kv=un_lv_kv, name=b.name)
        pp.create_line_from_parameters(
            net, prev, bus, length_km=b.length_m / 1e3,
            r_ohm_per_km=b.r20_ohm_km, x_ohm_per_km=b.x_ohm_km, c_nf_per_km=0.0,
            max_i_ka=10.0, parallel=b.runs,
            r0_ohm_per_km=b.r20_ohm_km * b.zero_seq_factor,
            x0_ohm_per_km=b.x_ohm_km * b.zero_seq_factor, c0_nf_per_km=0.0,
            endtemp_degree=theta_min_c, name=b.name)
        prev = bus
    return net


def run(grid, t, branches):
    """Return {bus name: (Ik3 max, ip, Ik1 max, Ik3 min)} in kA."""
    net = build_net(grid, t, branches)
    out = {}
    sc.calc_sc(net, case="max", fault="3ph", ip=True, lv_tol_percent=6)
    ik3 = net.res_bus_sc.ikss_ka.copy()
    ip = net.res_bus_sc.ip_ka.copy()
    sc.calc_sc(net, case="max", fault="1ph", lv_tol_percent=6)
    ik1 = net.res_bus_sc.ikss_ka.copy()
    sc.calc_sc(net, case="min", fault="3ph", lv_tol_percent=6)
    ik3_min = net.res_bus_sc.ikss_ka.copy()
    for idx, name in net.bus.name.items():
        if idx == 0:
            continue
        out[name] = (ik3[idx], ip[idx], ik1[idx], ik3_min[idx])
    return out
