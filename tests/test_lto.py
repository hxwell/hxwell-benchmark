import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bench.config import load_config
from bench.dependencies import sha256
from bench.lto import cpp_defines, ir_format, validate_evidence, verify_link
from bench.run import verify_bundle


class LtoTests(unittest.TestCase):
    def test_all_three_cpp_cases_require_lto_and_other_targets_do_not(self):
        config, lock = load_config()
        cpp = [case for case in config["cases"] if case["target"] == "cpp"]
        self.assertEqual(3, len(cpp))
        for case in config["cases"]:
            defines = cpp_defines(case)
            self.assertEqual(case["target"] == "cpp", "HXCPP_OPTIMIZE_LINK" in defines)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dependencies.lock.json").write_text(json.dumps(lock))
            for value in (False, None, "true"):
                case = {**cpp[0], "lto": value}
                (root / "benchmark.json").write_text(json.dumps({**config, "cases": [case]}))
                with patch("bench.config.ROOT", root), self.assertRaisesRegex(ValueError, "LTO"):
                    load_config()

    def test_old_non_lto_cpp_bundles_are_not_accepted(self):
        config, lock = load_config()
        case = next(c for c in config["cases"] if c["id"] == "cpp-socket")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {"case": case, "haxe_version": "4.3.7", "haxelib_source_checksums": lock["haxelib_source_checksums"],
                        "build_os": platform.system(), "build_arch": platform.machine(),
                        "workloads_sha256": sha256(Path(__file__).resolve().parents[1] / "benchmark.json")}
            (root / "build.json").write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "LTO"):
                verify_bundle(root, case)

    def test_a_define_alone_is_not_linker_evidence(self):
        self.assertFalse(validate_evidence(None))
        self.assertFalse(validate_evidence({"enabled": True, "define": "HXCPP_OPTIMIZE_LINK"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "obj").mkdir()
            (root / "obj/Settings.o").write_bytes(b"machine code")
            (root / "obj/Immix.o").write_bytes(b"machine code")
            with self.assertRaisesRegex(ValueError, "LTO IR"):
                verify_link(root)
            (root / "obj/Settings.o").write_bytes(b"BC\xc0\xdelto")
            (root / "obj/Immix.o").write_bytes(b"BC\xc0\xdelto")
            (root / "lto-link.o").write_bytes(b"not an optimized machine object")
            with self.assertRaisesRegex(ValueError, "linker"):
                verify_link(root)


@unittest.skipUnless(os.environ.get("HXWELL_TEST_LTO"), "Set HXWELL_TEST_LTO to run native compiler/linker verification")
class NativeLtoTests(unittest.TestCase):
    def test_compiler_ir_and_linker_optimization_outputs_are_real(self):
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "obj").mkdir()
            (root / "Settings.cpp").write_text('extern int helper(int); int main() { return helper(41) == 42 ? 0 : 1; }\n')
            (root / "Immix.cpp").write_text('int helper(int value) { return value + 1; }\n')
            for name in ("Settings", "Immix"):
                subprocess.run([compiler, "-O2", "-flto", "-c", name + ".cpp", "-o", "obj/" + name + ".o"], cwd=root, check=True, capture_output=True, timeout=20)
            flags = ["-Wl,-object_path_lto,lto-link.o"] if platform.system() == "Darwin" else ["-save-temps"]
            subprocess.run([compiler, "-O2", "-flto", *flags, "obj/Settings.o", "obj/Immix.o", "-o", "program"], cwd=root, check=True, capture_output=True, timeout=30)
            subprocess.run([str(root / "program")], check=True, timeout=5)
            evidence = verify_link(root)
            self.assertTrue(validate_evidence(evidence))
            self.assertEqual(2, evidence["ir_objects"])
            self.assertGreater(len(evidence["link_outputs"]), 0)
