from __future__ import annotations

import itertools
import time

from common import emit_log, fail, load_json_env, send_request, service_map


def main() -> None:
    services = service_map(load_json_env("SERVICES_JSON", []))
    normal_traffic = load_json_env("NORMAL_TRAFFIC_JSON", [])
    simulation_id = load_json_env("SIMULATION_ID_JSON", "")
    if not services or not normal_traffic:
        fail("SERVICES_JSON and NORMAL_TRAFFIC_JSON are required")

    service_names = [name for name in services if services[name].get("type") not in {"database", "cache", "worker"}]
    if not service_names:
        service_names = list(services)

    for index, entry in enumerate(normal_traffic[:30]):
        parts = str(entry).split(" ", 1)
        method = parts[0] if parts else "GET"
        endpoint = parts[1] if len(parts) > 1 else "/"
        target = service_names[index % len(service_names)]
        body = {"username": "student", "password": "demo"} if endpoint == "/login" and method == "POST" else None
        send_request(
            source="traffic-generator",
            target=target,
            services=services,
            method=method,
            endpoint=endpoint,
            payload_category="normal_user_behavior",
            event_type="normal_request",
            is_attack=False,
            body=body,
        )
        time.sleep(0.05)

    emit_log(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_service": "traffic-generator",
            "target_service": "traffic-generator",
            "method": "SIMULATE",
            "endpoint": "/complete",
            "status_code": 200,
            "request_count": 1,
            "payload_category": "runner_status",
            "event_type": "traffic_job_completed",
            "severity": "Info",
            "is_attack_simulation": False,
            "raw_log_json": {"simulation_id": simulation_id, "safe_simulation": True},
        }
    )


if __name__ == "__main__":
    main()
