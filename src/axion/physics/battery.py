"""Independent thermal verification battery (Phase 2, P2.2).

Each experiment drives the *legacy* integrator (or the fidelity-pinned
replica where legacy's fixed ``DT`` cannot go) and compares against an
*independently derived* expectation: closed-form RC solutions, a direct
linear-system equilibrium solve, or a tight-tolerance DOP853 reference.
Self-comparison (legacy vs legacy) is never a pass criterion.

``run_all()`` returns the full machine-readable report dict; ``main()``
writes it under the configured results root. Tests import the ``exp_*``
functions and assert the acceptance bounds recorded alongside.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from axion.config.legacy_config import load_core
from axion.physics import equations as EQ
from axion.physics import reference as REF

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

_CORE = load_core(REPO_ROOT / "Scripts")
CFG = _CORE.CFG
N = int(CFG["N_NODES"])
NPR = int(CFG["NODES_PER_RACK"])
NR = int(CFG["N_RACKS"])
R_AMB = float(CFG["R_AMB"])
C_TH = float(CFG["C_THERMAL"])
T_AMB = float(CFG["T_AMBIENT"])
T_SAFE = float(CFG["T_SAFE"])
K_BP = float(CFG["K_BYPASS"])
HVAC_DEG = float(CFG["HVAC_DEGREE_PER_LEVEL"])
DT = float(CFG["DT"])
P_COOL = float(CFG["P_COOLING"])
R_MAT = _CORE._R_MAT.copy()


def _kw() -> dict[str, Any]:
    return dict(n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG,
                r_amb=R_AMB, c_th=C_TH)


def _fresh(T0: np.ndarray) -> Any:
    phys = _CORE.ThermalPhysics(seed=0)
    phys.T = T0.astype(np.float64).copy()
    phys.cooling_on = np.zeros(N, dtype=bool)
    phys.cooling_events = 0
    phys.cooling_energy_J = 0.0
    return phys


def _hvac0() -> np.ndarray:
    return np.zeros(NR, dtype=np.int32)


def exp_zero_equilibrium(steps: int = 400) -> dict[str, Any]:
    """Test A: P=0 everywhere; state must approach T_amb (T_in == T_amb at Q=0)."""
    T0 = 44.0
    phys = _fresh(np.full(N, T0))
    P = np.zeros(N)
    worst = 0.0
    for _ in range(steps):
        T, _ = phys.step(P, _hvac0())
        worst = max(worst, float(np.max(np.abs(T.astype(np.float64) - T_AMB))))
    final = float(np.max(np.abs(phys.T - T_AMB)))
    # Analytic envelope: |T0-T_amb| exp(-t/tau), tau = R_amb*C.
    bound = abs(T0 - T_AMB) * float(np.exp(-steps * DT / (R_AMB * C_TH))) + 1e-6
    return {"test": "A_zero_equilibrium", "steps": steps, "T0": T0,
            "final_max_abs_err_C": final, "analytic_bound_C": bound,
            "pass": bool(final <= bound),
            "cooling_events": int(phys.cooling_events)}


def exp_rc_response(power: float = 210.0, t0: float = 50.0,
                    steps: int = 120) -> dict[str, Any]:
    """Test B: uniform power; legacy trajectory vs exact scalar RC solution."""
    phys = _fresh(np.full(N, t0))
    P = np.full(N, power)
    t_in = T_AMB + K_BP * 8.0 * power
    times = (np.arange(1, steps + 1)) * DT
    expect = REF.rc_step_response(t0, power, t_in, r_amb=R_AMB, c_th=C_TH, t=times)
    errs = np.empty(steps)
    for k in range(steps):
        T, _ = phys.step(P, _hvac0())
        errs[k] = float(np.max(np.abs(T.astype(np.float64) - expect[k])))
    return {"test": "B_rc_response", "power_W": power, "t0_C": t0, "steps": steps,
            "max_abs_err_C": float(errs.max()), "rms_err_C": float(np.sqrt((errs**2).mean())),
            "final_abs_err_C": float(errs[-1]),
            "pass": bool(errs.max() < 5e-5),
            "cooling_events": int(phys.cooling_events)}


def exp_coupled_equilibrium(steps: int = 600) -> dict[str, Any]:
    """Test C: non-uniform fixed power; legacy + replica vs direct linear solve."""
    rng = np.random.default_rng(0)
    powers = 40.0 + (np.arange(N) % 6) * 20.0  # 40..140 W: hot enough to matter, cool enough to avoid cooling
    assert powers.max() < 150.0
    hvac = _hvac0()
    T_in = EQ.rack_inlet(powers, hvac, n_racks=NR, nodes_per_rack=NPR,
                         t_ambient=T_AMB, k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG)
    target = REF.coupled_equilibrium(powers, T_in, R_MAT, r_amb=R_AMB)

    phys = _fresh(np.full(N, 30.0))
    for _ in range(steps):
        phys.step(powers, hvac)
    legacy_err = float(np.max(np.abs(phys.T - target)))

    T = np.full(N, 30.0)
    for _ in range(steps):
        T = EQ.rk4_step(T, powers, hvac, R_MAT, dt=DT, **_kw())
    replica_err = float(np.max(np.abs(T - target)))
    return {"test": "C_coupled_equilibrium", "steps": steps,
            "target_max_C": float(target.max()),
            "legacy_max_abs_err_C": legacy_err, "replica_max_abs_err_C": replica_err,
            "pass": bool(replica_err < 1e-6 and legacy_err < 0.02
                          and target.max() < T_SAFE),
            "cooling_events": int(phys.cooling_events)}


def exp_boundaries() -> dict[str, Any]:
    """Test D: floors, ceilings, and inlet limits (documented, not altered)."""
    out: dict[str, Any] = {"test": "D_boundaries"}
    # D1: zero rack heat => inlet exactly ambient.
    t_in = EQ.rack_inlet(np.zeros(N), None, n_racks=NR, nodes_per_rack=NPR,
                         t_ambient=T_AMB, k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG)
    out["zero_heat_inlet_equals_ambient"] = bool(np.all(t_in == T_AMB))
    # D2: ceiling — extreme state is clipped to 110 on output.
    phys = _fresh(np.full(N, 200.0))
    T, _ = phys.step(np.zeros(N), _hvac0())
    out["ceiling_enforced"] = bool(float(T.max()) <= 110.0)
    out["ceiling_value_C"] = float(T.max())
    # D3: floor — sub-ambient state is clipped up to T_ambient.
    phys = _fresh(np.full(N, -50.0))
    T, _ = phys.step(np.zeros(N), _hvac0())
    out["floor_enforced"] = bool(float(T.min()) >= T_AMB)
    out["floor_value_C"] = float(T.min())
    # D4: cooling engages above T_SAFE and reports P_actual honestly.
    phys = _fresh(np.full(N, 70.0))
    P = np.full(N, 40.0)
    _, P_actual = phys.step(P, _hvac0())
    out["cooling_engaged"] = bool(np.all(phys.cooling_on))
    out["p_actual_hot_equals_P_minus_Pcool"] = bool(
        np.allclose(P_actual, P - P_COOL))
    out["pass"] = bool(out["zero_heat_inlet_equals_ambient"] and out["ceiling_enforced"]
                        and out["floor_enforced"] and out["cooling_engaged"]
                        and out["p_actual_hot_equals_P_minus_Pcool"])
    return out


def exp_cooling_response() -> dict[str, Any]:
    """Test E: cooling off / nominal / net-negative bookkeeping."""
    out: dict[str, Any] = {"test": "E_cooling_response"}
    # E1: below threshold — no cooling, P_actual == P_eff, zero device energy.
    phys = _fresh(np.full(N, 50.0))
    P = np.full(N, 200.0)
    _, P_actual = phys.step(P, _hvac0())
    out["below_threshold_no_cooling"] = bool(
        not np.any(phys.cooling_on) and np.allclose(P_actual, P)
        and phys.cooling_energy_J == 0.0 and phys.cooling_events == 0)
    # E2/E3: hot low-power node — cooling engages; applied power goes negative.
    phys = _fresh(np.full(N, 70.0))
    P = np.full(N, 40.0)
    _, P_actual = phys.step(P, _hvac0())
    out["hot_low_power_p_actual_W"] = float(P_actual[0])
    out["net_negative_documented"] = bool(float(P_actual[0]) == 40.0 - P_COOL)
    out["device_energy_J"] = float(phys.cooling_energy_J)
    out["device_energy_expected_J"] = float(P_COOL * N * DT)
    out["events_edge_counted"] = int(phys.cooling_events)
    # Sustained heat counts once (edge semantics): step again, still hot.
    phys.step(P, _hvac0())
    out["sustained_counts_once"] = bool(int(phys.cooling_events) == N)
    out["pass"] = bool(out["below_threshold_no_cooling"] and out["net_negative_documented"]
                        and out["device_energy_J"] == out["device_energy_expected_J"]
                        and out["sustained_counts_once"])
    return out


def exp_refinement(dts: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125),
                   t_end: float = 30.0) -> dict[str, Any]:
    """Test F: timestep refinement of the pinned replica vs analytic + DOP853."""
    power, t0 = 210.0, 50.0
    P = np.full(N, power)
    hvac = _hvac0()
    t_in_scalar = T_AMB + K_BP * 8.0 * power
    rows = []
    for dt in dts:
        n = int(round(t_end / dt))
        T = np.full(N, t0)
        hist = np.empty(n)
        for k in range(n):
            T = EQ.rk4_step(T, P, hvac, R_MAT, dt=dt, **_kw())
            hist[k] = T[0]
        times = (np.arange(1, n + 1)) * dt
        expect = REF.rc_step_response(t0, power, t_in_scalar, r_amb=R_AMB,
                                      c_th=C_TH, t=times)
        err = np.abs(hist - expect)
        # Common physical times for cross-dt comparison.
        rows.append({"dt": dt, "steps": n, "max_abs_err_C": float(err.max()),
                     "rms_err_C": float(np.sqrt((err**2).mean())),
                     "final_abs_err_C": float(err[-1])})
    orders = []
    for a, b in zip(rows, rows[1:]):
        if a["max_abs_err_C"] > 0 and b["max_abs_err_C"] > 0:
            orders.append(float(np.log2(a["max_abs_err_C"] / b["max_abs_err_C"])))
    # Independent cross-check: finest replica vs DOP853 reference.
    T_in = EQ.rack_inlet(P, hvac, n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                         k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG)
    _, ref = REF.solve_ivp_reference(np.full(N, t0), P, T_in, R_MAT,
                                     r_amb=R_AMB, c_th=C_TH, t_end=t_end,
                                     n_points=31)
    T = np.full(N, t0)
    n = int(round(t_end / dts[-1]))
    for _ in range(n):
        T = EQ.rk4_step(T, P, hvac, R_MAT, dt=dts[-1], **_kw())
    xcheck = float(np.max(np.abs(T - ref[-1])))
    observed = orders[-1] if orders else None
    return {"test": "F_refinement", "t_end_s": t_end, "rows": rows,
            "observed_orders": orders, "finest_vs_dop853_C": xcheck,
            "pass": bool(observed is not None and 3.5 <= observed <= 4.5
                          and xcheck < 1e-6)}


def run_all() -> dict[str, Any]:
    """Execute the full battery; return the machine-readable report."""
    t0 = time.perf_counter()
    results = [exp_zero_equilibrium(), exp_rc_response(),
               exp_coupled_equilibrium(), exp_boundaries(),
               exp_cooling_response(), exp_refinement()]
    return {"battery": "thermal_verification_v1",
            "source": "legacy Scripts/core.py via fidelity-pinned replica",
            "experiments": results,
            "all_pass": bool(all(r["pass"] for r in results)),
            "elapsed_s": round(time.perf_counter() - t0, 3)}


def main() -> int:
    """Write the battery report under results/phase2/ (no tracked files touched)."""
    out_dir = REPO_ROOT / "results" / "phase2"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = run_all()
    (out_dir / "verification_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"all_pass": report["all_pass"],
                      "elapsed_s": report["elapsed_s"],
                      "out": "results/phase2/verification_report.json"}, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
