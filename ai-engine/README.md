# AI Engine

The MVP uses deterministic classification based on preset scenario labels and generated log features. This keeps the demonstration stable and explainable.

Suggested replacement plan:

1. Generate synthetic logs for every preset scenario.
2. Extract features such as request count, failed login count, endpoint diversity, payload category, request rate, service hop count, and blocked request count.
3. Train a Random Forest classifier for known attack categories.
4. Add Isolation Forest for anomaly detection.
5. Keep the rule-based explanation and recommendation layer for readable student output.

