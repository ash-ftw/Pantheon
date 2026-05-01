from __future__ import annotations

import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def load_json_env(name: str, default: Any) -> Any:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{name} must be valid JSON: {exc}") from exc


def emit_log(record: dict[str, Any]) -> None:
    print(json.dumps(record, separators=(",", ":")), flush=True)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def service_map(services: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in services if "name" in item}


def validate_service_name(target: str, services: dict[str, dict[str, Any]]) -> None:
    if target not in services:
        raise SystemExit(f"Refusing target outside lab service list: {target}")
    if any(part in target for part in (":", "/", "\\", "..", "@", "?", "#")):
        raise SystemExit(f"Invalid service target: {target}")


def service_url(target: str, services: dict[str, dict[str, Any]], endpoint: str) -> str:
    validate_service_name(target, services)
    service = services[target]
    port = int(service.get("port") or 8080)
    path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    if endpoint.startswith("tcp/"):
        path = "/db/ping"
    return f"http://{target}:{port}{path}"


def send_request(
    *,
    source: str,
    target: str,
    services: dict[str, dict[str, Any]],
    method: str,
    endpoint: str,
    payload_category: str,
    event_type: str,
    is_attack: bool,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    timeout: float = 2.0,
) -> dict[str, Any]:
    url = service_url(target, services, endpoint)
    if query:
        url = f"{url}?{urlencode(query)}"
    payload = None
    headers = {
        "User-Agent": "pantheon-runner/0.1",
        "X-Pantheon-Source": source,
        "X-Pantheon-Payload": payload_category,
        "X-Pantheon-Attack": "true" if is_attack else "false",
        "Content-Type": "application/json",
    }
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, method="POST" if method == "POST" else "GET", headers=headers)
    status_code = 0
    error = None
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            response.read()
    except HTTPError as exc:
        status_code = int(exc.code)
        error = str(exc)
    except URLError as exc:
        error = str(exc.reason)
    except TimeoutError:
        error = "request_timeout"

    record = {
        "timestamp": now_iso(),
        "source_service": source,
        "target_service": target,
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "request_count": 1,
        "payload_category": payload_category,
        "event_type": "blocked_by_defense" if is_attack and status_code == 403 else event_type,
        "severity": "High" if is_attack else "Info",
        "is_attack_simulation": is_attack,
        "raw_log_json": {
            "safe_simulation": True,
            "runner": os.getenv("HOSTNAME", "pantheon-runner"),
            "error": error,
        },
    }
    emit_log(record)
    return record


def fail(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(1)
