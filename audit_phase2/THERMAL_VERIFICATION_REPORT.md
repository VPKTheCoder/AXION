# THERMAL_VERIFICATION_REPORT.md — P2.2 Results (executed, independent references)

> Battery: `src/axion/physics/battery.py` → `results/phase2/verification_report.json`
> (`all_pass: true`, 1.7 s). Tests: `tests/test_thermal_verification.py` (6/6 PASS).
> No test compares the model to itself: references are closed-form RC solutions, a
> direct linear-system solve, and tight-tolerance DOP853. Legacy runs at fixed DT=1.0;
> refinement uses the fidelity-pinned replica (pin: < 5e-6 vs legacy, equation tests).

## Results

| Test | Setup | Expectation (independent) | Measured | Verdict |
|---|---|---|---|---|
| A zero-input equilibrium | P=0, T0=44 °C, 400 steps | analytic envelope 20·e^(−400/13.05)+1e-6 ≈ 1.0e-6 | final max err **9.7e-13**, 0 cooling events | PASS |
| B constant-power response | uniform 210 W, T0=50, 120 steps | exact `T*+(T0−T*)e^(−t/τ)` at every step | max **2.3e-6**, rms 1.1e-6, final 9.6e-7 °C (float32-output-dominated) | PASS |
| C coupled equilibrium | 40–140 W pattern, 600 steps | direct `A·T=b` solve, T*_max = 38.66 °C | replica err **7.1e-14**, legacy err **7.1e-14** °C, 0 events | PASS |
| D boundaries | Q=0 inlet; T0=200/−50; T0=70/P=40 | inlet==ambient; clip [24,110]; cooling engages with P−280 | all hold; P_actual = −240 W documented | PASS |
| E cooling response | below/above threshold; re-trip | no-cooling identity; edge counting; device ledger | energy 280·N·dt exact; sustained heat counts once; re-trip recounts | PASS |
| F refinement | replica dt ∈ {1,½,¼,⅛}, smooth 210 W case | RK4 order ≈ 4; DOP853 agreement | orders **4.046, 4.023, 4.012**; finest-vs-DOP853 **6.0e-11** °C; monotone error decay | PASS |

## Interpretation (what this does and does not prove)

- **Verified mathematical properties:** the implemented stepper is classical RK4 (4th-order
  smooth convergence + DOP853 agreement); uniform trajectories follow the exact RC solution;
  the coupled network converges to the exact linear-system fixed point; internal exchange
  nets to zero (7.1e-14-class agreement includes legacy float32 path here).
- **Not validated:** physical realism of any constant (all toy/heuristic); behavior across
  the cooling discontinuity (order demands suspended there by design — the step stays finite
  and ledger-computed instead); sensor-model fidelity; any controller claim.
- **Failures:** none in the battery. The scientifically important *observations* that stay
  visible: baseline TATS SLO 0.0% (scope artifact), AXION PBD 0 triggers, net-negative
  applied power (−240 W) as specified behavior — all carried into reconciliation, none
  converted into warnings or silent fixes.
