from __future__ import annotations

import time

from common import emit_log, fail, load_json_env, send_request, service_map, validate_service_name


def main() -> None:
    scenario = load_json_env("SCENARIO_CONFIG_JSON", {})
    services = service_map(load_json_env("SERVICES_JSON", []))
    simulation_id = load_json_env("SIMULATION_ID_JSON", "")
    if not scenario or not services:
        fail("SCENARIO_CONFIG_JSON and SERVICES_JSON are required")

    for step in scenario.get("steps", []):
        target = step["target"]
        validate_service_name(target, services)
        count = min(int(step.get("count", 1)), int(step.get("max_count", 80)))
        for index in range(count):
            endpoint = step.get("endpoint", "/")
            payload_category = step.get("payload_category", "simulated_attack")
            query = None
            body = None
            if payload_category == "sql_meta_characters":
                query = {"q": "' OR '1'='1' --"}
            if payload_category == "credential_attempt":
                body = {"username": f"student{index}", "password": f"wrong-{index}"}
            send_request(
                source=step.get("source", "attack-pod"),
                target=target,
                services=services,
                method=step.get("method", "GET"),
                endpoint=endpoint,
                payload_category=payload_category,
                event_type=step.get("event_type", "simulated_attack_step"),
                is_attack=True,
                body=body,
                query=query,
            )
            time.sleep(0.05)

    emit_log(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_service": "attack-pod",
            "target_service": "attack-runner",
            "method": "SIMULATE",
            "endpoint": "/complete",
            "status_code": 200,
            "request_count": 1,
            "payload_category": "runner_status",
            "event_type": "simulation_job_completed",
            "severity": "Info",
            "is_attack_simulation": True,
            "raw_log_json": {"simulation_id": simulation_id, "safe_simulation": True},
        }
    )


if __name__ == "__main__":
    main()
