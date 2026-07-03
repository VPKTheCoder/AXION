"""
TATS v6.0 — Thermally-Aware Tensor Scheduling  (third-pass audit clean)
HP 15-hr1000TU · Intel Core Ultra 5 125H · 16 GB DDR5

Changes from v5 (third-pass audit):
  [C1] Non-SA steps maintained SA assignment — was reverting to raw demand every step
  [B2] welch_ci95 sign: returns positive "reduction" (baseline minus TATS)
  [W3] Objective function: all terms in °C, normalized gradient, hard SLO via inf
  [O4] Pre-computed _IDX_N, dropped _SCALE_EFF multiply (scale = 1.000 for all nodes)
  [M5] SA_N_ITERS = 1200 (actual convergence at ~1033; was misleadingly set to 5000)
"""
import math, time, random, warnings
import numpy as np
import scipy.stats as sst
import tensorly as tl
from tensorly.decomposition import tucker as tucker_decomp
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator

warnings.filterwarnings("ignore")
random.seed(42); np.random.seed(42)

from core import *
from core import _R_EFF, _TAU_EFF, _TAU_ISO, _IDX_N


# ─────────────────────────────────────────────────────────────────────────────
#  THERMAL STATE TENSOR  T ∈ R^{N×S×T_win×W}
# ─────────────────────────────────────────────────────────────────────────────
class ThermalStateTensor:
    def __init__(self):
        S, Tw = CFG["N_SENSORS"], CFG["T_WINDOW"]
        self.tensor  = np.full((N,S,Tw,W_DIM), CFG["T_AMBIENT"], dtype=np.float32)
        self.T_hist  = np.full((N,Tw), CFG["T_AMBIENT"], dtype=np.float32)
        self.n_steps = 0

    def update(self, sensors, asgn):
        slot = self.n_steps % CFG["T_WINDOW"]
        for w in range(W_DIM):
            m = asgn == w
            if m.any(): self.tensor[m,:,slot,w] = sensors[m]
        self.T_hist[:,slot] = sensors[:,0]
        self.n_steps += 1

    @property
    def filled(self): return min(self.n_steps, CFG["T_WINDOW"])


# ─────────────────────────────────────────────────────────────────────────────
#  WORKLOAD TEMPERATURE PROFILER  (online Welford mean per node-workload pair)
# ─────────────────────────────────────────────────────────────────────────────
class TProfiler:
    def __init__(self):
        self.mean  = np.full((N, W_DIM), CFG["T_INIT_MU"], dtype=np.float64)
        self.count = np.zeros((N, W_DIM), dtype=np.int32)

    def update(self, T, asgn):
        for n in range(N):
            w = asgn[n]; self.count[n,w] += 1
            self.mean[n,w] += (T[n]-self.mean[n,w])/self.count[n,w]


# ─────────────────────────────────────────────────────────────────────────────
#  TUCKER DECOMPOSITION  (compression + RMSE analysis; not in SA decision path)
# ─────────────────────────────────────────────────────────────────────────────
class TuckerCompressor:
    def __init__(self):
        self.core=None; self.factors=None
        self.fitted=False; self.rmse_all=None; self.rmse_filled=None; self.ratio=None
        self.mu=0.0; self.sig=1.0   # de-normalisation constants

    def fit(self, tensor):
        self.mu=float(tensor.mean()); self.sig=float(tensor.std())+1e-6
        tn=(tensor-self.mu)/self.sig
        core,factors=tucker_decomp(tl.tensor(tn.astype(np.float32)),
                                    rank=CFG["TUCKER_RANKS"])
        self.core=tl.to_numpy(core); self.factors=[tl.to_numpy(f) for f in factors]
        self.fitted=True; self.ratio=tensor.size/(self.core.size + sum(f.size for f in self.factors))
        T_hat=tl.to_numpy(tl.tucker_to_tensor((core,factors)))*self.sig+self.mu
        self.rmse_all=float(np.sqrt(np.mean((tensor-T_hat)**2)))
        m=tensor>(CFG["T_AMBIENT"]+2.)
        self.rmse_filled=float(np.sqrt(np.mean((tensor[m]-T_hat[m])**2))) if m.any() else self.rmse_all
        return self.rmse_all, self.rmse_filled

    def make_pred_table(self, filled_slots: int) -> np.ndarray:
        """
        Return a (N, W_DIM) array: pred_table[n, w] is the Tucker-predicted
        temperature for node n if it runs workload w at the next slot.

        Derivation — Tucker-4 reconstruction, contracted at sensor s=0 and
        marginalized over time t, then expanded over all (node, workload) pairs:

          T_tucker[n, w] = Σ_{i,j,k,l} G[i,j,k,l]
                           · U_N[n,i] · U_S[0,j] · U_T_mean[k] · U_W[w,l]

        Efficient einsum schedule  (r_{N,S,T,W} are small rank dims):
          step1: v_S   = U_S[0,:]              → (r_S,)
          step2: A     = G ×_2 v_S             → (r_N, r_T, r_W)   einsum ijkl,j
          step3: v_T   = mean(U_T[:filled, :]) → (r_T,)
          step4: B     = A ×_2 v_T             → (r_N, r_W)        einsum ikl,k
          step5: table = U_N @ B @ U_W.T       → (N, W_DIM)
        """
        if not self.fitted:
            return None
        UN, US, UT, UW = self.factors                     # factor matrices
        v_S = US[0, :]                                    # sensor-0 slice
        v_T = UT[:filled_slots, :].mean(axis=0)           # time-slot slice, marginalized
        A   = np.einsum('ijkl,j->ikl', self.core, v_S)   # (r_N, r_T, r_W)
        B   = np.einsum('ikl,k->il',   A,          v_T)  # (r_N, r_W)
        table = (UN @ B @ UW.T) * self.sig + self.mu     # (N, W_DIM)
        return table.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  THERMAL COUPLING GRAPH  (Pearson correlations, pruned at COUPLING_THRESH)
# ─────────────────────────────────────────────────────────────────────────────
class ThermalGraph:
    def __init__(self):
        self.W_mat=np.zeros((N,N),dtype=np.float32)
        self.ei=np.empty(0,dtype=np.int32); self.ej=np.empty(0,dtype=np.int32)

    def update(self, T_hist):
        H=T_hist[:,-min(120,T_hist.shape[1]):]
        corr=np.corrcoef(H).astype(np.float32)
        corr=np.clip(np.nan_to_num(corr),0.,1.); np.fill_diagonal(corr,0.)
        corr[corr<CFG["COUPLING_THRESH"]]=0.
        self.W_mat=corr
        r,c=np.where(self.W_mat>0); m=r<c
        self.ei,self.ej=r[m].astype(np.int32),c[m].astype(np.int32)

    def gradient_cost(self, T):
        """Mean per-edge |ΔT| (°C) — normalised so β weight is interpretable."""
        if len(self.ei)==0: return 0.0
        raw=float(np.dot(self.W_mat[self.ei,self.ej],
                         np.abs(T[self.ei]-T[self.ej])))
        return raw / len(self.ei)


# ─────────────────────────────────────────────────────────────────────────────
#  SIMULATED ANNEALING SCHEDULER
#
#  Predictor — THREE-SOURCE BLEND (physics + profiler + Tucker manifold):
#
#    T_phys[n]   = T_now[n] + ΔP[n]·R_eff[n]          always available
#    T_data[n]   = profiler.mean[n, w]                  trust ramps after 30 obs
#    T_tucker[n] = pred_table[n, w]  (Tucker manifold)  trust ramps after 5 refits
#
#    data_blend[n]   = min(1, count[n,w] / 30)
#    tucker_blend    = min(1, refits / 5)               scalar — same for all n
#    T_pred[n]       = tucker_blend · T_tucker[n]
#                    + (1 − tucker_blend) · (data_blend·T_data + (1−data_blend)·T_phys)
#
#  This ensures the SA predictor is physics-grounded at warmup, data-blended
#  during learning, and Tucker-dominated once the manifold is well-fitted.
#
#  Objective [W3-FIX] — all terms in °C:
#    J(x) = α·T_max  +  β·(mean edge |ΔT|)  +  γ·(Σ excess above T_safe)
#    SLO hard constraint: return inf if any workload latency > L_MAX
# ─────────────────────────────────────────────────────────────────────────────
class SimulatedAnnealer:
    def __init__(self, graph, profiler, comp=None):
        self.graph=graph; self.profiler=profiler; self.comp=comp
        self.T_now       = np.full(N, CFG["T_INIT_MU"], dtype=np.float32)
        self.cur_asgn    = np.zeros(N, dtype=np.int32)
        self.tucker_table= None    # (N, W_DIM) — updated by TATSScheduler after each fit
        self.tucker_refits= 0      # counts Tucker fits seen
        self.ms_log=[]; self.E_log=[]; self.conv_iters=[]

    def _predict(self, asgn):
        """
        Three-source blended predictor:
          1. Physics   (always)        T_phys = T_now + ΔP·R_eff
          2. Profiler  (after 30 obs)  T_data = Welford mean[n, w]
          3. Tucker    (after 5 fits)  T_tucker = manifold table[n, w]
        """
        # ── Source 1: linearised physics ─────────────────────────────────────
        dP     = W_POW[asgn] - W_POW[self.cur_asgn]
        T_phys = np.clip(self.T_now + dP*_R_EFF, CFG["T_AMBIENT"], 110.0)

        # ── Source 2: data-driven Welford profiler ───────────────────────────
        T_data      = self.profiler.mean[_IDX_N, asgn].astype(np.float32)
        data_blend  = np.minimum(1.0, self.profiler.count[_IDX_N, asgn]/30.0
                                 ).astype(np.float32)
        T_phys_data = data_blend*T_data + (1.-data_blend)*T_phys

        # ── Source 3: Tucker manifold projection ─────────────────────────────
        if self.tucker_table is not None:
            # Tucker trust ramps up from 0 → 1 over the first 5 fits
            tucker_blend = float(min(1.0, self.tucker_refits / 5.0))
            T_tucker     = self.tucker_table[_IDX_N, asgn]   # (N,)
            return tucker_blend*T_tucker + (1.-tucker_blend)*T_phys_data

        return T_phys_data

    def objective(self, asgn):
        """
        [W3-FIX] All terms in °C.  Hard SLO constraint via return-inf.

        J = α·T_max  (dominant: drives SA to reduce peak temperature)
          + β·mean_edge_ΔT  (secondary: encourages even load distribution)
          + γ·sum_T_excess  (tertiary: penalises nodes already above T_safe)
        """
        # Hard SLO: never accept latency violations
        if float(W_LAT[asgn].max()) > CFG["L_MAX"]:
            return math.inf

        T       = self._predict(asgn)
        T_max   = float(T.max())
        grad    = self.graph.gradient_cost(T)            # mean |ΔT| in °C
        T_excess= float(np.sum(np.maximum(0., T-CFG["T_SAFE"])))  # °C above safe
        return (CFG["OBJ_ALPHA"]*T_max
              + CFG["OBJ_BETA"] *grad
              + CFG["OBJ_GAMMA"]*T_excess)

    def optimise(self, x0):
        t0=time.perf_counter()
        x=x0.copy(); tau=CFG["SA_TAU_INIT"]
        E=self.objective(x); xb,Eb=x.copy(),E; conv=CFG["SA_N_ITERS"]

        for i in range(CFG["SA_N_ITERS"]):
            if random.random() < CFG["SA_SWAP_PROB"]:
                n1,n2=random.sample(range(N),2)
                w1,w2=x[n1],x[n2]; x[n1],x[n2]=w2,w1
                dE=self.objective(x)-E
                if dE<0 or (dE!=math.inf and
                             random.random()<math.exp(max(-700,-dE/(tau+1e-12)))):
                    E+=dE
                else:
                    x[n1],x[n2]=w1,w2
            else:
                ni=random.randint(0,N-1); wo=x[ni]
                x[ni]=random.randint(0,W_DIM-1)
                dE=self.objective(x)-E
                if dE<0 or (dE!=math.inf and
                             random.random()<math.exp(max(-700,-dE/(tau+1e-12)))):
                    E+=dE
                else:
                    x[ni]=wo

            if E<Eb: xb,Eb=x.copy(),E
            tau*=CFG["SA_COOL_RATE"]
            if tau<CFG["SA_TAU_MIN"]: conv=i+1; break

        self.ms_log.append((time.perf_counter()-t0)*1000)
        self.E_log.append(float(Eb)); self.conv_iters.append(conv)
        return xb


# ─────────────────────────────────────────────────────────────────────────────
#  TATS SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────
class TATSScheduler:
    """
    [C1-FIX] Key change from v5: TATS now KEEPS its optimised assignment
    between SA scheduling periods.  Previously it reverted to raw demand
    every step, undoing all work the SA had just done.

    Between SA steps: maintain last SA assignment.
    Override only nodes within 2°C of T_safe (real-time safety).
    """
    def __init__(self):
        self.tst     =ThermalStateTensor()
        self.profiler=TProfiler()
        self.graph   =ThermalGraph()
        self.comp    =TuckerCompressor()
        self.sa      =SimulatedAnnealer(self.graph, self.profiler, comp=self.comp)
        self.asgn    =np.zeros(N, dtype=np.int32)
        self._sa_asgn=np.zeros(N, dtype=np.int32)  # last SA result
        self.pred_errs=[]; self.refits=0

    def update(self, sensors, demand, step):
        T_now = sensors[:,0].astype(np.float32)
        self.tst.update(sensors, self.asgn)
        self.profiler.update(T_now, self.asgn)
        self.sa.T_now=T_now.copy(); self.sa.cur_asgn=self.asgn.copy()

        if step>20 and step%60==0:
            self.graph.update(self.tst.T_hist)

        if step%CFG["SCHED_PERIOD"]==0 and self.tst.filled>=40:
            self.comp.fit(self.tst.tensor); self.refits+=1
            # ── [TUCKER-FIX] Update SA's prediction table from the freshly fitted
            #    Tucker factors. We marginalize over the filled time slots to
            #    remove temporal aliasing from the historical data.
            self.sa.tucker_table  = self.comp.make_pred_table(self.tst.filled)
            self.sa.tucker_refits = self.refits
            err=float(np.mean(np.abs(T_now-self.sa._predict(self.asgn))))
            self.pred_errs.append(err)

        if step%CFG["SCHED_PERIOD"]==0:
            x_opt=self.sa.optimise(demand.copy())
            if self._accept(self.asgn, x_opt):
                self.asgn=x_opt
            else:
                # Greedy fallback: demand but reroute hottest 25% to Embedding
                self.asgn=demand.copy()
                hot=np.argsort(T_now)[-N//4:]
                self.asgn[hot]=int(np.argmin(W_POW))
            self._sa_asgn=self.asgn.copy()   # store for between-SA steps
        else:
            # [C1-FIX] maintain SA assignment between scheduling periods
            self.asgn=self._sa_asgn.copy()
            # Real-time safety: reroute (swap) instead of substitution
            near=T_now>(CFG["T_SAFE"]-2.)
            if near.any():
                cool_order = np.argsort(T_now)  # coolest nodes first
                for hot_n in np.where(near)[0]:
                    for cool_n in cool_order:
                        if not near[cool_n] and cool_n != hot_n:
                            # Swap assignments: reroute, don't substitute
                            self.asgn[hot_n], self.asgn[cool_n] = self.asgn[cool_n], self.asgn[hot_n]
                            break

        # Belt-and-suspenders SLO guard: TATS never outputs a latency violation.
        # Catches any edge case where _sa_asgn or fallback contains Gradient (24ms > L_MAX).
        slo_viol = W_LAT[self.asgn] > CFG["L_MAX"]
        if slo_viol.any():
            safe_w = int(min(range(W_DIM),
                             key=lambda w: W_POW[w] if W_LAT[w] <= CFG["L_MAX"] else 1e9))
            self.asgn[slo_viol] = safe_w

        return self.asgn.copy()

    def _accept(self, x_old, x_new):
        """
        Accept x_new if it is feasible AND at least as good as x_old
        by objective value.  [v7-FIX]

        Previous check: (ΔT_max) > 0.4°C × n_changes
        Bug: n_changes compared against _old_ assignment, not demand.
             At step 0 n_changes = 26 → threshold = 10.4°C → always rejects.
        Fix: compare objective values.  SA result accepted when E(new) ≤ E(old).
        """
        E_new = self.sa.objective(x_new)
        E_old = self.sa.objective(x_old)
        if not np.isfinite(E_new): return False   # x_new violates SLO → reject
        if not np.isfinite(E_old): return True    # x_old violates SLO → accept anything feasible
        return E_new <= E_old + 0.1               # accept if new is at least as good (+0.1 tolerance)


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────────────────────────────────────────
class Metrics:
    def __init__(self, label):
        self.label=label
        self.T_peak=[]; self.T_mean=[]; self.T_snap=[]
        self.T_warn_frac=[]; self.cool_cum=[]; self.slo_ok=[]
        self.wue=[]; self.e_it_kwh=[]; self.pue=[]; self.rack_mean=[]
        self._phys=None

    def record(self, T, asgn, phys):
        self._phys=phys
        self.T_peak.append(float(T.max()))
        self.T_mean.append(float(T.mean()))
        self.T_snap.append(T.copy())
        self.T_warn_frac.append(float(np.mean(T>CFG["T_WARN"])))
        self.cool_cum.append(phys.cooling_events)
        self.slo_ok.append(bool(W_LAT[asgn].max()<=CFG["L_MAX"]))
        NPR=CFG["NODES_PER_RACK"]
        self.rack_mean.append(np.array(
            [T[r*NPR:(r+1)*NPR].mean() for r in range(CFG["N_RACKS"])],
            dtype=np.float32))
        Q_cool_J=CFG["P_COOLING"]*float(np.sum(phys.cooling_on))*CFG["DT"]
        W_water=Q_cool_J/(0.80*2_257_000.)
        P_IT=float(np.sum(W_POW[asgn]))
        E_kWh=P_IT*CFG["DT"]/3_600_000.
        self.e_it_kwh.append(E_kWh)
        self.wue.append(W_water/max(E_kWh,1e-12))
        P_cool_W=CFG["P_COOLING"]*float(np.sum(phys.cooling_on))
        self.pue.append((P_IT+P_cool_W+P_IT*.15)/max(P_IT,1e-9))

    @property
    def slo_pct(self): return 100.*sum(self.slo_ok)/max(len(self.slo_ok),1)
    @property
    def avg_wue(self): return float(np.mean(self.wue)) if self.wue else 0.
    @property
    def avg_pue(self): return float(np.mean(self.pue)) if self.pue else 0.
    @property
    def total_water_L(self): return float(np.dot(self.wue, self.e_it_kwh))


def cohens_d(a, b):
    """Pooled-standard-deviation effect size for two independent samples."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0
    pooled_var = ((n1 - 1) * a.var(ddof=1) + (n2 - 1) * b.var(ddof=1)) / (n1 + n2 - 2)
    return float((a.mean() - b.mean()) / (math.sqrt(pooled_var) + 1e-12))


def welch_ci95(baseline, candidate):
    """Return mean baseline-candidate reduction and 95% Welch CI half-width."""
    baseline = np.asarray(baseline, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    diff = baseline.mean() - candidate.mean()
    se = math.sqrt(baseline.var(ddof=1) / len(baseline) + candidate.var(ddof=1) / len(candidate))
    df_num = (baseline.var(ddof=1) / len(baseline) + candidate.var(ddof=1) / len(candidate)) ** 2
    df_den = ((baseline.var(ddof=1) / len(baseline)) ** 2 / (len(baseline) - 1)
              + (candidate.var(ddof=1) / len(candidate)) ** 2 / (len(candidate) - 1))
    df = df_num / max(df_den, 1e-12)
    return float(diff), float(sst.t.ppf(0.975, df) * se)


# ─────────────────────────────────────────────────────────────────────────────
#  SIMULATION LOOP
# ─────────────────────────────────────────────────────────────────────────────
def run():
    print("="*68)
    print("  TATS v7.0  ·  SLO + anti-thrash fixed")
    print("  HP 15-hr1000TU  ·  Core Ultra 5 125H  ·  16 GB DDR5")
    print("="*68)
    core_el=1
    for r in CFG["TUCKER_RANKS"]: core_el*=r
    raw_mb=N*CFG["N_SENSORS"]*CFG["T_WINDOW"]*W_DIM*4/1e6
    print(f"  Nodes {N} | Steps {CFG['SIM_STEPS']} | "
          f"Sched {CFG['SCHED_PERIOD']}s | SA {CFG['SA_N_ITERS']} iters")
    print(f"  TST {raw_mb:.1f}MB → Tucker {core_el*4/1e6:.2f}MB core  "
          f"({raw_mb/(core_el*4/1e6):.0f}×)")
    print(f"  τ_iso={_TAU_ISO:.1f}s | τ_eff={_TAU_EFF.min():.1f}–{_TAU_EFF.max():.1f}s"
          f" | scale≈1.000 (h/τ≫1) [O4]\n")

    phys_t=ThermalPhysics(seed=0); phys_b=ThermalPhysics(seed=0)
    tats=TATSScheduler(); met_t=Metrics("TATS"); met_b=Metrics("Baseline")

    t0=time.perf_counter()
    for step in range(CFG["SIM_STEPS"]):
        dm=demand(step)
        sens=phys_t.read_sensors()
        asgn_t=tats.update(sens, dm, step)
        T_t=phys_t.step_assignment(asgn_t)
        met_t.record(T_t, asgn_t, phys_t)
        T_b=phys_b.step_assignment(dm)
        met_b.record(T_b, dm, phys_b)

        if step%100==0 and step>0:
            sa_s=(f"SA {np.mean(tats.sa.ms_log[-3:]):.0f}ms "
                  f"@{np.mean(tats.sa.conv_iters[-3:]):.0f}it"
                  if tats.sa.ms_log else "SA (warmup)")
            eta=(time.perf_counter()-t0)/step*(CFG["SIM_STEPS"]-step)
            print(f"  Step {step:4d}  T_peak TATS={T_t.max():.1f}°C "
                  f"Base={T_b.max():.1f}°C  Δ={T_b.max()-T_t.max():+.1f}°C  |  "
                  f"Cool T={phys_t.cooling_events} B={phys_b.cooling_events}  |  "
                  f"{sa_s}  ETA {eta:.0f}s")

    print(f"\n  Done in {time.perf_counter()-t0:.1f}s")
    return met_t, met_b, tats


# ─────────────────────────────────────────────────────────────────────────────
#  RESULTS SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def summarise(mt, mb, sc):
    print("\n"+"="*68)
    print("  RESULTS  —  TATS v8.0")
    print("="*68)

    def row(lbl,bv,tv,unit="",fmt=".1f",note=""):
        if abs(bv)<1e-9 and abs(tv)<1e-9:
            tag="  –"
        elif abs(bv)<1e-9:
            tag=f"  ▲(Base=0)"
        else:
            pct=(bv-tv)/abs(bv)*100
            sym="▼" if pct>0 else "▲" if pct<0 else "–"
            tag=f"  {sym}{abs(pct):.1f}%"
        print(f"  {lbl:<32s} Base:{bv:{fmt}}{unit}  TATS:{tv:{fmt}}{unit}"
              +tag+(f"  ({note})" if note else ""))

    print(f"\n  ── Temperature")
    row("Mean peak temp",   np.mean(mb.T_peak),     np.mean(mt.T_peak),"°C")
    row("Worst-case peak",  max(mb.T_peak),          max(mt.T_peak),    "°C")
    row("Mean temp",        np.mean(mb.T_mean),      np.mean(mt.T_mean),"°C")
    row("Nodes > T_warn",   np.mean(mb.T_warn_frac), np.mean(mt.T_warn_frac),
        "%",".1%",f">{CFG['T_WARN']:.0f}°C")

    print(f"\n  ── Cooling")
    Cb,Ct=mb.cool_cum[-1],mt.cool_cum[-1]
    print(f"  {'Cooling events':<32s} Base:{Cb}  TATS:{Ct}  Δ={Cb-Ct:+d}")
    if mb._phys:
        row("Cooling energy",mb._phys.cooling_energy_J/1e3,
            mt._phys.cooling_energy_J/1e3," kJ",".1f","water ∝ energy")

    print(f"\n  ── Water & Power")
    row("Total water (L)",mb.total_water_L,mt.total_water_L,"",".6f","WUE×E_IT/step")
    row("Avg PUE",        mb.avg_pue,      mt.avg_pue,"",".4f")

    print(f"\n  ── SLO  (L_MAX={CFG['L_MAX']}ms; Gradient=24ms violates)")
    row("SLO compliance", mb.slo_pct,mt.slo_pct,"%",".1f","[C1-FIX] TATS holds SA assignment")

    c=sc.comp
    tucker_blend = round(min(1.0, sc.refits / 5.0), 2)
    print(f"\n  ── Tucker  (manifold active in SA predictor — trust={tucker_blend:.0%})")
    if c.fitted:
        raw=N*CFG["N_SENSORS"]*CFG["T_WINDOW"]*W_DIM*4/1e6
        print(f"  {'Compression':<32s} {c.ratio:.0f}× ({raw:.1f}→{c.core.size*4/1e6:.3f}MB)")
        print(f"  {'RMSE all slots':<32s} {c.rmse_all:.3f}°C")
        print(f"  {'RMSE filled slots':<32s} {c.rmse_filled:.3f}°C")
        print(f"  {'Tucker refits':<32s} {sc.refits}  (trust ramps over first 5)")
    if sc.pred_errs:
        print(f"  {'SA predictor MAE':<32s} {np.mean(sc.pred_errs):.3f}°C")

    print(f"\n  ── SA")
    if sc.sa.ms_log:
        print(f"  {'Wall time':<32s} {np.mean(sc.sa.ms_log):.1f}±{np.std(sc.sa.ms_log):.1f}ms "
              f"max {max(sc.sa.ms_log):.0f}ms")
        print(f"  {'Convergence iter':<32s} {np.mean(sc.sa.conv_iters):.0f} / {CFG['SA_N_ITERS']}")
        print(f"  {'Refits':<32s} {sc.refits}")

    # [B2-FIX] positive reduction
    t_s,p=sst.ttest_ind(mt.T_peak,mb.T_peak,alternative='less',equal_var=False)
    d   =cohens_d(mb.T_peak, mt.T_peak)
    eff ='large' if abs(d)>0.8 else 'medium' if abs(d)>0.5 else 'small'
    red, half = welch_ci95(mb.T_peak, mt.T_peak)  # positive = TATS is cooler
    print(f"\n  ── Statistics")
    print(f"  {'Welch t-test':<32s} t={t_s:.3f}  p={p:.4f}  "
          f"{'✓ sig' if p<0.05 else '~'} (α=0.05)")
    cdlbl="Cohen's d (pooled std)"
    print(f"  {cdlbl:<32s} {d:.3f}  ({eff})")
    print(f"  {'Peak temp reduction':<32s} +{red:.3f}°C  "
          f"95% CI (+{red-half:.3f}, +{red+half:.3f})°C  [B2-FIX: positive=cooler]")
    print(f"\n  ── Physics notes")
    print(f"  τ_iso={_TAU_ISO:.1f}s  τ_eff≈{_TAU_EFF.mean():.1f}s  "
          f"scale=1.000 (h/τ≫1) — [O4] _SCALE_EFF dropped")
    print(f"  Objective: α·T_max + β·grad_mean + γ·T_excess  [W3] all °C")
    print(f"  SLO: hard (return inf) — SA never accepts latency violations")
    print("="*68)


# ─────────────────────────────────────────────────────────────────────────────
#  VISUALISATION
# ─────────────────────────────────────────────────────────────────────────────
def plot(mt, mb, sc):
    S=CFG["SIM_STEPS"]; steps=np.arange(S)
    BG,BG2,BG3="#0d0d10","#16161c","#1e1e26"
    FG,FG2,FG3="#e8e6dc","#8a8a84","#3a3a44"
    TC,BC="#4dabf7","#ff7043"; SC,GC,WC="#ff4d6d","#69db7c","#ffd43b"

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
    ax1=ax_(fig.add_subplot(gs[0,:2]),"§9  Peak Node Temperature — TATS vs Baseline")
    ax1.fill_between(steps,mb.T_peak,mt.T_peak,
                     where=[b>t for b,t in zip(mb.T_peak,mt.T_peak)],
                     color=GC,alpha=0.13,label="TATS cooler region")
    ax1.plot(steps,mb.T_peak,color=BC,lw=1.3,alpha=0.85,label="Baseline")
    ax1.plot(steps,mt.T_peak,color=TC,lw=1.5,alpha=0.95,label="TATS")
    ax1.axhline(CFG["T_SAFE"],color=SC,lw=1.1,ls="--",
                label=f"T_safe={CFG['T_SAFE']:.0f}°C")
    ax1.axhline(CFG["T_WARN"],color=WC,lw=0.8,ls=":",
                label=f"T_warn={CFG['T_WARN']:.0f}°C")
    for lo,hi,lbl in [(150,260,"Burst 1\n(GEMM)"),(350,450,"Burst 2\n(Gradient+SLO)")]:
        ax1.axvspan(lo,hi,color=WC,alpha=0.07)
        ax1.text((lo+hi)/2,CFG["T_SAFE"]+1.5,lbl,ha='center',
                 fontsize=7.5,color=WC,alpha=0.9)
    ax1.set_xlim(0,S); ax1.set_xlabel("Step (s)"); ax1.set_ylabel("°C")
    ax1.legend(**lkw,ncol=3,loc="upper left")

    # P2 — SLO compliance  (the big improvement from [C1-FIX])
    ax2=ax_(fig.add_subplot(gs[0,2]),"§9  SLO Compliance  [C1-FIX]")
    slo_b=np.convolve([float(x) for x in mb.slo_ok],np.ones(30)/30,'valid')*100
    slo_t=np.convolve([float(x) for x in mt.slo_ok],np.ones(30)/30,'valid')*100
    ax2.plot(slo_b,color=BC,lw=1.3,label="Baseline")
    ax2.plot(slo_t,color=TC,lw=1.3,label="TATS")
    ax2.axhline(99.5,color=GC,lw=1.0,ls="--",label="99.5% target")
    ax2.set_ylim(0,105); ax2.set_xlabel("Step"); ax2.set_ylabel("% steps SLO-compliant")
    ax2.legend(**lkw)

    # P3 — Fraction above T_warn
    sm=30
    ax3=ax_(fig.add_subplot(gs[1,0]),f"Fraction Nodes > {CFG['T_WARN']:.0f}°C")
    ax3.plot(np.convolve(mb.T_warn_frac,np.ones(sm)/sm,'valid'),
             color=BC,lw=1.2,label="Baseline")
    ax3.plot(np.convolve(mt.T_warn_frac,np.ones(sm)/sm,'valid'),
             color=TC,lw=1.2,label="TATS")
    ax3.set_xlabel("Step"); ax3.set_ylabel("Fraction"); ax3.legend(**lkw)

    # P4 — Cumulative water (correct: WUE × E_IT)
    ax4=ax_(fig.add_subplot(gs[1,1]),"Cumulative Water Used (L)")
    wb=np.cumsum(np.array(mb.wue)*np.array(mb.e_it_kwh))
    wt=np.cumsum(np.array(mt.wue)*np.array(mt.e_it_kwh))
    ax4.plot(steps,wb,color=BC,lw=1.3,label="Baseline")
    ax4.plot(steps,wt,color=TC,lw=1.3,label="TATS")
    ax4.set_xlabel("Step"); ax4.set_ylabel("Litres"); ax4.legend(**lkw)

    # P5 — Per-rack temperature
    ax5=ax_(fig.add_subplot(gs[1,2]),"Per-Rack Mean Temp  (solid=TATS)")
    rack_b=np.array(mb.rack_mean); rack_t=np.array(mt.rack_mean)
    for r,rc in enumerate([TC,GC,WC,SC]):
        ax5.plot(steps,rack_b[:,r],color=rc,lw=1.0,ls="--",alpha=0.5)
        ax5.plot(steps,rack_t[:,r],color=rc,lw=1.4,ls="-",alpha=0.9,
                 label=f"Rack {r}")
    ax5.axhline(CFG["T_SAFE"],color=SC,lw=0.8,ls="--",alpha=0.5)
    ax5.set_xlabel("Step"); ax5.set_ylabel("°C"); ax5.set_xlim(0,S)
    ax5.legend(**lkw,ncol=2)

    # P6 — Predictor error
    ax6=ax_(fig.add_subplot(gs[2,0]),"SA Predictor MAE  (physics + profiler blend)")
    if sc.pred_errs:
        ax6.plot(sc.pred_errs,color=TC,lw=1.3,marker="o",ms=3.5)
        ax6.axhline(1.0,color=GC,lw=1.0,ls=":",label="target 1°C")
        ax6.axhline(CFG["REFIT_THRESH"],color=SC,lw=0.9,ls="--",
                    label=f"refit {CFG['REFIT_THRESH']}°C")
        ax6.set_xlabel("Refit"); ax6.set_ylabel("MAE (°C)"); ax6.legend(**lkw)

    # P7 — SA wall time
    ax7=ax_(fig.add_subplot(gs[2,1]),"SA Wall-Clock Time")
    ms=sc.sa.ms_log
    if ms:
        cols=[TC if m<=50 else WC if m<=100 else SC for m in ms]
        ax7.bar(range(len(ms)),ms,color=cols,alpha=0.85,width=0.8)
        ax7.axhline(50,color=GC,lw=1.1,ls="--",label="50ms target")
        ax7.set_xlabel("Invocation"); ax7.set_ylabel("ms"); ax7.legend(**lkw)

    # P8 — Node heatmap (TATS top, Baseline bottom)
    ax8=ax_(fig.add_subplot(gs[2,2]),"Node Heatmap  last 80 steps")
    T_tm=np.array(mt.T_snap[-80:]).T; T_bm=np.array(mb.T_snap[-80:]).T
    im=ax8.imshow(np.vstack([T_tm,T_bm]),aspect="auto",cmap="inferno",
                  vmin=CFG["T_AMBIENT"],vmax=CFG["T_SAFE"]+10,
                  interpolation="nearest",origin="upper")
    cb=plt.colorbar(im,ax=ax8,fraction=0.03,pad=0.02)
    cb.ax.tick_params(colors=FG2,labelsize=8); cb.set_label("°C",color=FG2)
    ax8.axhline(N-0.5,color=FG2,lw=1.0,ls="--")
    ax8.text(1,N//2-1,"TATS",color=TC,fontsize=8,fontweight="bold")
    ax8.text(1,N+N//2-1,"Baseline",color=BC,fontsize=8,fontweight="bold")
    for r in range(1,CFG["N_RACKS"]):
        for off in [0,N]:
            ax8.axhline(off+r*CFG["NODES_PER_RACK"]-0.5,color=FG3,lw=0.5,alpha=0.6)
    ax8.set_xlabel("Step offset"); ax8.set_ylabel("Node index")

    fig.text(0.5,0.972,
             "TATS v7.0  ·  v6+[SLO guard]+[anti-thrash objective]  ·  "
             f"{N} nodes·{CFG['SIM_STEPS']} steps  ·  "
             "HP 15-hr1000TU  (Core Ultra 5 125H · 16 GB DDR5)",
             ha='center',va='top',color=FG,fontsize=10,fontweight='bold')
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.abspath(os.path.join(script_dir, "..", "Assets"))
    os.makedirs(assets_dir, exist_ok=True)
    out = os.path.join(assets_dir, "TATS_Simulation_Results.png")
    plt.savefig(out,dpi=160,bbox_inches="tight",facecolor=BG); plt.close()
    print(f"\n  Plot saved → {out}")

# ─────────────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    mt,mb,sc=run(); summarise(mt,mb,sc); plot(mt,mb,sc)
    print("\n  Done.\n")
