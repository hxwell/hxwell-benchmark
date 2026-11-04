import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import threading
import time
import unittest

from bench.charts import validate_trial
from bench.config import ROOT, load_config
from bench.dependencies import sha256
from bench.loadgen import verify_wrk
from bench.report import summarize
from bench.run import MARKER, parse_wrk
from test_harness import measurement, trial


class StrictStatusTests(unittest.TestCase):
    def test_native_status_evidence_is_required_even_with_zero_error_counters(self):
        for expected in (None, 201, 204, "200", True):
            value = measurement()
            if expected is None:
                value.pop("expected_status")
            else:
                value["expected_status"] = expected
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError):
                    parse_wrk(MARKER + json.dumps(value))

    def test_unverified_or_non_200_responses_never_receive_a_score(self):
        for change in (lambda t: t.pop("warmup"),
                       lambda t: t["wrk"].pop("expected_status"),
                       lambda t: t["wrk"]["errors"].update(status=1),
                       lambda t: t.update(warmup={"wrk": {**measurement(), "expected_status": 201}}),
                       lambda t: t.update(warmup={"wrk": {**measurement(), "errors": {**measurement()["errors"], "status": 1}}})):
            value = trial(1234)
            change(value)
            self.assertFalse(validate_trial(value))
            row = summarize([value], 1)[0]
            self.assertFalse(row["valid"])
            self.assertNotIn("rps_median", row)

    def test_missing_or_tampered_load_generator_build_is_rejected(self):
        _, lock = load_config()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root / "wrk"
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o755)
            with self.assertRaises(ValueError):
                verify_wrk(binary, lock)
            manifest = {"upstream": lock["repositories"]["wrk"], "policy": lock["load_generator"],
                        "build_os": platform.system(), "build_arch": platform.machine(), "binary_sha256": sha256(binary)}
            (root / "build.json").write_text(json.dumps(manifest))
            self.assertEqual(binary.resolve(), verify_wrk(binary, lock)[0])
            binary.write_text("#!/bin/sh\nexit 1\n")
            with self.assertRaises(ValueError):
                verify_wrk(binary, lock)
            manifest["binary_sha256"] = sha256(binary)
            manifest["policy"] = {**manifest["policy"], "expected_status": 201}
            (root / "build.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                verify_wrk(binary, lock)


@contextlib.contextmanager
def status_server(status, mixed=False):
    lock = threading.Lock()
    state = {"requests": 0}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *_):
            pass
        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError):
                pass
        def do_GET(self):
            with lock:
                state["requests"] += 1
                code = status if not mixed or state["requests"] == 5 else 200
            body = b"" if code in (204, 304) else b"test response"
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            if 300 <= code < 400:
                self.send_header("Location", "/not-followed")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            # Keep this a short correctness test with four loopback connections.
            time.sleep(0.003)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@unittest.skipUnless(os.environ.get("HXWELL_TEST_WRK"), "Set HXWELL_TEST_WRK to run the native load-generator integration tests")
class NativeStrictStatusTests(unittest.TestCase):
    def measure(self, status, mixed=False):
        _, lock = load_config()
        binary, _ = verify_wrk(os.environ["HXWELL_TEST_WRK"], lock)
        with status_server(status, mixed) as port:
            result = subprocess.run([str(binary), "-t2", "-c4", "-d1s", "--timeout", "1s", "-s", str(ROOT / "load/report.lua"),
                                     f"http://127.0.0.1:{port}/"], text=True, capture_output=True, timeout=8,
                                    env={**os.environ, "BENCH_SCENARIO": "plaintext"})
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        value = parse_wrk(result.stdout)
        self.assertEqual(200, value["expected_status"])
        self.assertGreater(value["requests"], 0)
        for error in ("connect", "read", "write", "timeout"):
            self.assertEqual(0, value["errors"][error], result.stdout)
        return value

    def test_every_non_200_status_is_counted_by_the_native_client(self):
        for status in (200, 201, 204, 302, 304, 307, 404, 500):
            with self.subTest(status=status):
                measured = self.measure(status)
                self.assertEqual(0 if status == 200 else measured["requests"], measured["errors"]["status"])
                value = trial(1234)
                value["wrk"] = measured
                self.assertEqual(status == 200, validate_trial(value))
                self.assertEqual(status == 200, summarize([value], 1)[0]["valid"])

    def test_one_transient_non_200_response_invalidates_a_whole_trial(self):
        value = trial(1234)
        value["wrk"] = self.measure(201, mixed=True)
        self.assertGreater(value["wrk"]["requests"], 10)
        self.assertEqual(1, value["wrk"]["errors"]["status"])
        self.assertFalse(validate_trial(value))
        self.assertNotIn("rps_median", summarize([value], 1)[0])
