"""Receive a real local OTLP export and check that agent source text is absent."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


def verify():
    packets = []

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self):
            packets.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "PYTHONPATH": str(root / "services/api"),
        "HELM_OTLP_ENDPOINT": f"http://127.0.0.1:{server.server_port}/v1/traces",
        "OTEL_SDK_DISABLED": "false",
    }
    program = """
from app.observability import configure
from app.agents.runtime import run_agent
provider = configure()
run_agent('intake', {'id': 'telemetry-fixture', 'name': 'Fictional telemetry person',
    'medical_items': ['PHI_CANARY_TELEMETRY_9138'], 'needs': {'coverage': {'cancer': {'level': 3}}}})
assert provider.force_flush(timeout_millis=10000)
provider.shutdown()
"""
    try:
        subprocess.run([sys.executable, "-c", program], env=environment, cwd=root, check=True, timeout=60)
        spans = []
        for packet in packets:
            assert b"PHI_CANARY_TELEMETRY_9138" not in packet
            assert b"Fictional telemetry person" not in packet
            request = ExportTraceServiceRequest.FromString(packet)
            spans.extend(s for r in request.resource_spans for scope in r.scope_spans for s in scope.spans)
        agent = [span for span in spans if span.name == "agent.step"]
        assert agent and any(
            a.key == "helm.agent" and a.value.string_value == "intake" for s in agent for a in s.attributes
        )
        result = {
            "verified": True,
            "transport": "OTLP HTTP/protobuf to a local receiver",
            "received_agent_spans": len(agent),
            "medical_canary_absent": True,
            "applicant_name_absent": True,
        }
        (root / ".runtime/qa/telemetry.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps(result, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    verify()
