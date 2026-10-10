# PARAMETER_PROVENANCE.md — P2.6 Registry (no invented uncertainties)

> Classes: **toy** (demonstration choice) · **heuristic** (unvalidated proxy) ·
> **derived** (computed from equations/code) · **standard-constant** (textbook value,
> not facility evidence) · **unknown** (no basis recorded). Unknown uncertainty is
> recorded as **unknown**, never as an invented interval. No literature value below
> is claimed to validate the simulation.

| Parameter | Value | Unit | Meaning | Source | Provenance | Range / uncertainty |
|---|---|---|---|---|---|---|
| N_NODES / N_RACKS / NODES_PER_RACK | 32 / 4 / 8 | count | topology | `core.py:14` | toy | n/a (scenario choice) |
| SIM_STEPS / DT / SCHED_PERIOD | 600 / 1.0 / 30 | steps·s·s | horizon/step/cadence | `core.py:15` | toy | DT refinement verified numerically (F), not physically |
| T_AMBIENT | 24.0 | °C | boundary temperature | `core.py:17` | toy | unknown |
| T_SAFE / T_WARN | 65.0 / 60.0 | °C | control thresholds | `core.py:17` | toy | **experimental criteria, not hardware limits** |
| T_INIT_MU/SIGMA, +3 °C/rack, clip 60 | 44 / 4 / … | °C | hot-start init | `core.py:18,100-101` | toy | unknown; pre-loads near-threshold states |
| C_THERMAL | 90.0 | J/K | lumped nodal capacitance | `core.py:19` | toy | unknown |
| R_AMB | 0.145 | K/W | ambient resistance | `core.py:19` | toy | unknown |
| R_INTRA_RACK / R_INTER_RACK | 0.40 / 4.00 (+distance taper) | K/W | coupling | `core.py:20,69-78` | toy | unknown |
| K_BYPASS | 5e-5 | K/W (implicit) | recirculation | `core.py:21` | heuristic | unknown; authority only 0.148 K max |
| P_COOLING | 280.0 | W | emergency subtraction | `core.py:22` | toy | unknown; unbounded simultaneous use |
| WORKLOAD_POWER 350…370 | 6-vector | W | per-class power | `core.py:24` | toy | unknown |
| WORKLOAD_LAT 14…24 | 6-vector | ms | per-class latency | `core.py:26` | toy | unknown |
| L_MAX | 19.5 | ms | inference SLO | `core.py:27` | toy | unknown; Gradient conflict (D-03) |
| POWER_CAP_LEVELS | 5 levels | fraction | cap actions | `core.py:30` | toy | discrete by construction |
| HVAC_LEVELS / HVAC_DEG | {0..3} / 0.5 | level·K/level | HVAC actions | `core.py:31-33` | toy / heuristic | unknown |
| HVAC_FAN_BASE_W | 15.0 | W/level² (implicit) | fan proxy coefficient | `core.py:33` | heuristic | unknown (affinity-law form unvalidated) |
| SA hyper-parameters (τ, rates, iters) | various | mixed | optimizer | `core.py:35-38` | heuristic | unknown; variance unmeasured (E-08) |
| PBD_THRESH = 0.9·370/90 | 3.70 | °C/s | burst floor | `core.py:40` | derived (from toy power/C) | exceeds canonical burst slope 3.33 (A-02) |
| OBJ weights α/β/γ/ζ/η | 0.5/0.2/0.3/20/0.1 | mixed | SA objective | `core.py:42-43` | heuristic | unknown |
| T_WINDOW / N_SENSORS / TUCKER_RANKS | 240/4/[16,4,48,6] | mixed | TATS geometry | `core.py:46-47` | heuristic | sensor/workload ranks uncompressed (A-04) |
| η_cool / L_v | 0.80 / 2 257 000 | –/J/kg | water proxy | `tats:366-367` | heuristic / standard-constant | η unattributed; L_v textbook (100 °C value; T-dependence unmodeled) |
| τ_iso / τ_eff / R_eff | 13.05 s / ~3.2 s / ~0.035 K/W | s·K/W | derived scales | derived from above | derived | exact given toy inputs |

Tests using each parameter: equation suite (C, R_amb, DT, K_bypass, HVAC_deg),
verification battery (time constants, thresholds), ledger (P_cool, L_v path),
HVAC suite (levels, PBD-adjacent slopes), metrics (L_MAX scopes).
