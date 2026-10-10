# ENERGY_ACCOUNTING_REPORT.md — P2.3 Ledger (what closes, what is missing)

> Module: `src/axion/physics/ledger.py`. Tests: `tests/test_energy_ledger.py` (6/6 PASS).
> Convention: `residual = ΔU − (E_in − E_amb)` per step under the *specified* algebra
> (`P_applied` is post-cooling-subtraction). Internal exchange verified (= 0.0 W),
> never assumed. Near-zero scales return `None`, never a fake ratio.

## Measured closure (executed)

| Case | dU scale | Residual | Relative | Verdict |
|---|---|---|---|---|
| Uniform 210 W, dt=1.0 | 963 J | −0.47 J | 4.9e-4 | PASS (< 0.2%) |
| Same, dt=0.5 / 0.25 | 491 / 248 J | −0.060 / −0.0076 J | ratio exactly ~4× per halving | PASS (2nd-order trapezoidal quadrature, as theory predicts) |
| Zero-power quiet step | 0 J | 0 J | `None` (no meaningless ratio) | PASS |
| Clip step (flagged) | — | clip energy `C·N·(110−200)` reported separately, step marked | — | PASS (limitation explicit) |
| Cooling step (P−280 applied) | — | closes to < 0.2% with device energy alongside | — | PASS |

## Completeness assessment: PARTIAL by construction (documented, not fixed)

1. ** closes:** heat input → storage + boundary loss + (verified-zero) internal exchange,
   on clip-free, actuator-constant steps, to quadrature accuracy.
2. **Missing for a complete physical balance:** a COP linking the 280 W device energy to
   heat actually removed (model subtracts it from heat *input* — an algebraic proxy, not
   thermodynamics); chiller work for sub-ambient inlet; fan-energy coupling into the
   thermal field (fan watts are charged to a separate ledger, never injected as heat).
3. **Fan power** `P_fan = 15·Σlevel² W`: units consistent only if `15` encodes W/level²;
   basis stated in legacy comments as a "simplified affinity-law proxy" — real fan laws
   scale ~flow³. Recorded as heuristic with unknown uncertainty (see PARAMETER_PROVENANCE.md);
   charged separately from rack heat per the spec's anti-conflation rule.
4. **Water** `W = E/(0.8·2 257 000)`: unit-consistent proxy (kg≈L via standard latent
   heat); efficiency 0.80 unattributed. Reported via `CoolingSummary.water_is_proxy=True`
   with baseline-anchored percents only.

No unmodeled cooling quantity is represented as a validated physical measurement anywhere
in the new code. The canonical metrics refuse zero-baseline percents (`None`) and refuse
to equate device energy with heat removed (`cop_defined=False`, `abstract-control`).
