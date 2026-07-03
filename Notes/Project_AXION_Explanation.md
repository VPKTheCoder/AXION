# Project AXION: Comprehensive Technical Explanation

Project AXION is an advanced thermal management system for AI data centers. It addresses the escalating power densities of modern AI hardware (like GPUs running GEMM or Transformer workloads) which cause severe hot spots, high cooling costs, and hardware degradation. 

Unlike traditional reactive systems that simply throttle down hardware when it overheats—causing significant latency violations—Project AXION acts proactively. It distributes computational work, predicts thermal bursts, and optimizes power usage to eliminate thermal emergencies while strictly adhering to Service Level Objectives (SLOs).

This document breaks down every major component of Project AXION.

---

## 1. The Core Physics Model (The Environment)
At the heart of the simulation is a rigorous physical model of a data center rack network, simulated using **Newton's Law of Cooling** and **Runge-Kutta (RK4) integration**.

* **Thermal Coupling (`R_eff`)**: Nodes aren't isolated. Heat from one server bleeds into adjacent servers within a rack (`R_INTRA_RACK`), and across racks (`R_INTER_RACK`).
* **ASHRAE Bypass**: Hot exhaust air recirculates back into the cold aisles. The model calculates the inlet temperature of a rack based on the total power consumption of that rack (`K_BYPASS * ΣP`).
* **Cooling Dynamics**: Nodes heat up according to the power of the workload they are running. If a node exceeds a critical temperature (`T_SAFE`), emergency evaporative cooling kicks in, which is highly water- and energy-intensive. 

---

## 2. Thermally-Aware Tensor Scheduling (TATS)
TATS is the predictive intelligence engine. Instead of just reacting to current temperatures, it learns the thermal behavior of the entire data center across space (nodes, sensors), time (history), and workloads.

* **The Thermal State Tensor**: A 4-dimensional tensor capturing $[N_{nodes} \times N_{sensors} \times T_{window} \times W_{workloads}]$. 
* **Tucker Decomposition**: To avoid the curse of dimensionality, TATS compresses this massive tensor using Tucker Decomposition. It extracts a small "core tensor" and factor matrices representing latent relationships.
* **Manifold Prediction**: Before assigning a workload, the system projects the compressed Tucker factors forward in time. This creates a highly accurate prediction of what the temperature *will be* if a specific job is placed on a specific node.

---

## 3. The AXION Controller (The Decision Maker)
The AXION controller (`axion.py`) is responsible for assigning workloads to nodes every scheduling period. It operates under a strict constraint: **Work is conserved (permutation, not substitution).** It does not throw away heavy jobs to lower heat; it intelligently routes them.

### A. Greedy Load Balancing
AXION uses an $O(N \log N)$ algorithm to match the hottest workloads (e.g., dense GEMMs) to the coolest nodes, and the lightest workloads (e.g., Embeddings) to the hottest nodes.

### B. Dynamic Power Capping with SLO Guarantees
If balancing isn't enough, AXION applies power caps (e.g., limiting a node to 85% or 70% power). Crucially, it only applies caps that respect the **Service Level Objective (SLO)**. For example, if a workload has a strict maximum latency (`L_MAX = 19.5ms`), AXION calculates exactly how much the node can be throttled before the latency exceeds that limit. 

### C. Predictive Burst Detection (PBD)
AI workloads are bursty. TATS scheduling runs periodically (e.g., every 30 seconds), but a sudden GEMM burst can overheat a node in 5 seconds.
* **How it works**: PBD continuously monitors the derivative of temperature ($dT/dt$). 
* **Adaptive Thresholding**: If the slope exceeds a hard floor (e.g., 3.0°C/s) *and* statistically deviates from recent trends (Rolling Mean + $2\sigma$), PBD triggers an emergency mini-Simulated Annealing (SA) loop to instantly reroute workloads before the heat peak hits.

---

## 4. Simulated Annealing (SA) Optimizer
The actual job assignment is determined by Simulated Annealing, guided by a three-part objective function:
1. **Minimize Peak Temperature ($\alpha$)**: The primary goal is preventing hotspots.
2. **Minimize Thermal Gradients ($\beta$)**: Distribute heat evenly across connected nodes to prevent thermal stress.
3. **Penalize Excess Heat ($\gamma$)**: Heavily penalize any node crossing the safety threshold.

**The Three-Source Predictor**: When SA evaluates a potential schedule, it blends three predictions to guess the outcome:
1. *Physics*: Basic linear projection based on power jump and effective resistance.
2. *Welford Profiler*: Historical average of what happens when Node $X$ runs Workload $Y$.
3. *Tucker Manifold*: The advanced tensor projection (trust ramps up as the system gathers more data).

---

## 5. Evolutionary Constraint Mapper (ECM)
The ECM script (`ecm_simulation.py`) solves the **Cold-Start Problem**. When a new data center comes online, it has no thermal history, meaning the Tucker predictor is blind. ECM uses meta-learning to transfer thermal profiles from existing facilities to the new one using just a handful of observations ($K=20$). By solving a least-squares projection against a pre-trained meta-core, the new facility instantly "learns" its thermal dynamics.

---

## Conclusion
Project AXION successfully bridges the gap between theoretical tensor mathematics and practical systems engineering. By utilizing Tucker decomposition for prediction, Simulated Annealing for scheduling, and PBD for real-time safety, it achieves over 10°C in temperature reductions and eliminates emergency cooling events—all without dropping workloads or violating latency SLOs.
