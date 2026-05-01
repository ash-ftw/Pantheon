# Attack Engine

The runner image contains two Kubernetes job entry points:

- `traffic_generator.py`: sends normal lab traffic to internal service names.
- `runner.py`: executes preset scenario steps against internal service names only.

Build locally:

```powershell
cd "C:\Users\ASUS\OneDrive\Documents\New project\pantheon"
docker compose --profile images build runner-image
```

Image name:

```text
pantheon-runner:latest
```

Safety controls:

- no arbitrary URLs are accepted
- every target must exist in `SERVICES_JSON`
- service names reject URL/path metacharacters
- request count is capped per step
- logs are emitted as normalized JSON
- pods run without service account tokens or privilege escalation
