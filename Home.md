---
title: Project AXION
image: Assets/icon.png
cover: Assets/icon.png
icon: Assets/icon.png
---

# 🛡️ Project AXION: AI Data-Center Thermal Optimization

![Project AXION icon](Assets/icon.png)

Welcome to the **Project AXION** research repository. This project models and implements software-only, proactive mathematical frameworks to optimize thermodynamic performance, eliminate evaporative cooling water waste, and maintain service-level objectives (SLOs) in AI data centers.

---

## 🗺️ Project Map

### 📁 Research & Documentation
*   **[[Notes/Project_AXION_Research_Paper|Research Paper]]**: Draft paper covering the AXION architecture, methodology, results, and deployment implications.
*   **[[Notes/Project_AXION_Explanation|Technical Explanation]]**: System-level walkthrough of the thermal physics model, TATS, AXION controller, Simulated Annealing optimizer, PBD, and ECM.

### 📁 Simulation Scripts (`Scripts/`)
*   **[tats_simulation.py](Scripts/tats_simulation.py)**: Main simulation pipeline proving proactive tensor scheduling against a reactive baseline. Models Tucker SVD-based thermal manifold predictions.
*   **[ecm_simulation.py](Scripts/ecm_simulation.py)**: Evolutionary Constraint Mapper (ECM) framework. Demonstrates instant, day-one zero-warmup thermal transfer across heterogeneous clusters (Hyperscale, Edge, Hospital, Research).
*   **[axion.py](Scripts/axion.py)**: Core controller for load-balancing and dynamic power capping. Uses a permutation-conserved scheduler combined with Simulated Annealing caps ($c \in \{1.00, 0.85, 0.70, 0.55, 0.40\}$), rack-level HVAC tuning, and Predictive Burst Detection (PBD) to handle sudden thermal transients.

### 📁 Assets & Outputs (`Assets/`)
*   **`Assets/icon.png`**: Primary project icon used by the repository landing pages.
*   **`Assets/TATS_Simulation_Results.png`**: Multi-panel visualization of the TATS simulation runs.
*   **`Assets/ECM_Phase2_Results.png`**: Performance curves showing transfer learning accuracy (RMSE) and throughput gains for ECM.
*   **`Assets/AXION_Results.png`**: Simulation results of the AXION controller comparing peak temperatures, cooling events, throughput retention, SLO compliance, and PBD triggers against the baseline.

---

## 📊 Live Simulation Results

### 1. TATS vs. Traditional Reactive Cooling
TATS proactively maneuvers workloads along thermally safe paths, keeping peak node temperatures low and eliminating the need for evaporative water cooling.
![TATS Simulation Results](Assets/TATS_Simulation_Results.png)

### 2. ECM Multi-Facility Transfer
The Evolutionary Constraint Mapper (ECM) solves the cold-start problem by mapping a new facility's thermal fingerprint using only $K$ sensor readings.
![ECM Phase 2 Results](Assets/ECM_Phase2_Results.png)

### 3. AXION Load Balancing & Dynamic Power Capping
AXION uses load balancing (permuting tasks to cool nodes), dynamic power capping (via NVML limit simulation), and Predictive Burst Detection to handle sudden workloads.
![AXION Simulation Results](Assets/AXION_Results.png)
