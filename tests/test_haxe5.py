import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench.build import build
from bench.config import compiler_version, load_config
from bench.run import validate_health


class Haxe5Tests(unittest.TestCase):
    def test_compiler_variants_are_distinct_and_5_is_not_silently_built_with_4(self):
        config, lock = load_config()
        upstream = next(case for case in config["cases"] if case["id"] == "jvm-crossbyte")
        preview = next(case for case in config["cases"] if case["id"] == "jvm-crossbyte5")
        self.assertEqual("4.3.7", compiler_version(config, upstream))
        self.assertEqual("5.0.0-preview.1", compiler_version(config, preview))
        self.assertEqual(upstream["driver"], preview["driver"])
        self.assertEqual(upstream["io_threads"], preview["io_threads"])
        with tempfile.TemporaryDirectory() as directory, patch("bench.build.capture", return_value="4.3.7"):
            with self.assertRaisesRegex(ValueError, "requires Haxe 5"):
                build(config, lock, preview, directory, Path(directory) / "output")

    def test_actual_health_must_attest_the_preview_compiler_and_virtual_requests(self):
        config, _ = load_config()
        case = next(case for case in config["cases"] if case["id"] == "jvm-crossbyte5")
        health = {"run_id": "owned", "case_id": case["id"], "target": "jvm", "driver": "crossbyte", "workers": 2,
                  "haxe_version": "5.0.0-preview.1", "virtual_thread": True, "io_virtual_thread": False}
        validate_health(health, case, 2, "owned", {})
        for compiler in ("4.3.7", "5.0.0", None):
            with self.assertRaisesRegex(RuntimeError, "compiler version"):
                validate_health({**health, "haxe_version": compiler}, case, 2, "owned", {})
        with self.assertRaises(RuntimeError):
            validate_health({**health, "virtual_thread": False}, case, 2, "owned", {})

    def test_preview_is_limited_to_the_verified_upstream_jvm_driver(self):
        config, lock = load_config()
        preview = next(case for case in config["cases"] if case["id"] == "jvm-crossbyte5")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dependencies.lock.json").write_text(json.dumps(lock))
            for change in ({"target": "cpp"}, {"driver": "socket"}, {"haxe_version": "5.0.0"}, {"crossbyte_variant": "jvm-virtual"}):
                (root / "benchmark.json").write_text(json.dumps({**config, "cases": [{**preview, **change}]}))
                with patch("bench.config.ROOT", root), self.assertRaises(ValueError):
                    load_config()
