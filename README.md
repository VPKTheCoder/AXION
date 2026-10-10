# Project AXION

![Project AXION icon](Assets/icon.png)

> **Evidence status (Phases 0–5 audited).** AXION's thermal model is a mathematically
> verified **toy model** — it is **not physically calibrated** and no real-world energy,
> water, or hardware-safety claim is supported. Historical simulation figures below are
> preserved execution records, not superiority evidence. Fair paired-trial comparisons
> found that **greedy workload placement captures essentially all observed peak-temperature
> benefit** over reactive throttling, while the SA-based optimizer adds no demonstrated
> incremental benefit in tested conditions. Details: `audit_phase0/` … `audit_phase5/`.

Project AXION is a research repository for software-only thermal optimization in AI data centers. It contains the original simulation scripts for Thermally-Aware Tensor Scheduling (TATS), Evolutionary Constraint Mapping (ECM), and the AXION controller with predictive burst detection and SLO-aware power capping — plus a reproducibility harness, a verified physics core, a fair controller-comparison pipeline, a real-inference workload bridge, and an interactive 3D demonstrator.

The goal is simple: reduce AI data-center hotspots before they become emergency cooling events, while preserving workload correctness and service-level objectives (SLOs). Instead of relying only on reactive hardware throttling or facility cooling, AXION treats thermal management as a predictive scheduling and control problem.

## Abstract

The rapid proliferation of large language models and dense tensor workloads has drastically increased power densities in AI data centers, resulting in localized hotspots, cooling inefficiencies, and thermal throttling. Traditional reactive cooling mechanisms incur high operational costs and induce latency violations.

Project AXION introduces a proactive thermal management framework that combines Thermally-Aware Tensor Scheduling (TATS), Predictive Burst Detection (PBD), dynamic SLO-aware power capping, and Evolutionary Constraint Mapping (ECM). By modeling the spatial-temporal thermal manifold with Tucker Decomposition and using Simulated Annealing for placement and cap selection, AXION reduces peak temperatures, sharply lowers emergency cooling events, and maintains strict SLO compliance in simulation.

## Core Idea

Modern AI workloads such as GEMM, attention, feed-forward networks, KV-cache operations, embeddings, and gradient updates produce uneven thermal stress. A conventional scheduler often reacts after a device has already crossed a thermal threshold. AXION acts earlier:

1. It predicts how each workload will affect each node.
2. It routes high-power work to cooler nodes without dropping work.
3. It applies only power caps that preserve latency constraints.
4. It detects fast burst onset through temperature slope monitoring.
5. It transfers thermal knowledge to new facilities using sparse sensor observations.

The result is a software-defined thermal controller that can reduce cooling pressure without requiring a new facility design.

## System Architecture

### Thermal Physics Model

AXION uses a physical simulation based on Newton's Law of Cooling and Runge-Kutta 4 (RK4) integration:

```text
C_i dT_i/dt = P_i - (T_i - T_in) / R_amb - sum_j((T_i - T_j) / R_ij)
```

The model includes:

- **Thermal coupling**: Heat from one server bleeds into nearby servers inside a rack and, more weakly, across racks.
- **ASHRAE rack-inlet bypass**: Hot exhaust from heavily loaded racks can recirculate and raise inlet temperature.
- **Emergency cooling dynamics**: Nodes above the safety threshold trigger last-resort evaporative cooling, modeled as water and energy cost.
- **Shared workload profile**: Six AI workload classes with different power and latency characteristics.

The shared constants and physics live in [Scripts/core.py](Scripts/core.py). The verified,
testable re-expression lives in `src/axion/physics/` (RK4 order ~4 demonstrated against
analytic and DOP853 references; see `audit_phase2/THERMAL_VERIFICATION_REPORT.md`).
All thermal constants are **toy/heuristic, uncalibrated** (see `audit_phase2/PARAMETER_PROVENANCE.md`).

### Thermally-Aware Tensor Scheduling (TATS)

TATS is the predictive scheduling layer. It models data-center thermal history as a four-dimensional tensor:

```text
T in R^(nodes x sensors x time x workloads)
```

This tensor records how nodes behave across sensors, history windows, and workload types. To keep the representation tractable, TATS compresses the tensor with Tucker Decomposition. The compressed core and factor matrices are then projected forward to estimate what temperature a node will reach if a particular workload is assigned there.

TATS combines three prediction sources:

- **Physics projection**: A one-step thermal estimate from power deltas and effective resistance.
- **Welford profiler**: Online historical mean for each node-workload pair.
- **Tucker manifold**: A compressed thermal representation that gains trust as more refits complete.

The TATS simulation is implemented in [Scripts/tats_simulation.py](Scripts/tats_simulation.py).

### AXION Controller

The AXION controller is the decision layer. It makes scheduling and power decisions under a strict invariant: work is conserved. Heavy jobs are moved to better nodes; they are not silently removed.

AXION has three main mechanisms:

- **Greedy load balancing**: High-power jobs are assigned to cooler nodes using an `O(N log N)` ordering.
- **Dynamic power capping**: Per-node caps are selected from `{1.00, 0.85, 0.70, 0.55, 0.40}`.
- **Rack HVAC tuning**: Per-rack HVAC boost levels are included in the optimization objective.

For SLO-sensitive workloads, caps are only allowed when effective latency remains within the hard limit:

```text
L_eff = L_rated / cap <= L_MAX
```

The controller is implemented in [Scripts/axion.py](Scripts/axion.py).

### Predictive Burst Detection (PBD)

Standard scheduling periods can be too slow for sudden AI bursts. A high-power transition can drive a node upward by several degrees per second, so waiting for the next full scheduling interval can be too late.

PBD continuously monitors:

```text
dT/dt = (T_now - T_previous) / dt
```

It triggers a fast-path mini Simulated Annealing pass when the slope exceeds both:

- A physical floor threshold.
- A rolling statistical threshold based on recent slope mean and variance.

This catches true thermal transients while avoiding repeated false positives during normal cycling.

> **Audit note:** the canonical run recorded **zero PBD triggers** (floor 3.70 °C/s exceeds the
> canonical burst slope ≈ 3.33 °C/s). PBD calibration is deferred pending a precision/recall rig.

### Simulated Annealing Optimizer

Simulated Annealing evaluates candidate placements, caps, and HVAC levels with an objective that balances:

- Peak temperature reduction.
- Thermal-gradient smoothing.
- Penalty for temperatures above the safe threshold.
- Throughput retention.
- HVAC fan cost.

In the TATS scheduler, infeasible SLO decisions are rejected as hard constraints. In AXION, allowed cap sets are computed from latency limits before optimization.

### Evolutionary Constraint Mapper (ECM)

ECM addresses the cold-start problem. A new facility does not yet have enough thermal history for a mature tensor predictor, so ECM maps a known source facility to a new target facility using sparse sensor observations.

ECM fits a physics-constrained least-squares model over:

- Ambient resistance.
- Rack-level temperature offsets.
- Workload power response.

This gives the new facility a usable thermal profile after a small number of observations, rather than requiring a long warm-up period.

The ECM simulation is implemented in [Scripts/ecm_simulation.py](Scripts/ecm_simulation.py).

## Simulation Setup

The repository models a 32-node AI cluster across 4 racks. Each rack has 8 nodes. The simulation uses 600 time steps and six workload classes:

| Workload | Role | Power Profile |
| --- | --- | --- |
| GEMM | Dense matrix multiplication | High |
| Attention | Transformer attention | High |
| FFN | Feed-forward network | Medium |
| KV | KV-cache operation | Low |
| Embed | Embedding lookup | Very low |
| Grad | Gradient update / batch training | High |

The simulations compare proactive scheduling against reactive baselines that rely on throttling and emergency cooling after hotspots occur.

## Historical Results (preserved simulation records — see evidence note above)

### TATS Results

![TATS Simulation Results](Assets/TATS_Simulation_Results.png)

The TATS simulation showed:

- Mean peak temperature reduction of about `8.06°C`.
- Emergency cooling events reduced from `465` to `0`.
- Total modeled water use reduced to `0`.
- TATS maintained `100%` SLO compliance in the simulation (guard-scoped; the raw baseline scores `0.0%` under the same all-workload scope — see `audit_phase2/LEGACY_METRIC_RECONCILIATION.md`).
- Welch t-test result was statistically significant with a large effect size (per-step inference since withdrawn; trial-level restatement pending).

### AXION Controller Results

![AXION Simulation Results](Assets/AXION_Results.png)

The AXION controller simulation showed:

- Mean peak temperature reduced from `61.64°C` baseline to `57.99°C`.
- Cooling events reduced from `328` baseline events to `4`.
- Total water use reduced by about `98.8%` (modeled proxy, not metered savings).
- Cooling energy reduced by about `98.8%` (device-energy ledger, no COP).
- AXION maintained `100%` SLO compliance (SLO-sensitive scope; Gradient exempt).
- Mean throughput retention remained about `96.4%`.

### ECM Transfer Results

![ECM Phase 2 Results](Assets/ECM_Phase2_Results.png)

The ECM simulation showed:

- Hyperscale B profile RMSE reduced from `5.50°C` naive transfer to about `0.163°C` with `K=20` (static-model fit metric).
- Edge cluster cooling events reduced from `300` to `0` at `K=20` (static-lookup evaluation).
- Hospital AI throughput improved by about `38%` versus naive transfer (mean-power proxy).
- Research HPC converged to near-oracle behavior with sparse observations.

## What the Follow-Up Science Found (Phases 0–5)

- **Phase 0 audit** (`audit_phase0/`): read-only audit; found work-substitution fallbacks, asymmetric SLO enforcement, PBD miscalibration risk, single-run statistics, and uncalibrated constants.
- **Phase 1 reproducibility** (`audit_phase1/`): manifest schema, safe snapshot-copy runner, independent workload/SLO/action validators; all three legacy scripts reproduce as execution records with historical figures untouched.
- **Phase 2 verification** (`audit_phase2/`): RK4 4th-order convergence demonstrated; energy ledger closes to quadrature theory (partial — no COP/chiller); sub-ambient HVAC exploit proven and guarded; canonical metrics defined; Gradient-SLO conflict documented (exempt in caps, bound in TATS scoring).
- **Phase 3 fair comparison** (`audit_phase3/`): 240 paired arms — greedy placement captures essentially all peak benefit over reactive; SA capping adds nothing measurable (all p ≥ 0.23) at ~500× decision cost; predictive term ≡ myopic ablation. Real LFM2.5-230M inference on CPU (8/8 ok) with explicit synthetic thermal bridge; interactive 3D demonstrator with honest source labels.
- **Phase 4 sensitivity** (`audit_phase4/`): OAT over 10 conditions — greedy sign-robust, SA-null decisive (all diffs within ±0.02 °C vs 0.5 °C margin), sub-ambient exploitation grows with thermal stress.
- **Phase 5 calibration** (`audit_phase5/`): **BLOCKED** — no temperature/power source on accessible interfaces (WMI denied, no RAPL, no instruments). Frozen RC contract + measurement pipeline + protocol ready; fitter proven on fixtures with identifiability gates.

## Research Summary

Project AXION demonstrates that data-center thermal management can be treated as a tensor-compressed spatial routing problem rather than a purely reactive cooling problem. Its main research contributions are:

- A thermal state tensor that captures node, sensor, time, and workload interactions.
- A Tucker-compressed predictor that makes workload placement thermally aware.
- A work-conserving scheduler that reroutes jobs instead of dropping them.
- SLO-aware power caps derived from workload latency constraints.
- Predictive Burst Detection for sudden thermal transients.
- ECM transfer learning for fast deployment in new facilities.

The broader implication — still to be validated on metered hardware — is that software schedulers can reduce physical cooling demand and water use by avoiding thermal saturation before it occurs.

## Repository Map

Legacy baseline (frozen at `a8aec0c`; do not modify):

- [Home.md](Home.md): Project landing page and main index.
- [Notes/Project_AXION_Research_Paper.md](Notes/Project_AXION_Research_Paper.md): Draft research paper.
- [Notes/Project_AXION_Explanation.md](Notes/Project_AXION_Explanation.md): Technical explanation of the system.
- [Scripts/core.py](Scripts/core.py): Shared simulation constants and thermal physics.
- [Scripts/tats_simulation.py](Scripts/tats_simulation.py): TATS simulation and result plot generation.
- [Scripts/ecm_simulation.py](Scripts/ecm_simulation.py): ECM transfer simulation and result plot generation.
- [Scripts/axion.py](Scripts/axion.py): AXION controller simulation and result plot generation.
- [Assets/icon.png](Assets/icon.png): Primary project icon.

Revival infrastructure (`src/axion/`):

- `config/`, `experiments/` (manifest, RNG streams, safe storage, legacy runner), `constraints/` (workload/SLO/action validators), `metrics/` (canonical metrics), `legacy/` (snapshot helpers).
- `physics/` (verified equations, analytical references, energy ledger, HVAC guards, verification battery).
- `sim/` (shared thermal env, scenario library, fair-comparison harness, sensitivity battery), `controllers/` (reactive/greedy/axion/myopic policies).
- `workloads/` (real LFM2.5-230M inference + explicit thermal bridge), `measurement/` (schema, pipeline, frozen calibration contract, fitter).
- `service/` (local HTTP API + 3D frontend backend), `deployment/` (modes, policy gate, shadow replay).
- `frontend/` (Three.js 3D demonstrator, offline-capable).

Audits and evidence: `audit_phase0/` … `audit_phase5/` (phase reports; immutable), `results/` (untracked run records; never committed).

## Run

### Interactive 3D demonstrator (recommended)

```bash
pip install -r requirements.txt   # + torch/transformers for real inference (optional)
$env:PYTHONPATH = "src"
python -m axion.service.server --port 8765
# open http://127.0.0.1:8765/
```

### Legacy scripts (safe runner only — never in place; in-place runs overwrite tracked figures)

```bash
$env:PYTHONPATH = "src"
python -m axion.experiments.runner tats --seed 0
python -m axion.experiments.runner axion --seed 0
python -m axion.experiments.runner ecm --seed 0
```

### Tests

```bash
python -m pytest tests/ -q   # 146 tests; live-model test gated by AXION_LIVE_INFERENCE=1
```

## Dependencies

The project uses:

- `numpy`
- `scipy`
- `matplotlib`
- `tensorly`

Install them with:

```bash
pip install -r requirements.txt
```

Optional (real inference + richer UX): `torch`, `transformers`, `scikit-learn`, `psutil`, `flask`/`fastapi` (installed in dev; only stdlib + numpy/scipy required for sim/tests).

## Conclusion

Project AXION bridges tensor mathematics, thermal physics, and systems scheduling. By combining Tucker Decomposition, Simulated Annealing, SLO-aware power capping, and predictive burst detection, it shows a practical path toward lower water use, lower emergency cooling demand, and more stable AI data-center operation without discarding workloads or violating latency constraints.

That path is now an inspectable, reproducible, challengeable system — with its placement mechanism supported in simulation, its optimizer economics refuted-in-conditions, and physical calibration explicitly blocked pending instrumentation. A skeptical researcher can distinguish what AXION measures, what its equations calculate, what its assumptions imply, what its experiments support, and what must still be proven.
