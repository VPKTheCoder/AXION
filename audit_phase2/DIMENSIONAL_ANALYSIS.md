# DIMENSIONAL_ANALYSIS.md — P2.1 Dimensional Audit (every term checked, not just commented)

> Method: each equation's terms reduced to base units [W, J, s, K] and checked
> for additivity. Coefficients encoding units implicitly are flagged. Executed
> support: `tests/test_physics_equations.py::test_units_tau_is_seconds` and the
> affine-inlet slope test. PASSING.

## EQ-ODE: `C·dT/dt = P − (T−T_in)/R_amb − Σ(T_i−T_j)/R_ij` — CONSISTENT

| Term | Units | Check |
|---|---|---|
| `C·dT/dt` | (J/K)·(K/s) = **W** | LHS energy-rate ✓ |
| `P` | W | ✓ |
| `(T−T_in)/R_amb` | K/(K/W) = **W** (°C differences ≡ K differences) | ✓ |
| `(T_i−T_j)/R_ij` | K/(K/W) = **W**; diagonal `R=∞` contributes `0/∞ → 0` (guarded: `1/inf=0`, `pair[~isfinite]=0`) | ✓ |
| `dTdt` return | W/(J/K) = **K/s** | ✓ |
| RK4 update `T + dt·k` | °C + s·K/s | ✓ |
| `τ = R·C` | (K/W)·(J/K) = **s**; τ_iso = 13.05 s, τ_eff ≈ 3.16 s (executed) | ✓ |

## EQ-INLET: `T_in = T_amb + K_bypass·ΣP − HVAC_deg·hvac` — CONSISTENT, two implicit encodings

| Term | Units | Check |
|---|---|---|
| `T_amb` | °C | ✓ |
| `K_bypass·ΣP` | **K/W** · W = K | ✓ but `K_bypass = 5e-5` carries units **implicitly** (no unit recorded in source; inferred from additivity). Max authority 5e-5·2960 ≈ 0.148 K — two orders below HVAC authority. |
| `HVAC_deg·hvac` | (K/level)·level = K | ✓, likewise implicit. Authority 1.5 K max — 10× the bypass term, which is why full HVAC drives `T_in` sub-ambient (P2.4). |

## EQ-COOL / ledger terms — CONSISTENT as bookkeeping, INCOMPLETE as physics

| Term | Units | Check |
|---|---|---|
| `P_cool·n·dt` (device energy) | W·s = **J** | ✓ arithmetic |
| `P_actual = P_eff − P_cool` | W − W | ✓ arithmetic |
| `W_water = E/(η·L_v)` | J/(J/kg) = **kg ≈ L** | ✓ arithmetic (η=0.80 dimensionless, L_v=2 257 000 J/kg) |
| `P_fan = 15·Σlevel²` | **W** only if the `15` encodes W/level² — implicit, unvalidated (real affinity laws scale flow³; see HVAC audit) | ⚠ implicit + uncalibrated |
| Missing: COP between device energy and heat removed; chiller work for sub-ambient inlet | — | ✗ unsupported (ledger L2/L3; guards classify) |

## Sensor offsets — CONSISTENT but biased by construction

`T−4`, `T−2` channels are K-offsets (✓ units) with σ = 0.25–0.40 K Gaussian noise;
channel 3 recomputes `T_in` from *un-capped* power while physics uses post-cooling
power — a documented observation-model inconsistency (TATS sees a slightly wrong
inlet; AXION bypasses sensors entirely).

## Verdict

The ODE/integrator algebra is dimensionally sound; no term mixes incompatible units.
Three coefficients encode units implicitly (`K_bypass`, `HVAC_deg`, fan `15`) and all
parameter values are uncalibrated (see PARAMETER_PROVENANCE.md). The energy/water
bookkeeping is unit-consistent but physically incomplete (no COP, no chiller) — it
must be reported as proxy accounting, which the ledger and canonical metrics enforce.
