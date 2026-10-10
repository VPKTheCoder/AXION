# HVAC_AND_COOLING_AUDIT.md — P2.4 Findings (executed actuator-boundary battery)

> Guards: `src/axion/physics/guards.py` (no legacy behavior changed).
> Tests: `tests/test_hvac_cooling.py` (9/9 PASS). Equation traces: EQ-INLET
> (`core.py:108-116`), EQ-COOL (`core.py:124-131`), fan ledger (`axion.py:366`).

## 1. Equation trace

- Ambient `T_amb=24` → inlet `T_in[rack] = 24 + 5e-5·ΣP_rack − 0.5·hvac[rack]`
  (computed from post-cooling `P_actual`, so emergency cooling also cools inlet).
- HVAC authority: 0 / −0.5 / −1.0 / −1.5 K (levels 0–3, exact — pinned by test).
- Bypass authority: at most +0.148 K (8×370 W rack). HVAC outguns recirculation 10:1.
- Emergency: binary per-node (`T > 65`), −280 W applied power, device ledger
  `280·n·dt`, edge-counted events. No capacity limit, no COP, no chiller.

## 2. Required cases (all executed)

| # | Case | Result |
|---|---|---|
| 1–3 | HVAC 0 / 1–2 / 3 | exact offsets; verdict `physical` whenever `T_in ≥ T_amb` |
| 4 | Ambient sweeps (14/24/34 °C) | margins shift linearly; no hidden ambient coupling |
| 5 | Rack-heat sweep (0/1000/2960 W) | bypass slope exactly `K_bypass`; max +0.148 K |
| 6 | Coupled racks | per-rack inlet independent (rack-0 heat invisible to rack 1) |
| 7–8 | Activation + repeated transitions | engages > 65 °C; energy accrues only on hot steps; re-trip recounts (2N after recover-trip) |
| 9 | Step straddling cooling discontinuity | finite, ledger-computed, no order claimed |
| 10 | Ledger consistency per case | residuals < 0.2% (P2.3); device energy separate |

## 3. Core finding: sub-ambient inlet is reachable and unsupported

With zero rack heat and HVAC ≥ 1, `T_in = 23.5/23.0/22.5 °C < T_amb` — verified
exact. The model contains no refrigeration cycle, chiller work term, or COP, so the
temperature reduction has **no corresponding modeled mechanism or cost** (fan proxy
15·Σlevel² W is the only charge). Verdict `sub_ambient_unsupported` (guard), not a
silent clamp: per the spec, a blanket `T_in ≥ T_amb` floor was NOT imposed (it would
prejudge systems with real chillers). Instead:

- `inlet_assessment()` classifies every inlet field; future controllers (Phase 3) must
  consult it, and any optimization exploiting `sub_ambient_unsupported` inlet is
  reportable as invalid under the declared scope.
- Setting `refrigeration_modeled=True` is gated on a future validated chiller model.

## 4. Cooling-authority audit

Emergency cooling (−280 W/node vs typical 40–370 W loads) can drive *applied* power
negative (−240 W at 40 W load — pinned, not altered). Benefit-per-cost has no physical
meaning (`cop_defined=False`, verdict `abstract-control`): an optimizer trading
"280 W of cooling for 280 W of heat" is doing algebra, not thermodynamics. No arbitrary
penalty was introduced to suppress this; the cost relationship is reported as
uncalibrated and Phase 3 comparisons must not present emergency-cooling avoidance as a
metered energy saving.

## 5. Unsupported mechanisms (explicit list)

1. Refrigeration below ambient (no cycle, no work input, no COP).
2. Heat-removal accounting for the 280 W subtraction (input reduction, not extraction).
3. Fan-curve realism (level² proxy, unattributed coefficient).
4. Water-use causality (evaporative proxy, unattributed η=0.80).
5. Cooling capacity limits (unbounded simultaneous activation).

## 6. Model corrections in Phase 2

**None to legacy equations** (deliberate — spec §2 forbids tuning equations to figures).
Two narrowly scoped *non-behavioral* fixes in new code only: numpy-integer acceptance
in validators (bool still rejected; regression-tested) and float32-rounding-aware
fidelity bounds. Before/after evidence: failing→passing tests with root causes above.
