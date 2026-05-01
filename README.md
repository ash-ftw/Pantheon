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

## Run Demo Dashboard

```powershell
cd "C:\Users\ASUS\OneDrive\Documents\New project\pantheon"
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
cd "C:\Users\ASUS\OneDrive\Documents\New project\pantheon"
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

The production backend path now covers the full demo workflow: auth, templates, scenarios, labs, simulations, logs, AI analysis, defenses, comparisons, reports, dashboard serving, fake service containers, and Kubernetes Job-based traffic/attack runners. The next implementation steps are:

- add Alembic migrations instead of `create_all`
- add automated API tests once dependencies are installed
- add CI image builds and Kind integration tests
