# PHASE1_INVARIANTS.md — Implemented Invariants, Semantics, Coverage, Limits

## 1. Work accounting (`constraints/workload_accounting.py`)

- **Aggregate invariant** (`classify_step`/`check_conservation`): offered vs assigned
  workload-index multisets per step. Kinds: `conserved-identity` (no reroute),
  `conserved-permutation` (rerouted nodes listed, multiset intact — the AXION claim),
  `substitution` (multiset changed; per-node `{offered, assigned}` records — the TATS
  fallback/guard and ECM schedule shapes), `truncated` (length change).
- **Job ledger** (`WorkLedger`): offer → assign → terminal (`completed/rejected/
  dropped/failed`). Duplicates, unoffered transitions, and terminal re-entry raise
  `LedgerError`; `substitute()` forces non-`completed` terminality — **a substitution
  can never be recorded as completed** (C-01 guardrail for v2).
- Tests: 8 (`test_workload_accounting.py`) incl. legacy-shaped substitution
  `[0,0,1,2] → [4,0,1,2]` detected with explicit node record. All pass.
- Limitation: legacy exposes no job identities, so the ledger cannot audit legacy runs
  today; aggregate checks are the strongest valid layer. Substitution *rate*
  instrumentation over legacy trajectories is E-03 work (deferred — needs trajectory
  logging, not just final metrics).

## 2. SLO validation (`constraints/slo.py` + `legacy_adapter.build_legacy_slo_table`)

- Table entries carry `slo_applies: True | False | None`. Legacy Gradient (index 5)
  is `None` (**unresolved**, reason cites the 24 ms vs 19.5 ms vs exemption conflict
  and D-03) — we neither invent a Gradient SLO nor silently exempt it.
- `check_step` yields `PASS` (all decidable within threshold), `FAIL` (any decidable
  breach, unknown index, length mismatch, non-finite cap), or `UNDETERMINED`
  (no decidable breach but unresolved workloads present). `guarantee()` is fail-closed:
  `True` only on unambiguous `PASS`.
- Metric: `L_eff = L_rated / cap <= L_MAX` for bound workloads, matching legacy math.
- Tests: 7 (`test_slo.py`) + 2 adapter tests pinning legacy truth (exemption + conflict).
  All pass.
- Limitation: delayed/failed/unfinished work has no legacy observable; the validator
  scores assignments+caps only. Deferring D-03 keeps AXION-vs-TATS "100%" numbers
  non-comparable — stated explicitly wherever they appear.

## 3. Action validation (`constraints/actions.py` + adapter)

- `validate_caps` against live `ALLOWED_CAPS` (incl. the Gradient full-list exemption —
  valid *under legacy scope*, flagged by the SLO layer as UNRESOLVED, not silently safe);
  empty allowed sets accept nothing; tolerance `1e-4` matches legacy comparisons.
- `validate_hvac` (exact rack count, legal levels), `validate_permutation` (bijection
  with missing/duplicated reports), `validate_assignment_coverage` (length + known
  indices), `validate_finite_vector` (NaN/±inf rejection).
- Tests: 7 (`test_actions.py`) + adapter combined-step test (valid passes; a step with
  bad cap + bad HVAC level + short assignment reports all three fields). All pass.
- Limitation: no capacity model exists in legacy (any workload on any node), so
  "resource constraints" reduce to index validity; safe-fallback behavior is validated
  only as *absence of invalid output*, not as a recovery protocol (needs a v2 fallback
  contract — deferred).

## 4. Invariants that remain unenforceable with the legacy representation

1. Job-level no-loss/no-duplication over legacy runs (no identities) — ledger ready, data absent.
2. Unified SLO guarantee across TATS/AXION/ECM (D-03 undecided by design in Phase 1).
3. Temperature-dose / exceedance accounting (needs trajectory logs; E-10).
4. Predictor-fidelity and PBD-correctness invariants (need E-06/E-07 experiments).
5. Seed-controlled reproducibility of legacy scripts (scripts ignore seeds; E-02 needs v2 RNG).
