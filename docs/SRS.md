# Pantheon SRS Summary

## Functional Requirements Covered in MVP

- FR-001 to FR-005: basic user authentication and role-aware lab access
- FR-006 to FR-012: lab creation, status, stop/start, and delete
- FR-013 to FR-016: three organization templates
- FR-023 to FR-028: preset internal-only attack simulations
- FR-029 to FR-033: generated normal traffic mixed with attack logs
- FR-034 to FR-038: normalized logs stored per simulation
- FR-039 to FR-043: rule-based AI-style classification
- FR-044 to FR-048: defense recommendations
- FR-049 to FR-053: defense application and rerun comparison
- FR-054 to FR-058: attack path graph data and visualization
- FR-059 to FR-064: before/after comparison
- FR-065 to FR-073: report generation and dashboard view

## Deliberate MVP Constraints

- Kubernetes actions are represented as mock state.
- The attack engine does not send network traffic.
- AI is deterministic and rule-based, designed to be replaced by scikit-learn models later.
- Persistence is local JSON instead of PostgreSQL.

