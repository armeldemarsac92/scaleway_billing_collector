from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from billing_collector.metrics.collector import PrometheusMetricsCollector


class MetricsServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        collector: PrometheusMetricsCollector,
    ) -> None:
        self.host = host
        self.port = port
        self.collector = collector
        self.httpd = ThreadingHTTPServer((host, port), self._handler())

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        collector = self.collector

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
                    collector.render(),
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

