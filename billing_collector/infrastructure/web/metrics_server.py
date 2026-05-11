from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol


class MetricsRenderer(Protocol):
    def render(self) -> str:
        ...


class MetricsServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        metrics_renderer: MetricsRenderer,
    ) -> None:
        self.host = host
        self.port = port
        self.metrics_renderer = metrics_renderer
        self.httpd = ThreadingHTTPServer((host, port), self._handler())

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        metrics_renderer = self.metrics_renderer

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/healthz":
                    self._write(200, "ok\n", "text/plain; charset=utf-8")
                    return
                if self.path == "/readyz":
                    self._write(200, "ready\n", "text/plain; charset=utf-8")
                    return
                if self.path != "/metrics":
                    self._write(404, "not found\n", "text/plain; charset=utf-8")
                    return
                self._write(
                    200,
                    metrics_renderer.render(),
                    "text/plain; version=0.0.4; charset=utf-8",
                )

            def log_message(self, format: str, *args: object) -> None:
                return

            def _write(self, status: int, body: str, content_type: str) -> None:
                encoded = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler
