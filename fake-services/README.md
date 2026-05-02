# Fake Services

`demo-service` is a reusable fake microservice container for Pantheon labs. It exposes harmless demo endpoints, emits structured JSON access logs, and can represent frontend, API, database, or cache services by changing environment variables.

Build locally:

```powershell
cd "D:\Pantheon"
docker compose --profile images build fake-service-image
```

Image name:

```text
pantheon-fake-service:latest
```

Supported environment:

```text
SERVICE_NAME=auth-service
SERVICE_TYPE=api
PORT=8080
PANTHEON_INPUT_VALIDATION=false
PANTHEON_ADMIN_RESTRICTED=false
```

Each request log includes request ID, route family, safe header metadata, body hash, response size, latency, container hostname, and active defense flags. The service does not contain real vulnerabilities. It only labels predefined suspicious patterns for controlled training scenarios.

Real user-owned services are supported separately through Pantheon's BYO Web App Targets flow. The default fake-service image exists so the built-in lab templates remain safe, deterministic, and easy to evaluate.
