# THERMAL_MODEL_SPECIFICATION.md — P2.1 Formal Model (reconstructed from implementation)

> Authority: `Scripts/core.py` at `a8aec0c` (source of truth). Comments and
> `Notes/` were used as hints only; every equation below was traced to executed
> code. New test code: `src/axion/physics/equations.py` (mirror, `dt` parameterized).
> Fidelity pin: `tests/test_physics_equations.py::test_replica_matches_legacy[_nonuniform]`
> (replica == legacy to float32 output rounding, < 5e-6 at ~60 °C). PASSING.

## 1. State, inputs, actuators, units

| Symbol | Meaning | Unit | Code |
|---|---|---|---|
| `T ∈ R^32` | node temperatures (state) | °C | `core.py:97` (`float64` in state, `float32` on output, `:139`) |
| `P_eff ∈ R^32` | applied workload power per node (heat input) | W | `step(P_eff, …)`, `:123` |
| `hvac ∈ {0,1,2,3\}^4` | per-rack HVAC boost | level (dimensionless) | `:123`, `CFG HVAC_LEVELS` |
| `T_in ∈ R^32` | per-node inlet temperature (piecewise rack-constant) | °C | `:108-116` |
| `R_amb = 0.145` | ambient thermal resistance | K/W | `CFG:19` |
| `R_mat` | pairwise coupling resistances (diag = +inf) | K/W | `:69-78` (`R_INTRA_RACK=0.40` distance-scaled, `R_INTER_RACK=4.00`) |
| `C = 90.0` | lumped nodal thermal capacitance | J/K | `CFG:19` |
| `T_amb = 24.0` | ambient/boundary temperature | °C | `CFG:17` |
| `K_bypass = 5e-5` | rack recirculation coefficient | K/W (implicit — see dimensional audit) | `CFG:21` |
| `HVAC_deg = 0.5` | inlet offset per HVAC level | K/level | `CFG:32` |
| `P_cool = 280.0` | emergency-cooling power subtraction | W | `CFG:22` |
| `dt = DT = 1.0` | integration timestep | s | `CFG:15` |

## 2. Governing equations (as implemented)

**EQ-ODE** (`core.py:118-121`):
```text
C_i dT_i/dt = P_i - (T_i - T_in,i)/R_amb - Σ_j (T_i - T_j)/R_ij     [W == W]
```
**EQ-INLET** (`core.py:108-116`):
```text
T_in[rack] = T_amb + K_bypass · Σ_{i∈rack} P_applied,i - HVAC_deg · hvac[rack]   [°C]
```
Note: inlet is computed from `P_actual` (post-cooling-subtraction, `:133`), not the
requested power — cooling therefore also lowers inlet, a coupled effect tested in P2.4.

**EQ-COOL** (`core.py:124-131`): before the RK update,
```text
cooling_on  = T > T_SAFE (65 °C)
events     += Σ (cooling_on & ~prev)          # rising-edge count per node
E_cool     += P_cool · Σ cooling_on · dt      # device-energy ledger [J]
P_actual    = P_eff - P_cool·cooling_on        # heat-input reduction [W]
```

**EQ-STEP** (`core.py:134-139`): classical RK4 with `(P_actual, T_in)` frozen across
sub-stages, then `T ← clip(T + dt/6·(k1+2k2+2k3+k4), T_amb, 110)`.

**EQ-INIT** (`core.py:96-101`): `T[rack] ~ N(44 + 3·rack, 4²)`, clipped to `[T_amb+1, 60]`.

## 3. Boundary conditions, clamps, discontinuities

- Lower: output clipped up to `T_amb` (floor); upper: clipped down to 110 °C (ceiling).
- Cooling edge (`T == T_SAFE` is off; strictly-greater triggers) — a discontinuity the
  integrator steps over, not through (P2.2-F measures order only in smooth regimes).
- Sensor path (`read_sensors`, `:148-157`) adds fixed offsets (−4/−2 °C) and global-RNG
  noise; it is an observation model, not physics, and is bypassed by AXION (reads `T`).

## 4. Assumption classification

| Assumption | Class |
|---|---|
| EQ-ODE network form, EQ-STEP RK4 tableau, EQ-COOL edge rule, EQ-INLET affine form | Directly specified by source |
| Time constants (τ_iso = 13.05 s, τ_eff ≈ 3.2 s), equilibrium formulas, 4th-order smooth convergence | Derived mathematically (executed: battery tests A–C, F) |
| Lumped single-capacitance node, linear resistances, affine recirculation, `P_fan = 15·Σlevel²`, water proxy `W = E/(0.8·L_v)`, binary 280 W cooling | Explicit modeling assumption (heuristic/toy — see PARAMETER_PROVENANCE.md) |
| Any value justified by metered facility data | None — no calibrated parameters exist in the repo |
| Physical realism of constants (rack ΔT, power levels, 280 W authority) | Unknown/unsupported — labeled toy demonstrator pending calibration interface |

## 5. Equation ↔ code trace

| Equation | Code | Mirror | Test |
|---|---|---|---|
| EQ-ODE | `core.py:118-121` | `equations.dTdt` | `test_dTdt_zero_at_uniform_equilibrium`, antisymmetry |
| EQ-INLET | `core.py:108-116` | `equations.rack_inlet` | `test_inlet_matches_legacy`, linearity |
| EQ-STEP | `core.py:134-139` | `equations.rk4_step` | `test_replica_matches_legacy[_nonuniform]` |
| EQ-COOL | `core.py:124-131` | exercised directly | `test_E_cooling_response_and_edge_counting`, hvac/cooling suite |
| EQ-INIT | `core.py:96-101` | — (distribution shape only) | distribution smoke via seed reproducibility (Phase 1 RNG note) |
