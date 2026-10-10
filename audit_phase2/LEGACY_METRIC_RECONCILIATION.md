# LEGACY_METRIC_RECONCILIATION.md — P2.7 Claim Dispositions (executed evidence)

> Runs (safe runner, snapshot isolation, `seed_honored=false`):
> TATS `results/tats/20261009T134009Z_715608e1` (40.4 s, exit 0),
> AXION `results/axion/20261009T134053Z_aedeea55` (26.2 s, exit 0),
> ECM `results/ecm/20261009T134123Z_529fcf66` (52.4 s, exit 0).
> Machine-readable dispositions: `results/phase2/reconciliation.json`.
> Rule: values reproducible from recorded observables are **reproduced**;
> values needing unavailable trajectories/scopes are **redefined** (new meaning)
> or **non-comparable**; never manufactured. Comparative-superiority judgments
> are Phase 3 business — none made here.

## Disposition table

| Claim | Original definition | Reproduction | Canonical form | Recalculated | Confounds / remaining evidence |
|---|---|---|---|---|---|
| H-01 TATS −8.06 °C | 600-step mean-peak Δ, Welch/d/CI | **reproduced** (+8.059, CI +7.734/+8.385; t=−48.62, d=2.807) | `thermal.peak_mean` (scope-labeled); dose needs trajectories | 61.9→53.8 °C | substitution-rate logging needs E-03 trajectory capture |
| H-02 TATS 465→0, water→0 | edge counts; WUE proxy | **reproduced** (465→0; 130.2→0.0 kJ; 0.072109→0.000000 L) | edge-rule counts + proxy-labeled water | as reproduced | edge rule understates sustained episodes (verified); baseline full-power by construction |
| H-03 TATS 100% SLO | all-workload scope | **redefined** (candidate 100% guard scope; baseline 0.0% bound-all scope) | `slo.compliance` + scope + denominator | unified-scope value NOT TESTABLE | gap measures guard ≥ thermals; needs E-03/D-03 |
| H-04 Welch sig., large effect | per-step independence assumed | reproduced *numerically*, **redefined** inferentially | trial-level tests (E-02, Phase 3) | n/a | autocorrelation invalidates per-step p/d as inference |
| H-05/H-07 AXION temp/SLO/retention | paired steps; SENSITIVE scope; power retention | **reproduced** (61.64→57.99; +3.650 CI 3.487/3.814; 96.4%) | scope-labeled compliance; `work.retention` future | as reproduced | narrower SLO scope than TATS; retention is cap proxy |
| H-06 AXION 328→4, −98.8% | edge counts; device ledger; proxy | **reproduced** (328→4, Greedy 131; 91.84→1.12 kJ; −98.8%) | proxy-labeled cooling fields | as reproduced | greedy captures most peak benefit; no metered savings |
| PBD narrative | burst protection | **not-testable** (0 triggers over full canonical run incl. both bursts) | E-06 rig (Phase 3+) | 0 observed | floor exceeds canonical slope; precision/recall unknown |
| H-08 ECM RMSE 5.50→0.163 | static profile fit | **reproduced** (0.163; stat 0.1559±0.0678, 100% reliability) | `fit.rmse` (fit quality, not thermal outcome) | 0.163 confirmed | dynamic meaning needs E-09 |
| H-09/H-10 ECM cooling/throughput | static any()-cooling; power-throughput | **non-comparable** (numbers reproduced as records: 300→0; 164→226 W; oracle parity) | trajectory metrics uncomputable from lookups | — | power-throughput rewards heat (naive B cooler yet "worse") |
| Paper §4.2 "97.5%, −5.9%" | unstated | **non-comparable** (no provenance to any observable) | — | — | needs source run or withdrawal |
| Explanation "over 10 °C" | unstated | **contradicted** (max executed Δ ≈ 8.06; no artifact) | — | — | reserved for Phase 3 reporting correction |

## What changed status in Phase 2

- H-03: unverified → **redefined** (two scopes documented, unified value blocked on D-03).
- H-04: headline statistic → **redefined** (number stands, inference use withdrawn).
- H-09/H-10, §4.2: unverified → **non-comparable** (with stated reasons).
- H-12 ("over 10 °C"): contradicted-by-code → **contradicted** (executed ceiling).
- PBD narrative: concern → **not-testable with 0-trigger execution record**.
- All pure-magnitude reproductions (H-01/02/05/06/08): unverified → **reproduced as
  execution records** — explicitly NOT superiority evidence (single run, known confounds).
