# Pantheon MVP API

Node demo API base URL:

```text
http://localhost:8090
```

FastAPI backend base URL:

```text
http://localhost:8000
```

Authentication uses a demo bearer token returned by login/register.

FastAPI migration status:

```text
Implemented in backend/app:
- Auth
- Templates
- Scenarios
- Labs
- Kubernetes lab provisioning
- Simulations
- Logs
- AI analysis
- Defenses
- Reports
```

## Auth

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

## Templates and Scenarios

```text
GET /api/templates
GET /api/templates/{template_id}
GET /api/scenarios
GET /api/scenarios/{scenario_id}
```

## Labs

```text
POST   /api/labs
GET    /api/labs
GET    /api/labs/{lab_id}
DELETE /api/labs/{lab_id}
POST   /api/labs/{lab_id}/start
POST   /api/labs/{lab_id}/stop
GET    /api/labs/{lab_id}/logs
```

Create lab body:

```json
{
  "lab_name": "Small Company Demo",
  "template_id": "small-company"
}
```

## Simulations

```text
POST /api/labs/{lab_id}/simulations
WS   /api/labs/{lab_id}/simulations/stream?token={token}&scenario_id={scenario_id}
POST /api/simulations/{simulation_id}/stop
GET  /api/simulations/{simulation_id}
GET  /api/simulations/{simulation_id}/jobs
GET  /api/simulations/{simulation_id}/logs
POST /api/simulations/{simulation_id}/analyze
GET  /api/simulations/{simulation_id}/analysis
GET  /api/simulations/{simulation_id}/recommendations
```

Run simulation body:

```json
{
  "scenario_id": "multi-stage-chain"
}
```

Stop simulation cancels active Kubernetes Jobs labeled with the simulation ID in real mode and marks tracked `simulation_jobs` rows as `Cancelled`.

## Defenses

```text
GET  /api/labs/{lab_id}/defenses
POST /api/labs/{lab_id}/defenses/apply
```

Apply defense body:

```json
{
  "defense_ids": ["input-validation", "network-policy"],
  "simulation_id": "sim_1234abcd"
}
```

## Reports

```text
POST /api/simulations/{simulation_id}/report
GET  /api/reports/{report_id}
GET  /api/labs/{lab_id}/reports
```
