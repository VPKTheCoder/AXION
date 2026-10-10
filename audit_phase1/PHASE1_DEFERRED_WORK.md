# PHASE1_DEFERRED_WORK.md — Scientific Changes Intentionally Deferred to Phase 2

> Nothing below was changed in Phase 1. Each item names the audit finding, why it
> is out of scope, and the experiment that will decide it.

1. **Thermal equations & energy accounting** (P-01, P-03): parameter provenance table,
   sustained-excursion counting, net-negative cooling power, 110 °C clip policy → E-05a/b.
2. **HVAC & emergency-cooling corrections** (P-02): sub-ambient inlet floor or chiller
   model; fan-cost realism → E-05c + HVAC ablation.
3. **Numerical integration & timestep convergence** (P-05): DT-halving battery + clip-hit
   counters → E-05d.
4. **Predictor/simulator consistency** (A-03): residual logging, Tucker-trust ablation →
   E-07. Tucker stays in the decision path untouched (no rank change, no demotion).
5. **PBD calibration** (A-02): floor 3.70 °C/s + adaptive gate unchanged despite the
   executed 0-trigger observation; precision/recall rig → E-06.
6. **Tucker decision-path validation** (A-04): rank ablation incl. sensor/workload full-rank
   question → E-07.
7. **ECM transfer validation** (A-06): dynamic-simulator scoring, SVD-vs-pure-LS ablation,
   condition-number logging → E-09. Static-model numbers stand as execution records only.
8. **Unified metrics & statistical protocol** (C-04, C-05, §5 of AUDIT_EXPERIMENTS):
   dose metric, absolute-water reporting, work-based throughput, trial-level paired tests
   with pre-registered endpoints, count-data CIs, multiplicity control → E-02/E-10.
9. **Fair-harness reruns** (C-01, C-02, E-03): substitution-rate instrumentation, unified
   SLO scope (needs D-03 decision), identical observation models, conserving-only variants.
10. **Demand generalization** (R-05, E-04): burst randomization, held-out traces.
11. **Seed-grid infrastructure for legacy code** (R-03, E-02): requires rewiring legacy RNG
    ownership — a scientific-behavior change, explicitly not done via globals in Phase 1.
12. **D-03 SLO decision** (Gradient bound vs batch vs per-class table): the single biggest
    blocker for restating H-03/H-07; reserved for review + Phase 2.
13. **Doc contradiction H-12** ("over 10 °C" in Explanation): correction reserved for the
    Phase 3 reporting pass per roadmap.
