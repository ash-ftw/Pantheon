# AI Engine

Pantheon still keeps deterministic rule-based explanations in the API so demos are stable. This folder now adds a runnable synthetic-data path for the richer AI/anomaly PRD item.

## Generate Training Data

```powershell
cd D:\Pantheon
C:\Python314\python.exe ai-engine\generate_synthetic_dataset.py --rows 420 --output ai-engine\synthetic_training_logs.csv
```

## Train Baseline Artifact

```powershell
cd D:\Pantheon
C:\Python314\python.exe ai-engine\train_baseline_model.py --input ai-engine\synthetic_training_logs.csv --output ai-engine\model_artifact.json
```

The generated artifact is dependency-free and stores class centroids, feature spread, and anomaly policy thresholds. It gives the project a concrete model path that can later be replaced by scikit-learn Random Forest and Isolation Forest without changing the upstream log-feature contract.
