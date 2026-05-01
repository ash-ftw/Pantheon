# Fake Services

`demo-service` is a reusable fake microservice container for Pantheon labs. It exposes harmless demo endpoints, emits structured JSON logs, and can represent frontend, API, database, or cache services by changing environment variables.

Build locally:

```powershell
cd "C:\Users\ASUS\OneDrive\Documents\New project\pantheon"
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

The service does not contain real vulnerabilities. It only labels predefined suspicious patterns for controlled training scenarios.
