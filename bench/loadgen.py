"""Build and verify the pinned wrk variant that requires HTTP 200 natively."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from .config import ROOT
from .dependencies import command, sha256, verify_repository


def patch_bytes(lock):
    spec = lock["load_generator"]
    if spec["expected_status"] != 200 or spec["version"] != "4.2.0-hxwell-status-200":
        raise ValueError("The benchmark requires the locked strict HTTP 200 load generator")
    data = (ROOT / spec["patch"]["path"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != spec["patch"]["sha256"]:
        raise ValueError("wrk HTTP status patch checksum mismatch")
    return data


def verify_wrk(binary, lock):
    resolved = shutil.which(str(binary))
    if not resolved:
        raise ValueError("Build the strict HTTP 200 client with python -m bench build-wrk first")
    binary = Path(resolved).resolve()
    patch_bytes(lock)
    try:
        metadata = json.loads((binary.parent / "build.json").read_text())
    except (OSError, ValueError) as error:
        raise ValueError("Missing strict wrk provenance; run python -m bench build-wrk") from error
    expected = {"upstream": lock["repositories"]["wrk"], "policy": lock["load_generator"],
                "build_os": platform.system(), "build_arch": platform.machine(), "binary_sha256": sha256(binary)}
    if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("wrk source, status policy, host or binary checksum mismatch; rebuild the load generator")
    return binary, metadata


def build_wrk(lock, deps, output, openssl="/usr", make="make"):
    source = Path(deps).resolve() / "wrk"
    output = Path(output).resolve()
    verify_repository(source, lock["repositories"]["wrk"])
    data = patch_bytes(lock)
    if output.exists():
        return verify_wrk(output / "wrk", lock)[1]
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="build-strict-wrk-", dir=output.parent))
    build_source = work / "source"
    shutil.copytree(source, build_source, ignore=shutil.ignore_patterns(".git", "obj", "wrk"))
    patch = work / "status.patch"
    patch.write_bytes(data)
    with (work / "build.log").open("w") as log:
        command(["patch", "--batch", "--forward", "-p1", "-i", patch], cwd=build_source,
                stdout=log, stderr=subprocess.STDOUT, timeout=30)
        command([make, "-j2", f"WITH_OPENSSL={openssl}", f"VER={lock['load_generator']['version']}"],
                cwd=build_source, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    output.mkdir()
    shutil.copy2(build_source / "wrk", output / "wrk")
    shutil.copy2(work / "build.log", output / "build.log")
    metadata = {"upstream": lock["repositories"]["wrk"], "policy": lock["load_generator"],
                "build_os": platform.system(), "build_arch": platform.machine(), "binary_sha256": sha256(output / "wrk"),
                "patched_sources": {name: sha256(build_source / name) for name in ("src/wrk.c", "src/wrk.h", "src/script.c")}}
    (output / "build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return verify_wrk(output / "wrk", lock)[1]
