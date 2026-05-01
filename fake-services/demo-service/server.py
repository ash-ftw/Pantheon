from __future__ import annotations

import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


SERVICE_NAME = os.getenv("SERVICE_NAME", "pantheon-service")
SERVICE_TYPE = os.getenv("SERVICE_TYPE", "api")
PORT = int(os.getenv("PORT", "8080"))
INPUT_VALIDATION = os.getenv("PANTHEON_INPUT_VALIDATION", "false").lower() == "true"
ADMIN_RESTRICTED = os.getenv("PANTHEON_ADMIN_RESTRICTED", "false").lower() == "true"


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
                "user_agent": self.headers.get("User-Agent", ""),
            }
        )
        self._respond(status, {"service": SERVICE_NAME, "event_type": event_type, "data": data or {}})

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
        return self.rfile.read(min(length, 8192)).decode("utf-8", errors="replace")

    def _body_field(self, body: str, key: str, default: str) -> str:
        if not body:
            return default
        try:
            parsed = json.loads(body)
            return str(parsed.get(key, default))
        except json.JSONDecodeError:
            parsed = parse_qs(body)
            return parsed.get(key, [default])[0]


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(json.dumps({"event": "fake_service_started", "service": SERVICE_NAME, "port": PORT}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
