# Pantheon

Pantheon is a safe cyber-range project for learning Kubernetes attack paths and defenses. The repository now has two backend tracks:

- `backend/server.js`: dependency-free Node demo API that serves the current dashboard.
- `backend/app`: FastAPI + PostgreSQL + Kubernetes orchestration backend, which is the production architecture path from the PRD.

## What Works Now

- User login and registration
- Organization templates for Small Company, E-Commerce, and University
- Mock Kubernetes lab creation with namespaces and service inventory
- Preset safe attack simulations
- Normal traffic and attack log generation
- AI-style classification and explanation
- Attack path graph
- Defense recommendation and application
- Rerun workflow with before/after comparison
- Dashboard report generation
- Live Kubernetes pod/job status polling for lab services
- Observed Kubernetes job/pod lifecycle logs in real mode
- WebSocket simulation progress streaming in the FastAPI backend
- Deeper fake-service container access logs with request metadata, route family, latency, response size, and defense state
- Active Kubernetes runner job tracking and real simulation cancellation

Attack behavior is constrained to preset or custom safe scenarios inside the selected lab. In dry-run mode, Pantheon still uses generated logs and path data. In real Kubernetes mode, traffic and attack runners execute as Kubernetes Jobs and Pantheon records observed job, pod, and container-log events. The MVP does not attack real hosts, external IPs, domains, or local services outside the lab namespace.

## Local Project Root

Commands below assume the project is located at:

```text
D:\Pantheon
```

## Run Demo Dashboard

```powershell
cd "D:\Pantheon"
npm.cmd start
```

Open:

```text
http://localhost:8090
```

Demo users:

```text
Student: demo@pantheon.local / pantheon123
Admin:   admin@pantheon.local / admin123
```

## Run FastAPI + PostgreSQL Backend

The FastAPI backend exposes the real API foundation on port `8000`. It uses PostgreSQL and can run Kubernetes lab creation in either `dry-run` mode or `real` mode.

Start PostgreSQL and the API with Docker:

```powershell
cd "D:\Pantheon"
docker compose up --build
```

Open:

```text
http://localhost:8000/docs
```

The default Docker configuration uses:

```text
KUBERNETES_MODE=dry-run
```

That means lab creation writes real PostgreSQL records and returns Kubernetes provisioning results without touching a cluster.

To create real Kubernetes namespaces and deployments, install the backend dependencies, point `KUBECONFIG` at your Minikube/Kind config, and set:

```text
KUBERNETES_MODE=real
```

Build the lab service and runner images before using real Kubernetes mode:

```powershell
docker compose --profile images build fake-service-image runner-image
```

Load them into your local cluster:

```powershell
kind load docker-image pantheon-fake-service:latest
kind load docker-image pantheon-runner:latest
```

or:

```powershell
minikube image load pantheon-fake-service:latest
minikube image load pantheon-runner:latest
```



## Database Migrations

The FastAPI backend now includes Alembic migration files for the current schema. The app still defaults to auto-creating tables for local demo convenience. For migration-driven startup, disable auto-create and run Alembic first:

```powershell
cd "D:\Pantheon"
docker compose run --rm --no-deps `
  -e DATABASE_URL="sqlite+pysqlite:////tmp/pantheon-migration-check.db" `
  -e PANTHEON_AUTO_CREATE_TABLES=false `
  api alembic -c alembic.ini upgrade head
```

For PostgreSQL, use the same command with `DATABASE_URL` pointing at your Pantheon PostgreSQL database.

## Backend Tests

Run the API regression tests in the Docker image:

```powershell
cd "D:\Pantheon"
docker compose build api
docker compose run --rm --no-deps `
  -e KUBERNETES_MODE=dry-run `
  -e PANTHEON_AUTO_CREATE_TABLES=true `
  api pytest -q
```

Current tests cover the BYO web-app target workflow, custom scenario execution, WebSocket simulation progress, active job cancellation, report target inclusion, external target rejection, duplicate service-name rejection, dry-run Kubernetes readiness polling, and observed Kubernetes log normalization.

## CI and Kind Integration

The `webapp` branch includes GitHub Actions checks for:

- FastAPI regression tests in dry-run mode
- API image builds
- fake-service and runner image builds
- a Kind-backed integration test that creates a real lab namespace, waits for pod readiness, runs Kubernetes Job-based traffic/attack runners, and verifies observed Kubernetes logs

The Kind test is opt-in outside CI:

```powershell
cd "D:\Pantheon"
$env:PANTHEON_RUN_KIND_TESTS="true"
$env:KUBERNETES_MODE="real"
$env:KUBERNETES_SERVICE_IMAGE="pantheon-fake-service:latest"
$env:KUBERNETES_RUNNER_IMAGE="pantheon-runner:latest"
$env:KUBERNETES_RUNNER_IMAGE_PULL_POLICY="IfNotPresent"
C:\Python314\python.exe -m pytest backend\tests\test_kind_integration.py -q
```

## WebSocket Simulation Progress

The FastAPI backend exposes:

```text
WS /api/labs/{lab_id}/simulations/stream?token={token}&scenario_id={scenario_id}
```

The dashboard uses this stream when served by the FastAPI backend. The dependency-free Node demo keeps the existing REST simulation path as a fallback.

Stream events include simulation start, normal traffic generation, attack step start/completion, Kubernetes Job status changes, runner log observation, service container log collection, analysis, persistence, and the final simulation result.

## Active Job Tracking and Cancellation

Pantheon records Kubernetes runner jobs in `simulation_jobs` with job name, type, namespace, status, timestamps, and last observed event. The dashboard shows these jobs under each simulation result.

To stop a running simulation:

```text
POST /api/simulations/{simulation_id}/stop
```

In real Kubernetes mode, Pantheon deletes active Jobs labeled with the simulation ID and marks tracked jobs as `Cancelled`. In dry-run mode, it records the cancellation without touching a cluster.

## Fake-Service vs Real-Service Containers

Pantheon uses fake-service containers for built-in organization templates because they are safe, deterministic, lightweight, and academically repeatable. They make it possible to demonstrate attack paths, defenses, Kubernetes isolation, and AI classification without shipping intentionally vulnerable real business apps.

Pantheon also supports real user-provided app containers through the BYO Web App Targets workflow. A user can attach a Docker image or constrained Kubernetes YAML, and Pantheon deploys that app inside the lab namespace. Simulations still remain internal-only and cannot target external domains or IPs.

Recommended split:

- Use fake-service containers for default repeatable labs and evaluator demos.
- Use real-service containers for user-owned apps that need custom testing inside a contained namespace.
- Keep attack runners constrained to internal Kubernetes services in both cases.

## Bring Your Own Web App Targets

Pantheon now supports a safe BYO web-app workflow:

1. Create or open a lab.
2. Add a web app target from the `Web App Targets` panel.
3. Use a Docker image, constrained Kubernetes YAML, or local-service metadata.
4. Pantheon registers the app as an internal service in the selected lab.
5. Create a custom scenario against that service name.
6. Run the scenario and review the containment, path, risk, AI, defense, and report indicators.

Custom scenarios cannot target public URLs, IP addresses, or domains. They must target a service that already belongs to the selected lab.

Detailed requirements are in `docs/PRD-BYO-Web-App.md`.

## Demo Flow

1. Login with the demo student account.
2. Create a lab with the Small Company template.
3. Select `SQL Injection to Lateral Movement`.
4. Run the simulation.
5. Review logs, AI classification, and the attack path.
6. Apply `Input validation` or `Kubernetes NetworkPolicy`.
7. Rerun the same simulation.
8. Review the before/after comparison.
9. Generate the report.

## Project Layout

```text
pantheon/
  backend/
    app/
      main.py
      models.py
      api/
      services/
    server.js
    requirements.txt
  frontend/
    index.html
    styles.css
    app.js
  attack-engine/
    scenarios/
  ai-engine/
  fake-services/
  k8s/
    templates/
  docs/
```

## Next Engineering Step

The production backend path now covers the full demo workflow: auth, templates, scenarios, labs, simulations, logs, AI analysis, defenses, comparisons, reports, dashboard serving, fake service containers, Kubernetes Job-based traffic/attack runners, active job tracking/cancellation, live pod/job status polling, WebSocket simulation progress, observed Kubernetes lifecycle logs, deeper service access logs, Alembic migration scaffolding, API tests, CI image builds, and Kind integration coverage. The next implementation steps are:

- add a full in-dashboard service-log detail drawer
- add CI publishing for versioned local images
