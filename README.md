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

All attack behavior is simulated as generated logs and path data. The MVP does not attack real hosts, external IPs, domains, or local services.

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

Current tests cover the BYO web-app target workflow, custom scenario execution, report target inclusion, external target rejection, and duplicate service-name rejection.

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

The production backend path now covers the full demo workflow: auth, templates, scenarios, labs, simulations, logs, AI analysis, defenses, comparisons, reports, dashboard serving, fake service containers, Kubernetes Job-based traffic/attack runners, Alembic migration scaffolding, and initial API tests. The next implementation steps are:

- add CI image builds and Kind integration tests
- add live Kubernetes pod/job status polling
- replace more generated logs with observed pod and service logs
