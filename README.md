# HxWell target/driver benchmarks

<!-- benchmark-charts:start -->
## Summary

**Complete** · [Run #28 (attempt 1)](https://github.com/hxwell/hxwell-benchmark/actions/runs/41881955557) · profile `stress` · 81/81 valid trials.
Source: [`36484c4`](https://github.com/hxwell/hxwell-benchmark/commit/36484c4a84ac6482c7f464a4137af6509c04b694). Finished: `2026-11-04T18:24:56.500614+00:00`.

All selected measurements passed.

![Summary: all targets, throughput, p99 latency and memory](docs/benchmarks/latest/summary.svg?run=41881955557-1&layout=4)

Each chart shows throughput, p99 latency and peak RSS for plaintext, JSON and echo. Case colors are consistent across views; each target uses its own axis scales for detail. Workloads and connection levels remain separate.

## JVM

![JVM benchmark results](docs/benchmarks/latest/target-jvm.svg?run=41881955557-1&layout=4)

## JavaScript / Node

![JavaScript / Node benchmark results](docs/benchmarks/latest/target-js.svg?run=41881955557-1&layout=4)

## C++ / libhxcpp / LTO

![C++ / libhxcpp / LTO benchmark results](docs/benchmarks/latest/target-cpp.svg?run=41881955557-1&layout=4)

[Chart data and provenance](docs/benchmarks/latest/manifest.json) · Full raw results are in the linked run's `benchmark-results` artifact.
Only the selected targets, cases and connection levels from this run are shown; older runs are not mixed into these charts.

<!-- benchmark-charts:end -->

CI benchmarks for the same HxWell application across supported compiler targets
and HTTP drivers. The suite builds release applications, checks their responses,
then measures them with a pinned `wrk` client. This is a benchmark harness, not a
set of claimed performance numbers.

## Included cases

| Case | Target | Driver | Request execution |
| --- | --- | --- | --- |
| `jvm-socket` | JVM | HxWell Socket | Platform-thread pool |
| `jvm-undertow` | JVM | Undertow | XNIO worker pool |
| `jvm-crossbyte` | JVM | Upstream Crossbyte | Virtual requests, platform I/O runtime |
| `jvm-crossbyte-virtual` | JVM | HxWell Crossbyte fork | Virtual requests and virtual I/O runtime |
| `js-nodehttp` | JavaScript/Node | NodeHTTP | Cluster workers |
| `cpp-socket` | C++/libhxcpp | HxWell Socket | Platform-thread pool |
| `cpp-crossbyte` | C++/libhxcpp | Crossbyte | Worker pool, built-in polling |
| `cpp-crossbyte-libuv` | C++/libhxcpp | Crossbyte + libuv | Worker pool, libuv polling |
| `jvm-crossbyte5` | JVM / Haxe 5.0.0-preview.1 | Upstream Crossbyte | Virtual requests, platform I/O runtime |

The actual compiler version, target, driver, worker count and JVM virtual-thread state are checked
through `/health`; a mismatched build is never measured. Every C++ case must
report the pinned `libhxcpp` version. Crossbyte C++ cases inspect the actual
request I/O runtime before and after each trial: the built-in case must stay on
the built-in poller, and the libuv case must stay on libuv. A libuv fallback or
wrong linked libuv version invalidates the measurement. No driver source is
patched for benchmarking. PHP's development server and unsupported
target/driver combinations are not silently substituted for these cases.

All three C++ cases require **LTO**: the Haxe-generated code and libhxcpp runtime
are compiled with `HXCPP_OPTIMIZE_LINK`, and the executable linker explicitly
uses `-flto -O2`. The static libuv library additionally requires CMake IPO.
Build verification checks generated and runtime object IR plus native LTO linker
outputs; a define alone is insufficient. These checks and compiler/source
provenance are retained in `build.json` and `results.json`. `/health` must also
attest the LTO build flag. Legacy C++ bundles without this evidence are rejected.
GCC builds retain LTRANS objects; macOS builds retain the combined native LTO
object emitted by Apple's linker. C++ build jobs have a 35-minute budget for
compilation and LTO linking.

The current driver snapshot uses a single asynchronous handoff for complete
responses up to 32 KiB, and a blocking request queue for C++ workers.
The virtual-I/O and Haxe 5 builds also run the driver's existing HTTP/1.1, HTTP/2, TLS,
WebSocket, framework-feature and core/security regression suites against the
selected runtime before producing their benchmark bundles. Their compatibility
reports are saved separately from the performance results.

`jvm-crossbyte5` pins Haxe **5.0.0-preview.1** and `hx4compat` **1.0.0**.
It uses the same adapter source, upstream Crossbyte commit, Java 21, heap limits,
request limits and I/O settings as `jvm-crossbyte` (Haxe 4.3.7). A Haxe-5-only
classpath supplies type aliases for moved Java primitive/class helpers and the
legacy HTTP/2 secondary-type name, plus a `HashMap.size()` extension for the
unmodified haxe-concurrent 5.1.5 package; the runtime SDK is not patched. `/health`
embeds the real compiler version through a compile-time macro and must agree
with the build provenance. Both cases already hand requests to HxWell's
`jvm.thread.VirtualThread.create(work).start()` entry before `HttpHandler.process()`.
The driver uses explicit nullable status selection to preserve the default 200
on Haxe 5 preview 1.

The common workloads are GET plaintext, GET freshly serialized JSON and POST
JSON parsing/echo. They use the ordinary `hx.well.HxWell` application startup,
configuration, providers, routes and driver interfaces. Middleware is explicitly
empty; there is no database or session I/O in these transport-focused workloads.

## CI and measurement method

[The workflow](.github/workflows/benchmark.yml) runs on pushes to `main`, pull
requests, and manual dispatch:

1. Test the harness and validate the requested matrix.
2. Build cases in parallel, using pinned source/library versions.
3. Download the binaries to **one measurement job** and run cases sequentially.
   Thus the comparison is not assembled from differently loaded matrix runners.
4. Warm up each workload, measure repeated trials, and preserve raw results plus
   a JSON/CSV/Markdown summary in the `benchmark-results` artifact and job summary.
5. Generate one combined summary SVG, followed by separate JVM, JavaScript/Node
   and C++ charts for the selected targets. Each chart includes
   throughput, p99 latency and peak RSS, with separate workload/connection panels
   and consistent case colors across views. Target charts use their own axis scales
   to keep within-target differences visible. A separate publishing job
   updates the managed README section and `docs/benchmarks/latest/` for each
   completed `main` push or manual run, including unsuccessful runs.

The latest run replaces the chart snapshot; selected subsets and connection
levels are labeled and never merged with older measurements. Invalid/missing
groups have no bar, and smoke runs show validation status rather than performance
scores. A run link, source commit and UTC completion timestamp accompany the plots.
PR/other-branch runs produce chart artifacts without changing `main`; cancelled
runs do not replace the snapshot. Older runs/retries cannot overwrite newer ones.

Only the publishing job has `contents: write`. It regenerates plots from validated
raw data and updates only the README, generated SVGs and manifest. Obsolete target
charts are removed when a run selects fewer targets; unrelated files are preserved.
The publisher uses a non-forced, fast-forward Git reference update. On a concurrent edit it rereads the latest README and preserves
text outside the chart markers. Its `GITHUB_TOKEN` commit does not start another
benchmark; generated README/chart paths are also excluded from push triggers.
On Linux, available CPUs are split into disjoint server and client sets using
`taskset`; every child, including Node cluster workers, inherits its set. The
server worker budget equals the size of its CPU set unless explicitly overridden.
Client threads are adjusted so `wrk`'s requested connection count is exact.
The allocation, machine information, runtime versions, commands and revisions are
recorded. Without Linux affinity support, the report explicitly says pinning was
unavailable. The orchestrator itself is not CPU-isolated.

Each repetition starts a fresh server process group; case order is seeded and
shuffled between repetitions. Readiness is polled over HTTP using a unique run
token. Every workload has payload, status, compression and persistent-connection
preflights before and after load. The application suppresses Haxe per-request
traces and Crossbyte logging, and disables response compression and Crossbyte's
default per-address rate limiter. Crossbyte's keep-alive request-count cap is
disabled for this load test. All cases request HTTP/1.1 keep-alive and identity
encoding; this is not an HTTP/2, TLS, WebSocket or full middleware benchmark.

All JVM Crossbyte cases use `maxConnections=10000`, `maxConcurrentRequests=2000`,
`poolSize=16` and `runtimeCount=0`, with per-address rate limiting disabled.
Connections stay on the listener's I/O runtime, avoiding the bounded connection
handoff queue under connection bursts; HxWell requests still run on virtual
threads. The JVM driver does not use the configured pool size to execute
requests. The fork case uses the same base Crossbyte commit and adds
`-D crossbyte_jvm_virtual_threads`, changing child runtime owners to Java 21
virtual threads. The upstream case keeps platform I/O threads. `/health` posts a
probe to the request socket's actual runtime and checks its Java thread type;
both cases must also report a virtual HTTP application handler. The fork source
and commit are recorded separately in each build, so a mislabeled source or a
fallback thread type fails validation. See the [fork documentation](https://github.com/hxwell/crossbyte/blob/jvm-virtual-threads/JVM_VIRTUAL_THREADS.md).
Other Crossbyte targets retain the configured worker pool and separate
I/O runtimes.

The JVM heap is fixed at 256 MiB; Node's old-space limit is 256 MiB per process.
These are runtime settings, not equivalent total-memory limits. Socket pool,
XNIO pool, virtual threads and Node processes are different concurrency models;
the results retain those labels rather than pretending the same worker count
means the same implementation.

`wrk` performs native request generation. Its Lua script sets a fixed method/body
and writes the final statistics; it has **no per-request or response callback**.
Response bodies, content types and persistent connections are checked before
and after the measured interval. During load, `wrk` reports
HTTP status errors for **every response whose status is not exactly 200**,
including other 2xx responses and redirects. The pinned client applies
`load/wrk-status-200.patch` to the existing native C counter, with no Lua
per-response callback. The native summary must attest `expected_status: 200`;
missing evidence, any non-200 response in warmup or measurement, or a mismatched
client build invalidates the trial and prevents a performance score. Both the
client binary and patch hashes are verified and retained in `results.json`.
The locked haxe-concurrent synchronized-map source checksum also rejects locally patched copies
with the same package version. For a private Haxelib installation, set
`BENCH_HAXELIB_REPO` to that repository directory.
Reports use schema version 2. Run #23 and earlier used the previous `>399`
status counter; their historical charts do not prove that every load response
was 200. Those legacy reports cannot receive scores from the new publisher.
See the upstream
[wrk scripting API](https://github.com/wg/wrk/blob/4.2.0/SCRIPTING).

The Crossbyte runtime is pinned to upstream `45628a5`; the virtual-I/O fork
merges that same upstream base and adds only its runtime-thread option. This
base includes the connection-handoff backpressure fix: when every child queue
is full, new connections wait in the kernel's listen queue instead of being
accepted and immediately closed. Workload, concurrency and connection limits
are unchanged.

## Haxe 5 compiler comparison

[Run #27](https://github.com/hxwell/hxwell-benchmark/actions/runs/41872715214) completed
**81/81 stress trials** across all nine cases with the native strict-HTTP-200
client. Every warmup and measurement had zero status, connection, read, write
or timeout errors. `jvm-crossbyte` used Haxe **4.3.7** and `jvm-crossbyte5` used
**5.0.0-preview.1** on the same Java 21 host, CPU affinity, heap and server limits.
Both used adapter `8dca380`, HxWell `d2dba6f`, upstream Crossbyte `45628a5`,
virtual application requests and platform I/O runtime threads. Compiler and
actual thread types were checked before and after every trial.

| Workload | Haxe 4 req/s | Haxe 5 req/s | Median change | Haxe 4 p99 | Haxe 5 p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plaintext | 41,075 | 39,696 | -3.4% | 51.09 ms | 54.51 ms |
| JSON | 40,481 | 40,509 | +0.1% | 46.61 ms | 43.74 ms |
| Echo | 37,002 | 36,623 | -1.0% | 50.32 ms | 51.24 ms |

These are medians of three repetitions at 1,000 connections. The sample ranges
overlap for every workload. These measurements do not establish a consistent
compiler speed advantage. Neither client was saturated. Haxe 5
used about 2–5 MiB more peak RSS across these workloads.
[Raw repetitions, settings and source provenance](docs/benchmarks/comparisons/haxe5-vs-haxe4-41872715214.json)
are retained for this comparison.

## Historical driver-58 JVM comparison

[Run #22](https://github.com/hxwell/hxwell-benchmark/actions/runs/41545569490)
uses adapter `58d39ce`, upstream runtime `45628a5` and the same-base virtual-I/O
fork `3d23486`. All 90 stress trials passed, including 9/9 for each JVM variant.
The recorded run used 1,000 connections and three repeats.

| Workload | Platform I/O req/s | Virtual I/O req/s | Median change | Platform p99 | Virtual p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plaintext | 40,885 | 42,648 | +4.3% | 65.52 ms | 49.28 ms |
| JSON | 41,604 | 42,451 | +2.0% | 43.49 ms | 42.55 ms |
| Echo | 37,613 | 38,127 | +1.4% | 47.62 ms | 47.98 ms |

Both cases used virtual HTTP application handlers. The actual I/O owner was
probed before and after each trial: platform for upstream, virtual for the fork.
Neither client was saturated. Repeat ranges overlap, so the small median
throughput differences do not establish a consistent speed advantage. Peak RSS
was about 257–273 MiB; the virtual case used roughly 1–6 MiB more by workload.
[Raw samples, settings and source provenance for that run](docs/benchmarks/comparisons/driver58-sdk456-jvm-41545569490.json)
are retained separately from the older-driver comparisons below.

## Historical JVM virtual-runtime comparisons

These archived comparisons used adapter commit `c08ad42`. The current benchmark
uses adapter `8dca380`, which retains the small-response path introduced in `58d39ce` and sends a complete
response in one asynchronous runtime handoff. The upstream and virtual-I/O
cases both use that updated adapter with the same limits. Current measurements
are in the generated charts above; the archived numbers below describe the old
adapter and are retained with their original source provenance.

[Run #16](https://github.com/hxwell/hxwell-benchmark/actions/runs/41388256606)
compared the two Crossbyte cases on one AMD EPYC runner with two server CPUs
and two separate client CPUs: Java 21, 1,000 connections, 5 s warmup, 10 s
measurement and three repetitions. All 18 trials had zero client errors; neither
client was saturated. Both application handlers were virtual; the I/O owner was
confirmed platform for upstream and virtual for the fork.

| Workload | Upstream req/s | Fork req/s | Throughput change | Upstream p99 | Fork p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plaintext | 23,431 | 27,507 | +17.4% | 91.08 ms | 85.95 ms |
| JSON | 24,747 | 28,909 | +16.8% | 59.97 ms | 56.51 ms |
| Echo | 22,818 | 27,835 | +22.0% | 67.82 ms | 53.86 ms |

Throughput and p99 are medians of three trials. Peak process-group RSS stayed
about 357–361 MiB for both implementations. These numbers describe this paired
run; the current all-target charts above are regenerated independently.
[Samples, settings and source provenance](docs/benchmarks/comparisons/jvm-virtual-runtime-41388256606.json)
record the measured fork commit and show that its runtime sources are identical
to the subsequently pinned fork commit, which only corrects a JVM test assertion.

The subsequent [all-target run #17](https://github.com/hxwell/hxwell-benchmark/actions/runs/41389396916)
passed all 90 trials. On its AMD EPYC 7763 host, the fork increased throughput by
31.3% / 41.5% / 30.0% for plaintext / JSON / echo. JSON p99 increased from
132.89 ms to 262.74 ms; peak RSS increased by 4–18 MiB across the three workloads.
The fork therefore did not improve every latency or memory metric.
[Repeated-run samples and provenance](docs/benchmarks/comparisons/jvm-virtual-runtime-41389396916.json)
retain this result separately. The two runs used different hosted CPU models;
compare implementations within each run rather than absolute RPS between runs.

## Profiles

| Profile | Warmup per trial | Measurement | Repetitions | Connections | Request timeout | Use |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| `smoke` | 1 s | 1 s | 1 | 4 | 2 s | Harness validation only; used for PRs |
| `ci` | 3 s | 5 s | 3 | 32 | 2 s | Default push/manual run |
| `full` | 5 s | 10 s | 3 | 16, 128 | 2 s | Longer manual comparison |
| `stress` | 5 s | 10 s | 3 | 1000 | 10 s | High-concurrency manual run |

Defaults are in `benchmark.json`. Full runs are bounded by the workflow's
50-minute timeout. CI benchmarks can consume several runner minutes; workflows
do not run on a recurring schedule. In manual dispatch, choose a profile and
`all` or a comma-separated list of the case IDs above.

`stress` maintains **1,000 concurrent HTTP/1.1 connections** for every selected
case and workload. Throughput is measured independently in requests/second.
The longer request timeout allows queueing under this load; errors/timeouts still
invalidate a trial. Running all nine cases produces 81 trials and about 20 minutes
of warmup/load, plus startup and reporting. The README and charts are updated by
the selected profile's completed main-branch run.

Before starting the servers and clients, the harness checks the process file
descriptor limit and raises its soft limit when the hard limit permits it.
Insufficient hard limits fail with an explicit error. Requested connections are
divided exactly across client threads, and descriptor limits, timeout, CPU use
and possible client saturation are recorded in the report. Warmup measurements
and post-error backend diagnostics are retained; failed trials are not retried
into a passing score. This active-connection
load measures the complete HTTP path; backend-only costs and many idle sockets
require a separate poll benchmark.

For a focused C++ poll-backend comparison in GitHub Actions:

```sh
gh workflow run benchmark.yml --ref main -f profile=stress \
  -f cases=cpp-crossbyte,cpp-crossbyte-libuv
```

Choose `cases=all` to run the stress profile across every target/driver.

## Results and interpretation

- `results.json`: every trial, errors, preflights, build provenance, commands,
  latency distributions, server/client CPU and peak process-group RSS samples.
- `summary.csv` and `summary.md`: median/min/max requests per second and medians
  of each repetition's p50/p95/p99. A median of per-trial p99 is **not** a pooled
  latency percentile.
- Per-trial warmup/client logs and per-server logs, including failed samples.

Zero completed requests, wrk errors/timeouts, failed preflights, server exits,
changed process groups and missing builds fail the run. An incomplete or invalid
group is displayed as `INVALID` without a performance score. Other cases still
run when one case fails. There is no arbitrary throughput pass/fail threshold.

Linux `/proc` measurements sample the whole server process group, including Node
workers. CPU is reported in seconds and core equivalents. Peak RSS is a sampled
sum across processes, not PSS: shared pages may be counted more than once. Client
CPU saturation is flagged because the client can limit observed throughput. On
other OSes these `/proc` fields are unavailable, not zero. The load is closed-loop
and has no fixed offered arrival rate. Hosted CI hardware, noisy neighbors, JIT,
GC and CPU frequency make these trend/comparison observations, not production
capacity or latency-SLO guarantees. Compare only runs with compatible settings,
workloads and hardware; retain the raw trials.

## Reproducible dependencies

`dependencies.lock.json` pins HxWell, the Crossbyte adapter, Crossbyte, Emitter,
OpenFL libhxcpp, crossbyte-libuv, native libuv, wrk and Haxelib versions. All three
C++ cases use the same [OpenFL libhxcpp commit](https://github.com/openfl/libhxcpp/tree/04f436bc68c0f6f119ca1863c12974693ae8bcc7).
Each build prepares a separate runtime copy and registers both `libhxcpp` and
Haxe's compatibility name `hxcpp` to that copy. Build metadata and the live
health endpoint identify the runtime as libhxcpp 6.0.0.

The [crossbyte-libuv extension](https://github.com/DimensionscapeOrg/crossbyte-libuv/tree/49344cefa751569a20a56e530a793fab958da2fa)
is installed before the first Crossbyte runtime exists and enabled only for
`cpp-crossbyte-libuv`. CMake builds libuv 1.51.0 from its pinned source into a
static archive in the build directory; the executable needs no system libuv
package. Its source revision, archive hash and linked runtime version are
recorded. The other C++ case keeps Crossbyte's built-in poll backend.
On macOS, the libuv build preincludes the SDK's `uuid_t` definition to avoid a
case-insensitive collision with Haxe's generated `uuid/Uuid.h`; dependency
sources remain unchanged.

Undertow jars have SHA-256 hashes verified against the
official Maven artifacts. Node's native `deasync` dependency uses
`app/package-lock.json`. Builds create a local Haxelib repository in a temporary
build directory; they do not change global dev registrations.

`hxwell-crossbyte` is included as a versioned snapshot. Its runtime sources at the
locked commit are stored under `vendor/hxwell-crossbyte`, with the original
license and per-file SHA-256 provenance in `snapshot.json`. This keeps the driver source and its checksums self-contained for CI. The vendored
adapter is compiled as its own Haxelib package. Changes to it are made upstream,
then refreshed as a reviewed snapshot:

```sh
# First update the locked revision, then remove the old vendor directory after review.
python3 -m bench vendor-crossbyte --source /path/to/hxwell-crossbyte
```

The other source dependencies are fetched at immutable commits. A dirty or
different existing dependency checkout is refused. Application artifacts include
hashes and are transferred as tar archives to preserve executable modes.

## Run locally

Use Python 3.12+, Haxe **4.3.7** (or **5.0.0-preview.1** for `jvm-crossbyte5`), Git, the selected runtimes and the strict wrk build on a
POSIX host. Node builds use Node 22.13.0 and npm; JVM runs require Java 21+.
C++ builds require a C++ compiler, and the libuv case also requires CMake.
`bench fetch` downloads the locked libhxcpp and libuv sources; `bench build`
prepares the runtime tools and static libuv library automatically.

```sh
haxelib install haxe-concurrent 5.1.5
haxelib install uuid 2.4.1
haxelib install crypto 1.3.0
haxelib install hxjava 4.2.0
# For the corresponding optional targets:
haxelib install hxnodejs 12.2.0

python3 -m pip install -r requirements-charts.txt
python3 -m bench fetch
python3 -m bench build-wrk --openssl /usr
HXWELL_TEST_LTO=1 HXWELL_TEST_WRK="$PWD/out/wrk/wrk" python3 -m unittest discover -s tests -v

python3 -m bench build --case jvm-socket --haxe /path/to/haxe-4.3.7/haxe
python3 -m bench build --case jvm-crossbyte --haxe /path/to/haxe-4.3.7/haxe
# Optional compiler comparison (also install hx4compat 1.0.0):
python3 -m bench build --case jvm-crossbyte5 --haxe /path/to/haxe-5.0.0-preview.1/haxe
python3 -m bench run --cases jvm-socket,jvm-crossbyte \
  --profile smoke --wrk "$PWD/out/wrk/wrk" --out out/local-smoke

# Native C++ comparison, including the Crossbyte driver:
python3 -m bench build --case cpp-socket --haxe /path/to/haxe-4.3.7/haxe
python3 -m bench build --case cpp-crossbyte --haxe /path/to/haxe-4.3.7/haxe
python3 -m bench build --case cpp-crossbyte-libuv --haxe /path/to/haxe-4.3.7/haxe
python3 -m bench run --cases cpp-socket,cpp-crossbyte,cpp-crossbyte-libuv \
  --profile ci --wrk "$PWD/out/wrk/wrk" --out out/local-cpp
```

On macOS, supply the installed OpenSSL prefix (for example
`/opt/homebrew/opt/openssl@3` via `build-wrk --openssl`) and use
`build-wrk --make gmake` if GNU make is needed. A smoke run validates
behavior only. Choose a fresh output directory for each measurement; the harness
refuses to overwrite existing results or bundles. All traffic is loopback, and
cleanup signals only the process groups created by the harness, never `pkill`
or unrelated Java/Node processes.

## Render charts locally

```sh
python3 -m pip install -r requirements-charts.txt
python3 -m bench.charts --report out/local-run/results.json --output out/charts \
  --repository hxwell/hxwell-benchmark --run-id 123 --run-number 1 \
  --source-sha FULL_BENCHMARK_COMMIT_SHA --profile ci --cases all --preview
```

Use the actual run identifiers/source commit and the same profile/case selection
as the report. `--preview` additionally creates PNGs for inspection. The publisher
is restricted to trusted `main` GitHub Actions jobs; local rendering never writes
to GitHub. Install the chart requirements before running the Python test suite.
