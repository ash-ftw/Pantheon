# FastAPI Backend

The production backend lives in:

```text
backend/app
```

## Implemented

- FastAPI app with OpenAPI docs
- PostgreSQL connection through SQLAlchemy
- Tables for users, organization templates, attack scenarios, labs, and service instances
- Seed data for demo users, templates, and scenarios
- HMAC-signed bearer tokens using Python standard library password hashing
- Lab creation API
- Simulation run persistence
- Simulation logs
- AI analysis records
- Defense recommendation/action records
- Report records
- Dashboard served from FastAPI
- Kubernetes Job creation for normal traffic and preset attack runners in real mode
- Structured runner log collection back into PostgreSQL simulation logs
- Kubernetes orchestration service with `dry-run` and `real` modes
- Namespace, ResourceQuota, LimitRange, NetworkPolicy, Deployment, and Service creation in real mode

## Remaining Production Work

- Load local `pantheon-fake-service` and `pantheon-runner` images into Kind/Minikube for real mode
- Alembic migrations
- API and integration test suite
- Production password reset/session management

## Build Lab Images

```powershell
docker compose --profile images build fake-service-image runner-image
```

For Kind:

```powershell
kind load docker-image pantheon-fake-service:latest
kind load docker-image pantheon-runner:latest
```

For Minikube:

```powershell
minikube image load pantheon-fake-service:latest
minikube image load pantheon-runner:latest
```

## Run With Docker

```powershell
cd "C:\Users\ASUS\OneDrive\Documents\New project\pantheon"
docker compose up --build
```

Open:

```text
http://localhost:8000/docs
```

## Dry-Run Mode

Dry-run mode is the default:

```text
KUBERNETES_MODE=dry-run
```

It creates database records and returns successful Kubernetes provisioning states without contacting a cluster.

## Real Kubernetes Mode

Use this only with a local Minikube or Kind cluster:

```powershell
$env:KUBERNETES_MODE="real"
$env:KUBECONFIG="$HOME\.kube\config"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The orchestrator refuses namespaces outside the configured Pantheon prefix and only provisions services from stored organization templates.
