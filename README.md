# Project AXION

![Project AXION icon](Assets/icon.png)

Project AXION is a research repository for software-only thermal optimization in AI data centers. It contains simulation scripts for Thermally-Aware Tensor Scheduling (TATS), Evolutionary Constraint Mapping (ECM), and the AXION controller with predictive burst detection and SLO-aware power capping.

## Repository Map

- [Home.md](Home.md): Project landing page and main index.
- [Notes/Project_AXION_Research_Paper.md](Notes/Project_AXION_Research_Paper.md): Draft research paper.
- [Notes/Project_AXION_Explanation.md](Notes/Project_AXION_Explanation.md): Technical explanation of the system.
- [Scripts/core.py](Scripts/core.py): Shared simulation constants and thermal physics.
- [Scripts/tats_simulation.py](Scripts/tats_simulation.py): TATS simulation and result plot generation.
- [Scripts/ecm_simulation.py](Scripts/ecm_simulation.py): ECM transfer simulation and result plot generation.
- [Scripts/axion.py](Scripts/axion.py): AXION controller simulation and result plot generation.
- [Assets/icon.png](Assets/icon.png): Primary project icon.

## Run

Install the Python dependencies, then run scripts from the repository root:

```bash
pip install -r requirements.txt
python Scripts/axion.py
python Scripts/tats_simulation.py
python Scripts/ecm_simulation.py
```

Generated result plots are written to `Assets/`.
