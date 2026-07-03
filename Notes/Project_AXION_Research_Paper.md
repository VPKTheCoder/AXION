# Thermally-Aware Tensor Scheduling and Predictive Burst Detection for AI Data Centers: Project AXION

**Abstract**
The rapid proliferation of large language models and dense tensor workloads has drastically increased power densities in AI data centers, resulting in localized hotspots, cooling inefficiencies, and thermal throttling. Traditional reactive cooling mechanisms incur high operational costs and induce latency violations. In this paper, we introduce Project AXION, a proactive thermal management framework that combines Thermally-Aware Tensor Scheduling (TATS) with Predictive Burst Detection (PBD) and dynamic, SLO-aware power capping. By leveraging Tucker Decomposition to model the spatial-temporal thermal manifold and applying Simulated Annealing for load-balancing, AXION achieves over 8°C in peak temperature reductions, eliminates emergency evaporative cooling events entirely, and maintains strict Service Level Objective (SLO) compliance.

---

## 1. Introduction
Modern AI workloads, particularly Generalized Matrix Multiplications (GEMM) and attention mechanisms in Transformers, consume extreme amounts of power in concentrated bursts. A standard data center rack running inference can spike from 5 kW to 35 kW in seconds. When nodes overheat, conventional schedulers rely on reactive hardware throttling, severely degrading throughput and violating Service Level Objectives (SLOs) required for real-time inference.

Project AXION presents a holistic software-defined cooling approach. Rather than relying solely on HVAC systems or reactive throttling, AXION routes workloads spatially across the data center to balance the thermal load. 

## 2. System Architecture

### 2.1 Thermal Physics Model
AXION employs a rigorous physics simulation based on Newton’s Law of Cooling, modeled as a resistance network over Runge-Kutta 4 (RK4) integration:
$$C_i \frac{dT_i}{dt} = P_i - \frac{T_i - T_{in}}{R_{amb}} - \sum_{j \in N(i)} \frac{T_i - T_j}{R_{ij}}$$
The framework includes ASHRAE rack-inlet bypass effects, recognizing that hot exhaust air from heavily loaded servers recirculates and raises the baseline temperature for adjacent servers.

### 2.2 Thermally-Aware Tensor Scheduling (TATS)
Instead of treating temperature as an independent scalar, TATS models the data center's thermal history as a 4-dimensional tensor $\mathcal{T} \in \mathbb{R}^{N \times S \times T \times W}$ (Nodes $\times$ Sensors $\times$ Time $\times$ Workloads). 
To ensure tractability, TATS utilizes Tucker Decomposition to compress this state into a core tensor and factor matrices. By projecting these factor matrices forward via Einstein summation contractions, the system can predict the exact thermal outcome of assigning a specific workload to a specific node before the assignment is made.

### 2.3 SLO-Aware Power Capping and Load Balancing
AXION frames job scheduling strictly as a permutation problem, enforcing work conservation. Workloads are matched to nodes using a greedy $O(N \log N)$ heuristic that pairs high-power jobs with cool nodes. 
When physical routing is insufficient to prevent a hotspot, AXION applies dynamic power caps. Unlike naive throttling, AXION analytically derives the maximum allowable power cap $c$ based on the workload's baseline latency $L_{rated}$ and the hard latency constraint $L_{MAX}$:
$$c \ge \frac{L_{rated}}{L_{MAX}}$$
This guarantees that thermal capping never results in an SLO violation.

### 2.4 Predictive Burst Detection (PBD)
AI bursts happen faster than standard scheduling periods (e.g., 30s). PBD introduces a high-frequency derivative monitor ($dT/dt$). AXION employs an adaptive gate: if the thermal slope exceeds a physical floor limit *and* is statistically distinct from recent cycling noise ($\mu + 2\sigma$), PBD triggers a fast-path Simulated Annealing interrupt. This reroutes the burst dynamically before the hardware thermal capacitance is fully saturated.

### 2.5 Evolutionary Constraint Mapper (ECM)
To solve the cold-start problem in newly deployed data centers (which lack the history required to populate the Tucker tensor), ECM acts as a meta-learning module. It transfers the decomposed thermal core from a well-profiled "source" facility and fits it to the new "target" facility using only a sparse set of initial sensor readings, dropping Root Mean Square Error (RMSE) drastically within minutes of deployment.

## 3. Methodology and Simulation Setup
The framework was evaluated using a highly optimized Python simulation environment representing a 32-node cluster spanning 4 racks. Six distinct AI workloads were modeled (GEMM, Attention, FFN, KV Cache, Embedding, and Gradient Updates) with varying power profiles (40W to 370W) and latency constraints. The simulation compared the AXION controller against a reactive baseline relying on identical thermal physics.

## 4. Results and Discussion

### 4.1 Temperature Reduction and Cooling Costs
The integration of TATS and AXION resulted in profound thermal improvements:
- **Mean Peak Temperature**: Reduced by 8.06°C compared to the baseline (Cohen's $d = 2.82$, statistically significant).
- **Cooling Events**: Emergency evaporative cooling events were reduced from 465 to 0. Total auxiliary cooling energy expenditure fell by 100%.

### 4.2 Throughput and SLO Compliance
While the baseline system dropped to 97.5% SLO compliance due to indiscriminate hardware throttling during bursts, AXION maintained **100% SLO compliance**. The cost of this safety is a minimal 5.9% reduction in aggregate throughput, purely as a result of intelligent, mathematically constrained power capping.

### 4.3 PBD and SA Efficiency
Through adaptive statistical gating, the Predictive Burst Detection algorithm successfully identified true thermal emergencies without generating false positives during normal workload rotation. The Simulated Annealing predictor, enriched by the Tucker manifold, operated with an extremely low temporal profile ($\sim 1.5$ seconds for the total runtime across 600 simulation steps), proving its viability for real-time deployment.

## 5. Conclusion
Project AXION demonstrates that treating data center thermal management as a tensor-compressed spatial routing problem yields superior results to reactive throttling. By structurally embedding SLO guarantees and predictive burst detection into the optimization objective, AXION offers a highly practical, deployable framework for sustainable AI infrastructure.

---
*Drafted based on simulation outputs and technical specifications from the Project AXION repository.*
