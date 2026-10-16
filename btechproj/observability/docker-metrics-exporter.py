"""Expose minimal per-container Docker stats in Prometheus text format."""

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote


DOCKER_SOCKET = "/var/run/docker.sock"


def docker_get(path):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(3)
    client.connect(DOCKER_SOCKET)
    try:
        client.sendall(
            f"GET {path} HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n".encode()
        )
        response = b""
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            response += chunk
    finally:
        client.close()

    header, body = response.split(b"\r\n\r\n", 1)
    status = int(header.split(b" ", 2)[1])
    if status >= 400:
        raise RuntimeError(f"Docker API returned HTTP {status} for {path}")
    if b"transfer-encoding: chunked" in header.lower():
        decoded = b""
        while body:
            size_line, body = body.split(b"\r\n", 1)
            size = int(size_line.split(b";", 1)[0], 16)
            if size == 0:
                break
            decoded += body[:size]
            body = body[size + 2:]
        body = decoded
    return json.loads(body)


def escape_label(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def collect_metrics():
    lines = [
        "# HELP container_cpu_usage_seconds_total Cumulative container CPU time.",
        "# TYPE container_cpu_usage_seconds_total counter",
        "# HELP container_memory_working_set_bytes Current container memory working set.",
        "# TYPE container_memory_working_set_bytes gauge",
    ]
    for container in docker_get("/containers/json"):
        service = container.get("Labels", {}).get("com.docker.compose.service")
        if not service:
            continue
        container_id = container["Id"]
        stats = docker_get(
            f"/containers/{quote(container_id)}/stats?stream=false&one-shot=true"
        )
        cpu_seconds = (
            stats.get("cpu_stats", {})
            .get("cpu_usage", {})
            .get("total_usage", 0)
            / 1_000_000_000
        )
        memory = stats.get("memory_stats", {})
        usage = memory.get("usage", 0)
        cache = memory.get("stats", {}).get("inactive_file", 0)
        working_set = max(0, usage - cache)
        labels = (
            f'container_label_com_docker_compose_service="{escape_label(service)}",'
            f'id="/docker/{container_id}",name="{escape_label(container["Names"][0].lstrip("/"))}"'
        )
        lines.append(f"container_cpu_usage_seconds_total{{{labels}}} {cpu_seconds}")
        lines.append(f"container_memory_working_set_bytes{{{labels}}} {working_set}")
    return ("\n".join(lines) + "\n").encode()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return
        try:
            body = collect_metrics()
            self.send_response(200)
        except Exception as exc:
            body = f"# exporter_error {type(exc).__name__}: {exc}\n".encode()
            self.send_response(500)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9101), MetricsHandler).serve_forever()
