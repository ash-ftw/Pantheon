from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


SERVICE_NAME = os.getenv("SERVICE_NAME", "pantheon-service")
SERVICE_TYPE = os.getenv("SERVICE_TYPE", "api")
PORT = int(os.getenv("PORT", "8080"))
INPUT_VALIDATION = os.getenv("PANTHEON_INPUT_VALIDATION", "false").lower() == "true"
ADMIN_RESTRICTED = os.getenv("PANTHEON_ADMIN_RESTRICTED", "false").lower() == "true"
CONTAINER_NAME = os.getenv("HOSTNAME", socket.gethostname())


def emit(event: dict) -> None:
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_service": event.get("source_service", "unknown"),
        "target_service": SERVICE_NAME,
        "method": event.get("method"),
        "endpoint": event.get("endpoint"),
        "status_code": event.get("status_code"),
        "request_count": 1,
        "payload_category": event.get("payload_category", "normal_user_behavior"),
        "event_type": event.get("event_type", "normal_request"),
        "severity": event.get("severity", "Info"),
        "is_attack_simulation": event.get("is_attack_simulation", False),
        "raw_log_json": {
            "service_type": SERVICE_TYPE,
            "container": {
                "hostname": CONTAINER_NAME,
                "port": PORT,
            },
            "request_id": event.get("request_id"),
            "route_family": event.get("route_family"),
            "latency_ms": event.get("latency_ms"),
            "request": event.get("request", {}),
            "response": event.get("response", {}),
            "defense_state": {
                "input_validation": INPUT_VALIDATION,
                "admin_restricted": ADMIN_RESTRICTED,
            },
            "user_agent": event.get("user_agent", ""),
            "safe_simulation": True,
        },
    }
    print(json.dumps(record, separators=(",", ":")), flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "PantheonFakeService/0.1"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_CONNECT(self) -> None:
        self._respond(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "CONNECT is not supported by fake services"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _handle(self) -> None:
        self.request_started_at = time.perf_counter()
        self.request_id = self.headers.get("X-Pantheon-Request-Id") or uuid.uuid4().hex[:12]
        parsed = urlparse(self.path)
        endpoint = parsed.path
        source = self.headers.get("X-Pantheon-Source", "traffic-generator")
        payload_category = self.headers.get("X-Pantheon-Payload", "normal_user_behavior")
        is_attack = self.headers.get("X-Pantheon-Attack", "false").lower() == "true"
        body = self._read_body()
        status = HTTPStatus.OK
        event_type = "normal_request"
        severity = "Info"

        if endpoint == "/health":
            self._log_and_respond(source, endpoint, status, "health_check", payload_category, severity, is_attack)
            return

        if endpoint == "/login":
            username = self._body_field(body, "username", "student")
            password = self._body_field(body, "password", "demo")
            if is_attack or payload_category == "credential_attempt" or password.startswith("wrong"):
                status = HTTPStatus.UNAUTHORIZED
                event_type = "failed_login"
                severity = "High"
            else:
                event_type = "login_success"
            self._log_and_respond(source, endpoint, status, event_type, payload_category, severity, is_attack, {"user": username})
            return

        if endpoint in {"/search", "/employees", "/products", "/marks"}:
            query = parse_qs(parsed.query).get("q", [""])[0] or self._body_field(body, "q", "")
            suspicious = any(token in query.lower() for token in ["'", "--", " union ", " or ", "drop ", "select "])
            if suspicious:
                if INPUT_VALIDATION:
                    status = HTTPStatus.FORBIDDEN
                    event_type = "blocked_by_defense"
                    severity = "Warning"
                else:
                    event_type = "suspicious_input_pattern"
                    severity = "High"
                    payload_category = "sql_meta_characters"
            else:
                event_type = "business_api_request"
            self._log_and_respond(source, endpoint, status, event_type, payload_category, severity, is_attack)
            return

        if endpoint.startswith("/admin"):
            trusted = self.headers.get("X-Pantheon-Trusted", "false").lower() == "true"
            if ADMIN_RESTRICTED or is_attack or not trusted:
                status = HTTPStatus.FORBIDDEN
                event_type = "restricted_endpoint_access"
                payload_category = "low_privilege_token"
                severity = "High"
            else:
                event_type = "admin_request"
            self._log_and_respond(source, endpoint, status, event_type, payload_category, severity, is_attack)
            return

        if endpoint.startswith("/db") or SERVICE_TYPE in {"database", "cache"}:
            event_type = "database_reachability_attempt" if is_attack else "datastore_request"
            severity = "High" if is_attack else "Info"
            self._log_and_respond(source, endpoint, status, event_type, payload_category, severity, is_attack)
            return

        self._log_and_respond(source, endpoint, status, event_type, payload_category, severity, is_attack)

    def _log_and_respond(
        self,
        source: str,
        endpoint: str,
        status: HTTPStatus,
        event_type: str,
        payload_category: str,
        severity: str,
        is_attack: bool,
        data: dict | None = None,
    ) -> None:
        response_payload = {"service": SERVICE_NAME, "event_type": event_type, "data": data or {}}
        response_bytes = len(json.dumps(response_payload).encode("utf-8"))
        emit(
            {
                "source_service": source,
                "method": self.command,
                "endpoint": endpoint,
                "status_code": int(status),
                "payload_category": payload_category,
                "event_type": event_type,
                "severity": severity,
                "is_attack_simulation": is_attack,
                "request_id": getattr(self, "request_id", ""),
                "route_family": self._route_family(endpoint),
                "latency_ms": round((time.perf_counter() - getattr(self, "request_started_at", time.perf_counter())) * 1000, 2),
                "request": self._request_context(endpoint),
                "response": {
                    "bytes": response_bytes,
                    "status_text": status.phrase,
                },
                "user_agent": self.headers.get("User-Agent", ""),
            }
        )
        self._respond(status, response_payload)

    def _respond(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return ""
        body = self.rfile.read(min(length, 8192)).decode("utf-8", errors="replace")
        self.request_body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""
        self.request_body_bytes = len(body.encode("utf-8"))
        return body

    def _body_field(self, body: str, key: str, default: str) -> str:
        if not body:
            return default
        try:
            parsed = json.loads(body)
            return str(parsed.get(key, default))
        except json.JSONDecodeError:
            parsed = parse_qs(body)
            return parsed.get(key, [default])[0]

    def _request_context(self, endpoint: str) -> dict:
        parsed = urlparse(self.path)
        safe_headers = {
            "user_agent": self.headers.get("User-Agent", ""),
            "content_type": self.headers.get("Content-Type", ""),
            "accept": self.headers.get("Accept", ""),
            "pantheon_source": self.headers.get("X-Pantheon-Source", ""),
            "pantheon_payload": self.headers.get("X-Pantheon-Payload", ""),
            "pantheon_attack": self.headers.get("X-Pantheon-Attack", ""),
            "pantheon_trusted": self.headers.get("X-Pantheon-Trusted", ""),
        }
        remote_ip = self.client_address[0] if self.client_address else ""
        return {
            "id": getattr(self, "request_id", ""),
            "path": endpoint,
            "query_keys": sorted(parse_qs(parsed.query).keys()),
            "query_length": len(parsed.query),
            "content_length": int(self.headers.get("Content-Length", "0") or "0"),
            "body_bytes_read": getattr(self, "request_body_bytes", 0),
            "body_sha256": getattr(self, "request_body_sha256", ""),
            "headers": safe_headers,
            "remote_addr_hash": hashlib.sha256(remote_ip.encode("utf-8")).hexdigest()[:12] if remote_ip else "",
        }

    def _route_family(self, endpoint: str) -> str:
        if endpoint == "/health":
            return "health"
        if endpoint == "/login":
            return "authentication"
        if endpoint in {"/search", "/employees", "/products", "/marks"}:
            return "business-api"
        if endpoint.startswith("/admin"):
            return "admin-api"
        if endpoint.startswith("/db") or SERVICE_TYPE in {"database", "cache"}:
            return "datastore"
        return "generic"


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(json.dumps({"event": "fake_service_started", "service": SERVICE_NAME, "port": PORT}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
