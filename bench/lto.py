"""Require actual LTO object code and linker output for every C++ bundle."""
from pathlib import Path
import re

from .dependencies import sha256


def cpp_defines(case):
    if case["target"] != "cpp":
        return []
    if case.get("lto") is not True:
        raise ValueError("Every C++ benchmark must require LTO")
    return ["HXCPP_OPTIMIZE_LINK", "HXCPP_VERBOSE", "HXCPP_COMPILE_THREADS=2"]


def ir_format(path):
    data = Path(path).read_bytes()
    if data[:4] in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
        return "llvm-bitcode"
    if data[:4] == b"\x7fELF" and b".gnu.lto_" in data:
        return "gcc-lto"
    return None


def machine_object(path):
    data = Path(path).read_bytes()
    return (data[:4] in (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce") and not ir_format(path))


def describe(path, base):
    return {"file": str(path.relative_to(base)), "sha256": sha256(path), "bytes": path.stat().st_size}


def verify_link(native, generated="Settings", runtime="Immix"):
    native = Path(native)
    objects = sorted((native / "obj").rglob("*.o"))
    probes = {}
    for label, name in (("generated", generated), ("runtime", runtime)):
        candidates = [path for path in objects if path.name == name + ".o" or path.name.endswith("_" + name + ".o")]
        ir = [path for path in candidates if ir_format(path)]
        if not ir:
            raise ValueError(f"Missing LTO IR for {label} C++ code ({name})")
        probes[label] = {**describe(ir[0], native), "format": ir_format(ir[0])}
    if probes["generated"]["format"] != probes["runtime"]["format"]:
        raise ValueError("Generated code and libhxcpp used different LTO toolchains")
    # GCC writes native LTRANS partitions only after executing its LTO passes.
    # Apple ld writes the combined native LTO object requested by object_path_lto.
    candidates = list(native.rglob("*.ltrans*.o")) + list(native.rglob("lto-link.o"))
    linked = [path for path in candidates if machine_object(path)]
    if not linked:
        raise ValueError("LTO linker produced no native optimization evidence")
    return {"enabled": True, "define": "HXCPP_OPTIMIZE_LINK", "probes": probes,
            "ir_objects": sum(ir_format(path) is not None for path in objects),
            "link_outputs": [describe(path, native) for path in sorted(set(linked))]}


def verify_libuv(build_dir):
    build_dir = Path(build_dir)
    objects = sorted((build_dir / "CMakeFiles/uv_a.dir").rglob("*.o"))
    if not objects or any(ir_format(path) is None for path in objects):
        raise ValueError("libuv must be built with working CMake IPO/LTO")
    return {"ipo": True, "ir_objects": len(objects), "probe": describe(objects[0], build_dir),
            "format": ir_format(objects[0])}


def valid_file(value):
    return (isinstance(value, dict) and isinstance(value.get("file"), str)
            and not Path(value["file"]).is_absolute() and ".." not in Path(value["file"]).parts
            and isinstance(value.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None
            and type(value.get("bytes")) is int and value["bytes"] > 0)


def validate_evidence(value):
    if not isinstance(value, dict) or value.get("enabled") is not True or value.get("define") != "HXCPP_OPTIMIZE_LINK":
        return False
    if type(value.get("ir_objects")) is not int or value["ir_objects"] < 2:
        return False
    probes = value.get("probes")
    if not isinstance(probes, dict) or not all(valid_file(probes.get(name)) for name in ("generated", "runtime")):
        return False
    kind = probes["generated"].get("format")
    if kind not in ("gcc-lto", "llvm-bitcode") or probes["runtime"].get("format") != kind:
        return False
    outputs = value.get("link_outputs")
    return isinstance(outputs, list) and len(outputs) > 0 and all(valid_file(entry) for entry in outputs)
