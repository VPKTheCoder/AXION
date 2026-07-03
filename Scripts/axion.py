"""
================================================================================
 PROJECT AXION
 AI Data-Centre Thermal Optimisation — Load-Balancing + Dynamic Power Capping
 HP 15-hr1000TU · Intel Core Ultra 5 125H · 16 GB DDR5
================================================================================

CRITIQUE OF "BINARY WORKLOAD-SUBSTITUTION" SCHEDULING
------------------------------------------------------
A simpler thermal scheduler might, when a node overheats, just swap that
node's task for a lighter one (e.g. replace a GEMM job with an Embedding
lookup). This has two structural problems:

  1. WORK IS DESTROYED, NOT MOVED.  The GEMM job that was "swapped away"
     still needs to be computed by *someone* — it cannot simply vanish.
     A scheduler that reports "0 cooling events" by silently dropping the
     hottest jobs is not solving the thermal problem, it is hiding it.

  2. ALL-OR-NOTHING GRANULARITY.  Routing a node from GEMM (350 W) to
     Embedding (40 W) is a 89% power cut in one step. There is no way to
     ask for "GEMM at 70% power" — which is exactly what GPU power-capping
     (NVML set_power_limit) and reduced-precision execution provide on
     real hardware.

PROJECT AXION'S APPROACH
-------------------------
AXION reformulates the problem as TWO separable, conserved sub-problems:

  A. LOAD BALANCING (every step, O(N log N) greedy):
     The same multiset of jobs must be processed every step — AXION decides
     WHICH NODE runs WHICH JOB, routing high-power jobs to the coolest
     available nodes. Total work is conserved: it is a *permutation*,
     not a substitution.

  B. POWER-CAP & FACILITY TUNING (every 30 s, or immediately if a fast
     thermal transient is detected — see PBD below):
     Simulated Annealing chooses a per-node power-cap level
     c ∈ {1.00, 0.85, 0.70, 0.55, 0.40} and a per-rack HVAC boost level
     ∈ {0,1,2,3}. Capping trades power for latency
     (L_eff = L_rated / c), so each workload type has a hardware-derived
     ALLOWED_CAPS set (computed below from L_eff ≤ L_MAX = 19.5 ms).

PREDICTIVE BURST DETECTION (PBD)
----------------------------------
The 30-second scheduling cadence is too slow for a burst onset: at
ΔP ≈ 300 W, dT/dt ≈ ΔP/C ≈ 3.3 °C/s (computed below), so 5 seconds of
delay costs ~16 °C. AXION monitors the *measured* slope (T_now-T_prev)/dt
every second; if any node exceeds PBD_THRESH = 1.0 °C/s, an emergency
mini-SA (300 iterations) runs immediately to retune caps/HVAC.

BASELINE FOR COMPARISON
-------------------------
"No AXION" = identity assignment (node n always runs job n's request,
no load balancing), cap = 1.0 always (no proactive capping), HVAC = 0,
with only the HARDWARE'S OWN reactive thermal throttle:
  T > T_safe        → forced cap = 0.5  (typical GPU thermal throttle)
  T > T_safe + 5°C  → forced cap = 0.3  (emergency throttle)
If throttling is insufficient and T keeps rising, the facility's
evaporative cooling activates exactly as in the baseline thermal model
(same WUE formula as previous work: water = P_cool·n_hot·dt / (η·L_v)).

EXPLICIT MODELLING ASSUMPTIONS (stated up front, not hidden)
--------------------------------------------------------------
  • Throughput ∝ power within a node's operating envelope (standard
    simplifying proxy; real perf/W curves flatten near the power floor).
  • Capping increases latency proportionally: L_eff = L_rated / c
    (consistent with DVFS — lower clock ⇒ proportionally slower).
  • Gradient (backprop/training, 24 ms) is NOT subject to the 19.5 ms
    inference SLO — training jobs have no per-request latency
    requirement. (Verified below: 24/1.0 = 24 > 19.5, so Gradient would
    have an EMPTY allowed-cap set under the inference SLO — a contradiction
    that disappears once Gradient is correctly classified as a batch job.)
  • HVAC fan power follows P_fan ∝ level² (simplified affinity-law
    proxy for flow³ vs Δflow; real curves are steeper).
  • All physics (Newton-cooling network + ASHRAE rack-inlet bypass +
    RK4 integration) is identical to the previously-validated model —
    these are standard textbook relations, not project-specific.

Install:  pip install numpy scipy matplotlib
Run:      python axion.py
================================================================================
"""

import math, time, random, warnings
import numpy as np
import scipy.stats as sst
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator

warnings.filterwarnings("ignore")
random.seed(123); np.random.seed(123)

from core import *
from core import _R_EFF, _TAU_EFF, _IDX_N, _EW, _EW_SUM, _EI, _EJ

# ══════════════════════════════════════════════════════════════════════════════
#  PREDICTOR  — one-shot linearised model, extended for cap & HVAC
#
#    T_pred[n] = T_now[n] + ΔP[n]·R_eff[n] + ΔT_in[n]
#
#  ΔP[n]    = cap[n]·P_job[n]  −  P_cur[n]
#  ΔT_in[n] = T_in_candidate[rack(n)] − T_in_current[rack(n)]
#
#  (h/τ ≈ 30/2.6 ≈ 11.5 ⇒ scale = 1−e^(−11.5) ≈ 1.000, so the one-step
#   exponential-decay shift IS the ~30-second-ahead steady-state shift —
#   no separate multi-step rollout is needed; this was verified previously.)
# ══════════════════════════════════════════════════════════════════════════════
def rack_inlet_vec(P_eff: np.ndarray, hvac: np.ndarray) -> np.ndarray:
    T_in = np.full(N, CFG["T_AMBIENT"], dtype=np.float32)
    for rack in range(CFG["N_RACKS"]):
        lo,hi=rack*NPR,rack*NPR+NPR
        Q=float(np.sum(P_eff[lo:hi]))
        T_in[lo:hi]=(CFG["T_AMBIENT"]+CFG["K_BYPASS"]*Q
                     -CFG["HVAC_DEGREE_PER_LEVEL"]*hvac[rack])
    return T_in


def predict(T_now, P_cur, Tin_cur, P_job, cap, hvac, job_types=None, perm=None, tucker_table=None, tucker_trust=0.0):
    """Return T_pred (N,) for candidate (cap,hvac) given fixed job assignment."""
    P_cand   = cap*P_job
    Tin_cand = rack_inlet_vec(P_cand, hvac)
    dP   = P_cand - P_cur
    dTin = Tin_cand - Tin_cur
    T_phys = np.clip(T_now + dP*_R_EFF + dTin, CFG["T_AMBIENT"], 110.0)
    if tucker_table is not None and tucker_trust > 0:
        T_tucker = tucker_table[np.arange(N), job_types[perm]]
        return tucker_trust * T_tucker + (1. - tucker_trust) * T_phys
    return T_phys


def coupling_gradient(T_pred):
    if len(_EI)==0: return 0.0
    return float(np.dot(_EW, np.abs(T_pred[_EI]-T_pred[_EJ])))/_EW_SUM


# ══════════════════════════════════════════════════════════════════════════════
#  AXION CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════
class AxionController:
    def __init__(self):
        self.perm  = np.arange(N, dtype=np.int32)         # job j -> node perm[j]... assign node n to job perm[n]
        self.cap   = np.ones(N, dtype=np.float32)
        self.hvac  = np.zeros(CFG["N_RACKS"], dtype=np.int32)
        self.P_cur = np.zeros(N, dtype=np.float32)
        self.Tin_cur = np.full(N, CFG["T_AMBIENT"], dtype=np.float32)
        self.T_prev  = np.full(N, CFG["T_INIT_MU"], dtype=np.float32)
        self.sa_log_full = []
        self.sa_log_pbd  = []
        self.sa_calls    = 0
        self.pbd_triggers= 0
        self.tucker_table = None   # (N, W_DIM) — updated after each Tucker fit
        self.tucker_trust = 0.0    # ramps from 0 → 1 over first 5 fits
        # Adaptive PBD: rolling buffer of max per-step slopes (last 30 steps)
        self._slope_hist = np.zeros(30, dtype=np.float32)
        self._slope_ptr  = 0

    # ── A. Load balancing (every step, greedy O(N log N)) ──────────────────────
    def load_balance(self, job_types: np.ndarray, T_now: np.ndarray) -> np.ndarray:
        """
        Sort jobs by power (desc), nodes by temperature (asc).
        Assign hottest-job-first to coolest-node-first, restricted to
        nodes where (job_type, current cap) is SLO-feasible.
        Returns perm: perm[n] = job index assigned to node n.
        """
        job_power = W_POW[job_types]
        job_order = np.argsort(-job_power)          # hottest jobs first
        node_order = np.argsort(T_now)               # coolest nodes first

        perm = -np.ones(N, dtype=np.int32)
        used_nodes = np.zeros(N, dtype=bool)

        for j in job_order:
            w = job_types[j]
            placed = False
            for n in node_order:
                if used_nodes[n]:
                    continue
                if any(abs(self.cap[n] - c) < 1e-4 for c in ALLOWED_CAPS[w]):
                    perm[n] = j; used_nodes[n] = True; placed = True
                    break
            if not placed:
                # fall back: any free node, force cap=1.0 for this node
                for n in node_order:
                    if not used_nodes[n]:
                        perm[n]=j; used_nodes[n]=True
                        self.cap[n]=1.0
                        break
        return perm

    # ── B. SA objective ──────────────────────────────────────────────────────
    def _objective(self, cap, hvac, T_now, P_cur, Tin_cur, job_types, perm):
        P_job = W_POW[job_types[perm]]
        T_pred = predict(T_now, P_cur, Tin_cur, P_job, cap, hvac, job_types, perm, self.tucker_table, self.tucker_trust)
        T_max  = float(T_pred.max())
        grad   = coupling_gradient(T_pred)
        excess = float(np.mean(np.maximum(0., T_pred-CFG["T_SAFE"])))
        ideal  = float(np.sum(P_job))
        actual = float(np.sum(cap*P_job))
        loss   = 1.0 - actual/max(ideal,1e-9)
        fan    = float(np.sum(hvac))
        return (CFG["OBJ_ALPHA"]*T_max + CFG["OBJ_BETA"]*grad
              + CFG["OBJ_GAMMA"]*excess + CFG["OBJ_ZETA"]*loss
              + CFG["OBJ_ETA"]*fan)

    # ── B. Simulated annealing over (cap, hvac) ────────────────────────────────
    def _run_sa(self, n_iters, T_now, P_cur, Tin_cur, job_types, perm):
        t0=time.perf_counter()
        cap  = self.cap.copy()
        hvac = self.hvac.copy()

        # Ensure feasibility of initial cap w.r.t. current perm's job types
        for n in range(N):
            w = job_types[perm[n]]
            if not any(abs(cap[n] - c) < 1e-4 for c in ALLOWED_CAPS[w]):
                cap[n] = 1.0

        E = self._objective(cap,hvac,T_now,P_cur,Tin_cur,job_types,perm)
        cap_b, hvac_b, E_b = cap.copy(), hvac.copy(), E
        tau = CFG["SA_TAU_INIT"]

        for _ in range(n_iters):
            if random.random() < 0.75:
                n = random.randint(0,N-1)
                w = job_types[perm[n]]
                old = cap[n]
                cap[n] = random.choice(ALLOWED_CAPS[w])
                E2 = self._objective(cap,hvac,T_now,P_cur,Tin_cur,job_types,perm)
                dE = E2-E
                if dE<0 or random.random()<math.exp(max(-700,-dE/(tau+1e-12))):
                    E=E2
                else:
                    cap[n]=old
            else:
                r = random.randint(0,CFG["N_RACKS"]-1)
                old = hvac[r]
                hvac[r] = random.choice(HVACS)
                E2 = self._objective(cap,hvac,T_now,P_cur,Tin_cur,job_types,perm)
                dE = E2-E
                if dE<0 or random.random()<math.exp(max(-700,-dE/(tau+1e-12))):
                    E=E2
                else:
                    hvac[r]=old
            if E<E_b:
                cap_b,hvac_b,E_b = cap.copy(),hvac.copy(),E
            tau*=CFG["SA_COOL_RATE"]
            if tau<CFG["SA_TAU_MIN"]: break

        ms=(time.perf_counter()-t0)*1000
        return cap_b, hvac_b, ms

    # ── Per-step controller call ───────────────────────────────────────────────
    def step(self, step_idx, T_now, job_types):
        max_slope = float(np.max((T_now - self.T_prev)/CFG["DT"]))

        # Adaptive PBD gate: fire only when slope exceeds BOTH the hard floor
        # AND (rolling mean + 2σ) — suppresses sustained-regime false positives.
        self._slope_hist[self._slope_ptr % 30] = max_slope
        self._slope_ptr += 1
        hist     = self._slope_hist if self._slope_ptr >= 30 else self._slope_hist[:self._slope_ptr]
        adaptive = float(hist.mean()) + 2.0*float(hist.std()) if len(hist) > 5 else 1e9
        pbd_fire = bool(max_slope > CFG["PBD_THRESH"] and max_slope > adaptive)

        # A. Greedy load balancing — every step
        self.perm = self.load_balance(job_types, T_now)

        # B. SA — every SCHED_PERIOD steps, or immediately on PBD trigger
        run_full = (step_idx % CFG["SCHED_PERIOD"] == 0)
        if run_full or pbd_fire:
            n_iters = CFG["SA_N_ITERS_FULL"] if run_full else CFG["SA_N_ITERS_PBD"]
            cap_b,hvac_b,ms = self._run_sa(n_iters, T_now, self.P_cur,
                                            self.Tin_cur, job_types, self.perm)
            self.cap, self.hvac = cap_b, hvac_b
            self.sa_calls += 1
            if run_full: self.sa_log_full.append(ms)
            if pbd_fire and not run_full:
                self.sa_log_pbd.append(ms); self.pbd_triggers += 1

        # Final assignment for this step
        P_job  = W_POW[job_types[self.perm]]
        P_eff  = (self.cap*P_job).astype(np.float32)
        self.Tin_cur = rack_inlet_vec(P_eff, self.hvac)
        self.P_cur   = P_eff
        self.T_prev  = T_now.copy()
        return P_eff, self.hvac.copy(), self.perm.copy(), self.cap.copy()


class GreedyBaseline:
    """Temperature-aware greedy: same load_balance as AXION, no SA or Tucker."""
    def __init__(self):
        self.hvac = np.zeros(CFG["N_RACKS"], dtype=np.int32)
    def step(self, step_idx, T_now, job_types):
        job_power = W_POW[job_types]
        job_order = np.argsort(-job_power)
        node_order = np.argsort(T_now)
        perm = np.zeros(N, dtype=np.int32)
        used = np.zeros(N, dtype=bool)
        for j in job_order:
            for n in node_order:
                if not used[n]:
                    perm[n] = j; used[n] = True; break
        cap = np.ones(N, dtype=np.float32)
        P_eff = (cap * W_POW[job_types[perm]]).astype(np.float32)
        return P_eff, self.hvac.copy(), perm, cap


# ══════════════════════════════════════════════════════════════════════════════
#  BASELINE CONTROLLER  — identity assignment + reactive hardware throttle
# ══════════════════════════════════════════════════════════════════════════════
class BaselineController:
    def __init__(self):
        self.hvac = np.zeros(CFG["N_RACKS"], dtype=np.int32)

    def step(self, step_idx, T_now, job_types):
        perm = np.arange(N, dtype=np.int32)     # identity: node n <- job n
        cap  = np.ones(N, dtype=np.float32)
        # Reactive hardware thermal throttle
        cap[T_now > CFG["T_SAFE"]]    = 0.5
        cap[T_now > CFG["T_SAFE"]+5]  = 0.3
        P_job = W_POW[job_types[perm]]
        P_eff = (cap*P_job).astype(np.float32)
        return P_eff, self.hvac.copy(), perm, cap


# ══════════════════════════════════════════════════════════════════════════════
#  METRICS
# ══════════════════════════════════════════════════════════════════════════════
class Metrics:
    def __init__(self, label):
        self.label=label
        self.T_peak=[]; self.T_mean=[]; self.T_snap=[]
        self.cool_cum=[]; self.slo_ok=[]; self.retention=[]
        self.wue=[]; self.e_kwh=[]; self.hvac_energy_J=0.0
        self.rack_mean=[]
        self._phys=None

    def record(self, T, P_eff, P_actual, job_types, perm, cap, hvac, phys):
        self._phys=phys
        self.T_peak.append(float(T.max()))
        self.T_mean.append(float(T.mean()))
        self.T_snap.append(T.copy())
        self.cool_cum.append(phys.cooling_events)

        # SLO: for SLO-sensitive jobs, L_eff = L_rated/cap must be <= L_MAX
        ok=True
        for n in range(N):
            w=job_types[perm[n]]
            if w in CFG["SLO_SENSITIVE"]:
                if W_LAT[w]/cap[n] > CFG["L_MAX"]+1e-6:
                    ok=False; break
        self.slo_ok.append(ok)

        ideal = float(np.sum(W_POW[job_types]))
        actual= float(np.sum(P_eff))
        self.retention.append(100.0*actual/ideal)

        # WUE — water from last-resort evaporative cooling only
        Q_cool_J = CFG["P_COOLING"]*float(np.sum(phys.cooling_on))*CFG["DT"]
        W_water  = Q_cool_J/(0.80*2_257_000.)
        E_kWh    = float(np.sum(P_actual))*CFG["DT"]/3_600_000.
        self.e_kwh.append(E_kWh)
        self.wue.append(W_water/max(E_kWh,1e-12))

        # HVAC fan energy
        fan_W = CFG["HVAC_FAN_BASE_W"]*np.sum(hvac.astype(np.float64)**2)
        self.hvac_energy_J += fan_W*CFG["DT"]

        rm=[T[r*NPR:(r+1)*NPR].mean() for r in range(CFG["N_RACKS"])]
        self.rack_mean.append(np.array(rm,dtype=np.float32))

    @property
    def slo_pct(self): return 100.*sum(self.slo_ok)/max(len(self.slo_ok),1)
    @property
    def avg_retention(self): return float(np.mean(self.retention))
    @property
    def total_water_L(self): return float(np.dot(self.wue,self.e_kwh))


# ══════════════════════════════════════════════════════════════════════════════
#  SIMULATION LOOP
# ══════════════════════════════════════════════════════════════════════════════
def run():
    print("="*70)
    print("  PROJECT AXION — AI Data-Centre Thermal Optimisation")
    print("  HP 15-hr1000TU · Core Ultra 5 125H · 16 GB DDR5")
    print("="*70)
    print(f"\n  Nodes={N}  Steps={CFG['SIM_STEPS']}  SCHED_PERIOD={CFG['SCHED_PERIOD']}s")
    print(f"  R_eff range = {_R_EFF.min():.4f}-{_R_EFF.max():.4f} °C/W   "
          f"tau_eff range = {_TAU_EFF.min():.2f}-{_TAU_EFF.max():.2f}s")
    print(f"\n  ALLOWED_CAPS (derived from L_eff = L_rated/cap <= {CFG['L_MAX']}ms):")
    for w,name in enumerate(CFG["WORKLOAD_NAMES"]):
        tag = "no SLO (batch)" if w not in CFG["SLO_SENSITIVE"] else ""
        print(f"    {name:6s} lat={W_LAT[w]:5.1f}ms  allowed={ALLOWED_CAPS[w]}  {tag}")

    phys_a = ThermalPhysics(seed=0)   # AXION
    phys_b = ThermalPhysics(seed=0)   # Baseline
    phys_g = ThermalPhysics(seed=0)   # Greedy
    axion  = AxionController()
    base   = BaselineController()
    greedy = GreedyBaseline()
    met_a  = Metrics("AXION")
    met_b  = Metrics("Baseline")
    met_g  = Metrics("Greedy")

    t0=time.perf_counter()
    for step in range(CFG["SIM_STEPS"]):
        jt = demand(step)

        # AXION
        T_now_a = phys_a.T.astype(np.float32)
        P_eff_a, hvac_a, perm_a, cap_a = axion.step(step, T_now_a, jt)
        T_a, P_act_a = phys_a.step(P_eff_a, hvac_a)
        met_a.record(T_a, P_eff_a, P_act_a, jt, perm_a, cap_a, hvac_a, phys_a)

        # Baseline
        T_now_b = phys_b.T.astype(np.float32)
        P_eff_b, hvac_b, perm_b, cap_b = base.step(step, T_now_b, jt)
        T_b, P_act_b = phys_b.step(P_eff_b, hvac_b)
        met_b.record(T_b, P_eff_b, P_act_b, jt, perm_b, cap_b, hvac_b, phys_b)

        # Greedy
        T_now_g = phys_g.T.astype(np.float32)
        P_eff_g, hvac_g, perm_g, cap_g = greedy.step(step, T_now_g, jt)
        T_g, P_act_g = phys_g.step(P_eff_g, hvac_g)
        met_g.record(T_g, P_eff_g, P_act_g, jt, perm_g, cap_g, hvac_g, phys_g)

        if step%100==0 and step>0:
            sa_str=(f"SA{np.mean(axion.sa_log_full[-3:]):.1f}ms"
                    if axion.sa_log_full else "SA(warm)")
            eta=(time.perf_counter()-t0)/step*(CFG['SIM_STEPS']-step)
            print(f"  Step {step:4d}  T_peak AXION={T_a.max():.1f}°C "
                  f"Base={T_b.max():.1f}°C Greedy={T_g.max():.1f}°C Δ={T_b.max()-T_a.max():+.1f}°C  |  "
                  f"Cool A={phys_a.cooling_events} B={phys_b.cooling_events} G={phys_g.cooling_events}  |  "
                  f"Ret A={met_a.retention[-1]:.0f}% B={met_b.retention[-1]:.0f}% G={met_g.retention[-1]:.0f}%  |  "
                  f"{sa_str}  PBD={axion.pbd_triggers}  ETA {eta:.0f}s")

    print(f"\n  Done in {time.perf_counter()-t0:.1f}s")
    return met_a, met_b, met_g, axion


# ══════════════════════════════════════════════════════════════════════════════
#  RESULTS
# ══════════════════════════════════════════════════════════════════════════════
def summarise(ma, mb, mg, axion):
    print("\n"+"="*70)
    print("  RESULTS — AXION vs Greedy vs Baseline")
    print("="*70)

    def row(lbl,bv,gv,av,unit="",fmt=".2f",note=""):
        if abs(bv)<1e-9 and abs(av)<1e-9 and abs(gv)<1e-9:
            tag="  –"
        elif abs(bv)<1e-9:
            tag="  (Base=0)"
        else:
            pct=(bv-av)/abs(bv)*100
            sym="▼" if pct>0 else "▲" if pct<0 else "–"
            tag=f"  {sym}{abs(pct):.1f}%"
        print(f"  {lbl:<28s} Base:{bv:{fmt}}{unit}  Greedy:{gv:{fmt}}{unit}  AXION:{av:{fmt}}{unit}"+tag
              +(f"  ({note})" if note else ""))

    print(f"\n  -- Temperature")
    row("Mean peak temp",np.mean(mb.T_peak),np.mean(mg.T_peak),np.mean(ma.T_peak),"°C")
    row("Worst-case peak",max(mb.T_peak),max(mg.T_peak),max(ma.T_peak),"°C")
    row("Mean temperature",np.mean(mb.T_mean),np.mean(mg.T_mean),np.mean(ma.T_mean),"°C")

    print(f"\n  -- Cooling / Water")
    Cb,Cg,Ca=mb.cool_cum[-1],mg.cool_cum[-1],ma.cool_cum[-1]
    print(f"  {'Cooling events':<28s} Base:{Cb}  Greedy:{Cg}  AXION:{Ca}  Δ={Cb-Ca:+d}")
    row("Total water (L)",mb.total_water_L,mg.total_water_L,ma.total_water_L,"",".6f")
    row("Cooling energy (kJ)",mb._phys.cooling_energy_J/1e3,
        mg._phys.cooling_energy_J/1e3,
        ma._phys.cooling_energy_J/1e3," kJ",".2f")

    print(f"\n  -- Throughput (work conserved — same job multiset both sides)")
    row("Mean throughput retention",np.mean(mb.retention),np.mean(mg.retention),np.mean(ma.retention),"%",".1f")
    row("Worst-case retention",min(mb.retention),min(mg.retention),min(ma.retention),"%",".1f")

    print(f"\n  -- SLO  (L_MAX={CFG['L_MAX']}ms, inference workloads only)")
    row("SLO compliance",mb.slo_pct,mg.slo_pct,ma.slo_pct,"%",".1f")

    print(f"\n  -- HVAC (AXION only)")
    print(f"  {'HVAC fan energy':<28s} AXION: {ma.hvac_energy_J/1e3:.2f} kJ")

    print(f"\n  -- SA performance")
    if axion.sa_log_full:
        print(f"  {'Full SA wall time':<28s} "
              f"{np.mean(axion.sa_log_full):.2f}±{np.std(axion.sa_log_full):.2f}ms"
              f"  max {max(axion.sa_log_full):.2f}ms  (n={len(axion.sa_log_full)})")
    if axion.sa_log_pbd:
        print(f"  {'PBD mini-SA wall time':<28s} "
              f"{np.mean(axion.sa_log_pbd):.2f}ms  (n={len(axion.sa_log_pbd)})")
    print(f"  {'PBD triggers':<28s} {axion.pbd_triggers}")
    print(f"  {'Total SA calls':<28s} {axion.sa_calls}")

    # Statistics — paired t-test on per-step T_peak (AXION should be <= baseline)
    t,p = sst.ttest_rel(mb.T_peak, ma.T_peak, alternative='greater')
    diff = np.array(mb.T_peak)-np.array(ma.T_peak)
    d = float(diff.mean()/(diff.std(ddof=1)+1e-12))
    print(f"\n  -- Statistics  (paired t-test on per-step T_peak, n={len(mb.T_peak)})")
    print(f"  t={t:.3f}  p={p:.6f}  {'(sig)' if p<0.05 else '(n.s.)'}")
    print(f"  Cohen's d (paired) = {d:.3f}")
    print(f"  Mean reduction = {diff.mean():+.3f}°C   95% CI "
          f"({diff.mean()-sst.t.ppf(0.975,len(diff)-1)*diff.std(ddof=1)/math.sqrt(len(diff)):.3f}, "
          f"{diff.mean()+sst.t.ppf(0.975,len(diff)-1)*diff.std(ddof=1)/math.sqrt(len(diff)):.3f})°C")
    print("="*70)


# ══════════════════════════════════════════════════════════════════════════════
#  PLOTTING
# ══════════════════════════════════════════════════════════════════════════════
def plot(ma, mb, mg, axion):
    S=CFG["SIM_STEPS"]; steps=np.arange(S)
    BG,BG2,BG3="#0d0d10","#16161c","#1e1e26"
    FG,FG2,FG3="#e8e6dc","#8a8a84","#3a3a44"
    TC,BC,GC,SC,WC,MC="#4dabf7","#ff7043","#69db7c","#ff4d6d","#ffd43b","#e03131"  # MC=Magentaish/Red for Greedy

    fig=plt.figure(figsize=(22,14),facecolor=BG)
    gs=gridspec.GridSpec(3,3,figure=fig,hspace=0.52,wspace=0.37,
                         left=0.06,right=0.97,top=0.93,bottom=0.06)

    def ax_(ax,title=""):
        ax.set_facecolor(BG2)
        for s in ax.spines.values(): s.set_color(FG3)
        ax.tick_params(colors=FG2,labelsize=9)
        ax.xaxis.label.set_color(FG2); ax.xaxis.label.set_fontsize(9)
        ax.yaxis.label.set_color(FG2); ax.yaxis.label.set_fontsize(9)
        ax.grid(color=BG3,lw=0.7,ls="--")
        if title: ax.set_title(title,color=FG,fontsize=9.5,fontweight="bold",pad=7)
        return ax
    lkw=dict(fontsize=8,facecolor=BG2,edgecolor=FG3,labelcolor=FG)

    # P1 — Peak temperature
    ax1=ax_(fig.add_subplot(gs[0,:2]),"Peak Node Temperature — AXION vs Greedy vs Baseline")
    ax1.fill_between(steps,mb.T_peak,ma.T_peak,
                     where=[b>a for b,a in zip(mb.T_peak,ma.T_peak)],
                     color=GC,alpha=0.13,label="AXION cooler region")
    ax1.plot(steps,mb.T_peak,color=BC,lw=1.3,alpha=0.85,label="Baseline (reactive throttle)")
    ax1.plot(steps,mg.T_peak,color=MC,lw=1.4,alpha=0.85,label="Greedy (sorting only)")
    ax1.plot(steps,ma.T_peak,color=TC,lw=1.5,alpha=0.95,label="AXION")
    ax1.axhline(CFG["T_SAFE"],color=SC,lw=1.1,ls="--",label=f"T_safe={CFG['T_SAFE']}°C")
    for lo,hi,lbl in [(150,260,"Burst 1\n(GEMM)"),(350,450,"Burst 2\n(Gradient)")]:
        ax1.axvspan(lo,hi,color=WC,alpha=0.07)
        ax1.text((lo+hi)/2,CFG["T_SAFE"]+1.5,lbl,ha='center',fontsize=7.5,color=WC,alpha=0.9)
    ax1.set_xlim(0,S); ax1.set_xlabel("Step (s)"); ax1.set_ylabel("°C")
    ax1.legend(**lkw,ncol=3,loc="upper left")

    # P2 — Cooling events
    ax2=ax_(fig.add_subplot(gs[0,2]),"Cumulative Cooling Events")
    ax2.plot(steps,mb.cool_cum,color=BC,lw=1.3,label="Baseline")
    ax2.plot(steps,mg.cool_cum,color=MC,lw=1.3,label="Greedy")
    ax2.plot(steps,ma.cool_cum,color=TC,lw=1.3,label="AXION")
    ax2.set_xlabel("Step"); ax2.set_ylabel("Events")
    ax2.legend(**lkw); ax2.set_xlim(0,S)
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))

    # P3 — Throughput retention
    ax3=ax_(fig.add_subplot(gs[1,0]),"Throughput Retention  (work conserved)")
    ax3.plot(steps,mb.retention,color=BC,lw=1.2,alpha=0.85,label="Baseline")
    ax3.plot(steps,mg.retention,color=MC,lw=1.2,alpha=0.85,label="Greedy")
    ax3.plot(steps,ma.retention,color=TC,lw=1.3,alpha=0.95,label="AXION")
    ax3.axhline(100,color=GC,lw=1.0,ls=":",label="100% (no capping)")
    ax3.set_xlabel("Step"); ax3.set_ylabel("% of ideal throughput")
    ax3.set_ylim(0,105); ax3.legend(**lkw); ax3.set_xlim(0,S)

    # P4 — SLO compliance (rolling)
    ax4=ax_(fig.add_subplot(gs[1,1]),"SLO Compliance  (rolling 30-step)")
    sm=30
    slo_b=np.convolve([float(x) for x in mb.slo_ok],np.ones(sm)/sm,'valid')*100
    slo_a=np.convolve([float(x) for x in ma.slo_ok],np.ones(sm)/sm,'valid')*100
    ax4.plot(slo_b,color=BC,lw=1.3,label="Baseline")
    ax4.plot(slo_a,color=TC,lw=1.3,label="AXION")
    ax4.axhline(99.5,color=GC,lw=1.0,ls="--",label="99.5% target")
    ax4.set_ylim(0,105); ax4.set_xlabel("Step"); ax4.set_ylabel("% SLO-compliant")
    ax4.legend(**lkw)

    # P5 — Per-rack temperature (AXION solid, Baseline dashed)
    ax5=ax_(fig.add_subplot(gs[1,2]),"Per-Rack Mean Temp  (solid=AXION, dashed=Base)")
    rack_b=np.array(mb.rack_mean); rack_a=np.array(ma.rack_mean)
    for r,rc in enumerate([TC,GC,WC,SC]):
        ax5.plot(steps,rack_b[:,r],color=rc,lw=1.0,ls="--",alpha=0.5)
        ax5.plot(steps,rack_a[:,r],color=rc,lw=1.4,ls="-",alpha=0.9,label=f"Rack {r}")
    ax5.axhline(CFG["T_SAFE"],color=SC,lw=0.8,ls="--",alpha=0.5)
    ax5.set_xlabel("Step"); ax5.set_ylabel("°C"); ax5.set_xlim(0,S)
    ax5.legend(**lkw,ncol=2)

    # P6 — SA wall time (full + PBD)
    ax6=ax_(fig.add_subplot(gs[2,0]),"SA Wall-Clock Time  (full vs PBD mini-SA)")
    if axion.sa_log_full:
        ax6.bar(range(len(axion.sa_log_full)),axion.sa_log_full,
                color=TC,alpha=0.85,width=0.8,label=f"Full SA (n={len(axion.sa_log_full)})")
    if axion.sa_log_pbd:
        offset=len(axion.sa_log_full)
        ax6.bar(range(offset,offset+len(axion.sa_log_pbd)),axion.sa_log_pbd,
                color=WC,alpha=0.85,width=0.8,label=f"PBD mini-SA (n={len(axion.sa_log_pbd)})")
    ax6.set_xlabel("SA invocation index"); ax6.set_ylabel("ms")
    ax6.legend(**lkw)

    # P7 — Cap-level usage heatmap over time (AXION)
    ax7=ax_(fig.add_subplot(gs[2,1]),"AXION Power-Cap Usage  (fraction of nodes at each level)")
    # Reconstruct cap distribution per step from retention isn't exact;
    # instead show retention histogram as proxy for cap aggressiveness
    ax7.hist(ma.retention,bins=20,color=TC,alpha=0.75,label="AXION")
    ax7.hist(mb.retention,bins=20,color=BC,alpha=0.55,label="Baseline")
    ax7.set_xlabel("Throughput retention (%)"); ax7.set_ylabel("Steps")
    ax7.legend(**lkw)

    # P8 — Summary text
    ax8=ax_(fig.add_subplot(gs[2,2]),"Summary")
    ax8.axis("off")
    diff=np.array(mb.T_peak)-np.array(ma.T_peak)
    t,p=sst.ttest_rel(mb.T_peak,ma.T_peak,alternative='greater')
    d=float(diff.mean()/(diff.std(ddof=1)+1e-12))
    lines=[
        f"Mean T_peak reduction: {diff.mean():+.2f}°C",
        f"Worst-case T_peak: Base={max(mb.T_peak):.1f}  AXION={max(ma.T_peak):.1f}",
        f"Cooling events: {mb.cool_cum[-1]} -> {ma.cool_cum[-1]}",
        f"Water used: {mb.total_water_L:.4f}L -> {ma.total_water_L:.4f}L",
        "",
        f"Throughput retention:",
        f"  Base mean={np.mean(mb.retention):.1f}%  worst={min(mb.retention):.1f}%",
        f"  AXION mean={np.mean(ma.retention):.1f}%  worst={min(ma.retention):.1f}%",
        "",
        f"SLO: Base={mb.slo_pct:.1f}%  AXION={ma.slo_pct:.1f}%",
        f"HVAC energy: {ma.hvac_energy_J/1e3:.2f} kJ",
        "",
        f"Paired t={t:.2f}  p={p:.5f}  d={d:.2f}",
        f"PBD triggers: {axion.pbd_triggers} / {axion.sa_calls} SA calls",
    ]
    for i,line in enumerate(lines):
        col=GC if ("->" in line and "AXION" in line) or "reduction" in line else FG2
        ax8.text(0.04,0.95-i*0.072,line,transform=ax8.transAxes,
                 fontsize=9,color=col,fontfamily="monospace")

    fig.text(0.5,0.972,
             "PROJECT AXION  ·  Load-balancing + dynamic power capping + PBD + HVAC  ·  "
             "HP 15-hr1000TU (Core Ultra 5 125H · 16 GB DDR5)",
             ha="center",va="top",color=FG,fontsize=10,fontweight="bold")

    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.abspath(os.path.join(script_dir, "..", "Assets"))
    os.makedirs(assets_dir, exist_ok=True)
    out = os.path.join(assets_dir, "AXION_Results.png")
    plt.savefig(out,dpi=160,bbox_inches="tight",facecolor=BG); plt.close()
    print(f"\n  Plot saved -> {out}")


# ══════════════════════════════════════════════════════════════════════════════
if __name__=="__main__":
    ma,mb,mg,axion=run()
    summarise(ma,mb,mg,axion)
    plot(ma,mb,mg,axion)
    print("\n  Done.\n")
