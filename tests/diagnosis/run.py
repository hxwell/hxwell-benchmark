"""Controlled JVM diagnosis; this records failures, it does not turn them into scores."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench.run import affinity, load, pinned, request, stop_group

OUT = ROOT / "out/diagnosis"
OUT.mkdir(parents=True, exist_ok=True)


def command(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def prepare():
    work = next((ROOT / "out/build").glob("build-jvm-crossbyte-*"))
    with (OUT / "probe-build.log").open("w") as log:
        command(["haxe", "-lib", "crossbyte", "-lib", "hxjava", "-cp", ROOT / "tests/diagnosis",
                 "-cp", ROOT / "dependencies/hxwell/src", "-D", "analyzer-optimize", "-main", "ProbeMain",
                 "--jvm", OUT / "probe.jar"], cwd=work, stdout=log, stderr=subprocess.STDOUT)
    path = ROOT / "dependencies/wrk/src/wrk.c"
    source = path.read_text()
    source = source.replace("    size_t n;\n\n    do {\n        switch (sock.read(c, &n)) {",
                            "    size_t n;\n    status read_result = OK;\n\n    do {\n        switch (read_result = sock.read(c, &n)) {", 1)
    before = "error:\n    c->thread->errors.read++;\n    reconnect_socket(c->thread, c);"
    after = """error:
    {
        static unsigned int diagnostic_count = 0;
        if (__sync_fetch_and_add(&diagnostic_count, 1) < 24) {
            fprintf(stderr, "WRK_READ_DIAG status=%d errno=%d parser=%s detail=%s\\n", read_result, errno,
                    http_errno_name(HTTP_PARSER_ERRNO(&c->parser)), http_errno_description(HTTP_PARSER_ERRNO(&c->parser)));
        }
    }
    c->thread->errors.read++;
    reconnect_socket(c->thread, c);"""
    if before not in source:
        raise ValueError("Unexpected pinned wrk source")
    path.write_text(source.replace(before, after, 1))
    with (OUT / "client-instrumentation.diff").open("w") as file:
        command(["git", "diff", "--", "src/wrk.c"], cwd=ROOT / "dependencies/wrk", stdout=file)
    with (OUT / "client-build.log").open("w") as log:
        command(["make", "-j2", "WITH_OPENSSL=/usr", "VER=4.2.0"], cwd=ROOT / "dependencies/wrk", stdout=log, stderr=subprocess.STDOUT)


def tcp_counters():
    result = {}
    path = Path("/proc/net/netstat")
    if path.exists():
        lines = path.read_text().splitlines()
        for labels, values in zip(lines[0::2], lines[1::2]):
            a, b = labels.split(), values.split()
            if a[0] == "TcpExt:":
                fields = dict(zip(a[1:], map(int, b[1:])))
                for key in ("ListenOverflows", "ListenDrops", "TCPAbortOnData", "TCPAbortOnClose", "TCPAbortOnMemory", "TCPAbortOnTimeout"):
                    result[key] = fields.get(key)
    return result


def run_case(kind, runtimes, repetition, cpus):
    label = f"{kind}-io{runtimes}-r{repetition}"
    directory = OUT / label
    directory.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = uuid.uuid4().hex
    env = dict(os.environ, BENCH_PORT=str(port), BENCH_WORKERS="2", BENCH_MAX_CONNECTIONS="4000", BENCH_RUN_ID=token,
               DIAG_RUNTIMES=str(runtimes), DIAG_MODE=kind)
    args = ["java", "-XX:ActiveProcessorCount=2", "-Djdk.virtualThreadScheduler.parallelism=2", "-Xms256m", "-Xmx256m"]
    if kind == "driver":
        cwd = ROOT / "out/build/jvm-crossbyte"
        args += ["-cp", "server.jar", "hx.well.HxWell"]
    else:
        cwd = directory
        args += ["-jar", str(OUT / "probe.jar")]
    record = {"label": label, "kind": kind, "runtimes": runtimes, "repetition": repetition, "command": pinned(args, cpus["server"]),
              "phases": [], "tcp_before": tcp_counters()}
    with (directory / "server.log").open("w") as log:
        process = subprocess.Popen(pinned(args, cpus["server"]), cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Server exited before readiness")
                try:
                    health = json.loads(request(port, "/health")[0])
                    if kind != "driver" or health.get("run_id") == token:
                        record["health_start"] = health
                        break
                except (OSError, ValueError):
                    time.sleep(.1)
            else:
                raise TimeoutError("Readiness timed out")
            for phase, seconds in (("warmup", 5), ("measure", 10)):
                started = time.time()
                data = load(ROOT / "dependencies/wrk/wrk", process, port, {"id": "plaintext", "path": "/plaintext"}, 1000, 2, seconds,
                            cpus["client"], directory / (phase + ".log"), 10)
                entry = {"phase": phase, "started_at": started, "finished_at": time.time(), **data}
                if phase == "measure":
                    try:
                        entry["health_after"] = json.loads(request(port, "/health")[0])
                    except Exception as error:
                        entry["health_error"] = str(error)
                record["phases"].append(entry)
                if phase == "measure":
                    print(label, phase, data["wrk"]["errors"], round(data["rps"]), entry.get("health_after"), flush=True)
        except Exception as error:
            record["error"] = str(error)
        finally:
            stop_group(process)
    record["tcp_after"] = tcp_counters()
    record["tcp_delta"] = {key: record["tcp_after"][key] - before for key, before in record["tcp_before"].items()
                           if before is not None and record["tcp_after"].get(key) is not None}
    (directory / "results.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def exact_benchmark():
    # Exercise the original controller, including the immediate handoff from
    # the warmup client to a fresh measurement client and all three routes.
    env = dict(os.environ, DIAG_RUNTIMES="2")
    config = [sys.executable, "-m", "bench", "run", "--cases", "jvm-crossbyte", "--profile", "stress",
              "--wrk", str(ROOT / "dependencies/wrk/wrk")]
    results = []
    for kind, build in (("diagnostic", ROOT / "out/build"), ("original", ROOT / "out/original-build")):
        output = OUT / ("exact-" + kind)
        with (OUT / ("exact-" + kind + ".log")).open("w") as log:
            done = subprocess.run(config + ["--bundles", str(build), "--out", str(output)], cwd=ROOT,
                                  env=env, stdout=log, stderr=subprocess.STDOUT)
        results.append({"kind": kind, "exit_code": done.returncode})
        print("EXACT", kind, done.returncode, flush=True)
    (OUT / "exact-exit-codes.json").write_text(json.dumps(results, indent=2))


def build_original():
    names = ("app/src/hx/well/provider/BenchmarkProvider.hx", "app/src/hx/well/config/InstanceConfig.hx")
    saved = {name:(ROOT / name).read_bytes() for name in names}
    try:
        for name in names:
            (ROOT / name).write_bytes(subprocess.check_output(["git", "show", "23ea850:" + name], cwd=ROOT))
        with (OUT / "original-build.log").open("w") as log:
            command([sys.executable, "-m", "bench", "build", "--case", "jvm-crossbyte", "--out", ROOT / "out/original-build"],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    finally:
        for name, data in saved.items():
            (ROOT / name).write_bytes(data)


def main():
    prepare()
    build_original()
    exact_benchmark()
    cpus = affinity()
    if len(cpus["server"]) != 2 or len(cpus["client"]) < 2:
        raise RuntimeError("This controlled diagnosis requires at least 4 CPUs")
    data = {"affinity": cpus, "java": subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True),
            "somaxconn": Path("/proc/sys/net/core/somaxconn").read_text().strip(), "cases": []}
    scenarios = [("buffered", 2), ("posted-stream", 2)]
    for kind, runtimes in scenarios:
        for repetition in (1, 2):
            data["cases"].append(run_case(kind, runtimes, repetition, cpus))
            (OUT / "results.json").write_text(json.dumps(data, indent=2) + "\n")
    shutil.copy2(ROOT / "dependencies.lock.json", OUT / "dependencies.lock.json")


if __name__ == "__main__":
    main()
