import math
import sys
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ══════════════════════════════════════════════════════════════════════════════
#  UNIFIED CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
CFG = dict(
    N_NODES=32, N_RACKS=4, NODES_PER_RACK=8, N_WORKLOADS=6,
    SIM_STEPS=600, DT=1.0, SCHED_PERIOD=30,

    T_AMBIENT=24.0, T_SAFE=65.0, T_WARN=60.0,
    T_INIT_MU=44.0, T_INIT_SIGMA=4.0,
    C_THERMAL=90.0, R_AMB=0.145,
    R_INTRA_RACK=0.40, R_INTER_RACK=4.00,
    K_BYPASS=5e-5,
    P_COOLING=280.0,

    WORKLOAD_POWER=np.array([350.,280.,210.,75.,40.,370.], dtype=np.float32),
    WORKLOAD_NAMES=["GEMM","Attn","FFN","KV","Embed","Grad"],
    WORKLOAD_LAT=np.array([14., 19., 9., 3.5, 1., 24.], dtype=np.float32),
    L_MAX=19.5,
    SLO_SENSITIVE=[0,1,2,3,4],

    POWER_CAP_LEVELS=[1.00, 0.85, 0.70, 0.55, 0.40],
    HVAC_LEVELS=[0,1,2,3],
    HVAC_DEGREE_PER_LEVEL=0.5,
    HVAC_FAN_BASE_W=15.0,

    SA_TAU_INIT=15.0, SA_TAU_MIN=0.01, SA_COOL_RATE=0.995,
    SA_N_ITERS_FULL=1500, SA_N_ITERS_PBD=300,
    SA_N_ITERS=1200,          # Used by tats_simulation
    SA_SWAP_PROB=0.20,        # Used by tats_simulation

    PBD_THRESH=0.90 * 370.0 / 90.0,
    
    OBJ_ALPHA=0.50, OBJ_BETA=0.20, OBJ_GAMMA=0.30,
    OBJ_ZETA=20.0, OBJ_ETA=0.10,

    # TATS specifics
    T_WINDOW=240, N_SENSORS=4,
    TUCKER_RANKS=[16,4,48,6],
    COUPLING_THRESH=0.15,
    REFIT_THRESH=1.0,
)

N       = CFG["N_NODES"]
W_DIM   = CFG["N_WORKLOADS"]
W_POW   = CFG["WORKLOAD_POWER"]
W_LAT   = CFG["WORKLOAD_LAT"]
NPR     = CFG["NODES_PER_RACK"]
RACK_OF = np.repeat(np.arange(CFG["N_RACKS"]), NPR)
CAPS    = CFG["POWER_CAP_LEVELS"]
HVACS   = CFG["HVAC_LEVELS"]

ALLOWED_CAPS = []
for w in range(W_DIM):
    if w in CFG["SLO_SENSITIVE"]:
        allowed = [c for c in CAPS if W_LAT[w]/c <= CFG["L_MAX"] + 1e-9]
    else:
        allowed = list(CAPS)
    ALLOWED_CAPS.append(allowed)

def _build_R():
    R = np.full((N,N), CFG["R_INTER_RACK"], dtype=np.float64)
    for rack in range(CFG["N_RACKS"]):
        lo, hi = rack*NPR, rack*NPR+NPR
        for i in range(lo,hi):
            for j in range(lo,hi):
                if i!=j:
                    R[i,j]=CFG["R_INTRA_RACK"]*(0.7+0.3*abs(i-j)/NPR)
    np.fill_diagonal(R, np.inf)
    return R

_R_MAT  = _build_R()
_INV_R  = np.where(np.isfinite(_R_MAT), 1.0/_R_MAT, 0.0)
_R_EFF  = (1.0/(1.0/CFG["R_AMB"] + _INV_R.sum(axis=1))).astype(np.float32)
_TAU_EFF= CFG["C_THERMAL"]*_R_EFF

_EI, _EJ = np.where(np.triu(_INV_R, k=1) > 0)
_EW      = _INV_R[_EI,_EJ]
_EW_SUM  = float(_EW.sum()) if len(_EW) else 1.0
_IDX_N   = np.arange(N, dtype=np.int32)
_TAU_ISO = float(CFG["C_THERMAL"] * CFG["R_AMB"])

# ══════════════════════════════════════════════════════════════════════════════
#  UNIFIED THERMAL PHYSICS
# ══════════════════════════════════════════════════════════════════════════════
class ThermalPhysics:
    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        self.T = np.zeros(N, dtype=np.float64)
        for rack in range(CFG["N_RACKS"]):
            lo, hi = rack*NPR, rack*NPR+NPR
            self.T[lo:hi] = rng.normal(CFG["T_INIT_MU"]+rack*3.0, CFG["T_INIT_SIGMA"], NPR)
        self.T = np.clip(self.T, CFG["T_AMBIENT"]+1, 60.0)
        self.R_mat = _R_MAT.copy()
        self.assignment = np.zeros(N, dtype=np.int32)  # for TATS read_sensors compatibility
        self.cooling_on = np.zeros(N, dtype=bool)
        self.cooling_events = 0
        self.cooling_energy_J = 0.0

    def rack_inlet(self, P_eff, hvac_levels=None):
        T_in = np.full(N, CFG["T_AMBIENT"])
        for rack in range(CFG["N_RACKS"]):
            lo,hi=rack*NPR,rack*NPR+NPR
            Q = float(np.sum(P_eff[lo:hi]))
            hvac_val = hvac_levels[rack] if hvac_levels is not None else 0
            T_in[lo:hi] = (CFG["T_AMBIENT"] + CFG["K_BYPASS"]*Q
                          - CFG["HVAC_DEGREE_PER_LEVEL"]*hvac_val)
        return T_in

    def _dTdt(self, T, P_eff, T_in):
        Q_amb   = (T - T_in)/CFG["R_AMB"]
        Q_inter = np.sum((T[:,None]-T[None,:])/self.R_mat, axis=1)
        return (P_eff - Q_amb - Q_inter)/CFG["C_THERMAL"]

    def step(self, P_eff: np.ndarray, hvac_levels: np.ndarray = None):
        dt = CFG["DT"]
        prev = self.cooling_on.copy()
        self.cooling_on = self.T > CFG["T_SAFE"]
        self.cooling_events += int(np.sum(self.cooling_on & ~prev))
        self.cooling_energy_J += CFG["P_COOLING"]*float(np.sum(self.cooling_on))*dt

        P_actual = P_eff.copy().astype(np.float64)
        P_actual[self.cooling_on] -= CFG["P_COOLING"]

        T_in = self.rack_inlet(P_actual, hvac_levels)
        k1 = self._dTdt(self.T,             P_actual, T_in)
        k2 = self._dTdt(self.T+dt/2*k1,    P_actual, T_in)
        k3 = self._dTdt(self.T+dt/2*k2,    P_actual, T_in)
        k4 = self._dTdt(self.T+dt*k3,      P_actual, T_in)
        self.T = np.clip(self.T+dt/6*(k1+2*k2+2*k3+k4), CFG["T_AMBIENT"], 110.0)
        return self.T.copy().astype(np.float32), P_actual

    def step_assignment(self, assignment: np.ndarray):
        """Helper for TATS which passes assignment instead of P_eff."""
        self.assignment = assignment.copy()
        P_eff = W_POW[assignment]
        T_new, _ = self.step(P_eff, None)
        return T_new

    def read_sensors(self):
        """Used by TATS."""
        T = self.T.astype(np.float32)
        T_in = self.rack_inlet(W_POW[self.assignment]).astype(np.float32)
        out = np.empty((N, CFG["N_SENSORS"]), dtype=np.float32)
        out[:,0] = T    + np.random.normal(0, 0.25, N)
        out[:,1] = T-4. + np.random.normal(0, 0.40, N)
        out[:,2] = T-2. + np.random.normal(0, 0.30, N)
        out[:,3] = T_in + np.random.normal(0, 0.30, N)
        return out

# ══════════════════════════════════════════════════════════════════════════════
#  UNIFIED DEMAND GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
def demand(step: int) -> np.ndarray:
    d = ((np.arange(N)+step//10)%W_DIM).astype(np.int32)
    if 150<=step<260: d[16:]=0   
    if 350<=step<450: d[24:]=5   
    return d
