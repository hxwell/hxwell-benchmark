"""Compare the proposed driver limits with and without runtime spreading."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench.config import load_config, select_cases
from bench.run import run


def main():
    config, lock = load_config()
    output = ROOT / "out/diagnosis"
    output.mkdir(parents=True, exist_ok=False)
    summary = {"configuration": {"maxConnections": 10000, "maxConcurrentRequests": 2000, "poolSize": 16,
                                 "rateLimitDisabled": True, "maxWaiting": 256},
               "profile": config["profiles"]["stress"], "comparisons": []}
    for runtime_count in (0, 2):
        if runtime_count:
            os.environ["DIAG_RUNTIMES"] = str(runtime_count)
        else:
            os.environ.pop("DIAG_RUNTIMES", None)
        destination = output / f"recommended-io{runtime_count}"
        error = None
        try:
            run(config, lock, select_cases(config, "jvm-crossbyte"), ROOT / "out/build", destination,
                "stress", str(ROOT / "dependencies/wrk/wrk"))
        except RuntimeError as failure:
            if not str(failure).startswith("Some benchmarks were invalid;"):
                raise
            error = str(failure)
        report = json.loads((destination / "results.json").read_text())
        assert len(report["trials"]) == report["expected_trials"] == 9
        comparison = {"runtimeCount": runtime_count, "valid": 0, "expected": 9,
                      "error": error, "trials": []}
        for trial in report["trials"]:
            start = trial["health"]
            end = trial["health_after"]
            for health in (start, end):
                assert health["virtual_thread"] is True
                observed = health["diagnosis"]
                for field in ("maxConnections", "maxConcurrentRequests", "poolSize", "maxWaiting"):
                    assert observed[field] == summary["configuration"][field], (field, observed)
                assert observed["runtimeCount"] == runtime_count
            comparison["valid"] += int(trial["valid"])
            result = {"workload": trial["workload"], "repetition": trial["repetition"], "valid": trial["valid"],
                      "refused_delta": end["diagnosis"]["refused"] - start["diagnosis"]["refused"],
                      "warmup_errors": trial.get("warmup", {}).get("wrk", {}).get("errors"),
                      "measure_errors": trial.get("wrk", {}).get("errors"), "error": trial.get("error")}
            comparison["trials"].append(result)
        summary["comparisons"].append(comparison)
        (output / "user-config-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("COMPARISON", json.dumps(comparison), flush=True)
    assert summary["comparisons"][0]["valid"] == 9, "Proposed configuration with default runtime count failed"


if __name__ == "__main__":
    main()
