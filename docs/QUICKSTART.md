# Arbitrum Nitro Benchmarking — Quickstart

This guide walks through the full workflow for benchmarking Arbitrum execution clients (`arbitrum-nethermind` or `arbitrum-nitro`): recording RPC traffic, converting payloads, and running a benchmark scenario.

## Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Docker](https://docs.docker.com/engine/install/)
- Access to an Arbitrum Nitro node running Nethermind (for recording RPC traffic)
- A synced Arbitrum Nethermind datadir (used as the snapshot source)

## Step 1: Record RPC Traffic

Recordings are captured by Nethermind itself (the execution engine inside Nitro), not by the Nitro node directly. Enable recording by adding these flags to Nethermind:

```
--JsonRpc.RpcRecorderState=Request
--JsonRpc.RpcRecorderBaseFilePath=/app/nethermind_db/logs/rpc/rpc.{counter}.txt
```

This produces files named `rpc.0.txt`, `rpc.1.txt`, `rpc.2.txt`, etc. under the configured path. Each file corresponds to a single RPC session and contains one JSON-RPC request per line.

> **Note:** `{counter}` is a sequential counter — it is **not** the actual block number. The mapping between file index and block number depends on when each session was opened.

## Step 2: Convert Recordings to Benchmark Format

Use the `convert-arbitrum-payloads` command to extract `nitroexecution_digestMessage` calls from the recorded files and produce a `payloads.jsonl` suitable for benchmarking:

```bash
expb convert-arbitrum-payloads \
  --input-dir ~/rpc \
  --output-dir ./arbitrum-payloads \
  --start-block 0 \
  --end-block 99
```

- `--input-dir` — directory containing the `rpc.<N>.txt` files
- `--output-dir` — where `payloads.jsonl` will be written
- `--start-block` / `--end-block` — **file index** range (inclusive), not block numbers

The output file `./arbitrum-payloads/payloads.jsonl` will contain one JSON-RPC request body per line. Each `digestMessage` line also includes a computed `msgDataSize` field (base64-decoded L2 message data size in bytes).

To include additional RPC methods beyond `digestMessage`, use the `--methods` flag:

```bash
expb convert-arbitrum-payloads \
  --input-dir ~/rpc \
  --output-dir ./arbitrum-payloads \
  --methods "digestMessage,headMessageIndex,setConsensusSyncData,resultAtMessageIndex"
```

> The command refuses to overwrite an existing `payloads.jsonl`. Delete or move the old file first if you need to re-run.

## Step 3: Prepare a Snapshot

The `snapshot_source` in the config file points to a synced Arbitrum data directory. The benchmarking tool creates a temporary overlay copy of this directory so the original data is never modified.

Requirements:
- The snapshot must contain chain state **at or before** the first payload's block, otherwise the execution client will reject the payloads.
- The default snapshot backend is `overlay` (uses overlayfs). Alternatives are `zfs` and `copy` — see [USAGE.md](USAGE.md) for details.

The directory structure depends on which client you use:

**`arbitrum-nethermind`** — standard Nethermind `--datadir`:

```
./snapshots/arbitrum-nethermind/
├── nethermind_db/
├── keystore/
└── ...
```

**`arbitrum-nitro`** — Nitro `--persistent.global-config` directory:

```
./snapshots/arbitrum-nitro/
├── nitro/
├── l2chaindata/
└── ...
```

## Step 4: Create a Config File

Create an `expb.yaml` with a minimal Arbitrum scenario. Only the fields shown below are required.

**Using `arbitrum-nethermind`** (Nethermind execution engine):

```yaml
paths:
  work: ./work
  outputs: ./outputs

scenarios:
  arbitrum-bench:
    client: arbitrum-nethermind
    network: arbitrum
    payloads: ./arbitrum-payloads/payloads.jsonl
    snapshot_source: ./snapshots/arbitrum-nethermind
    amount: 1000
    duration: 30m
    startup_wait: 60
```

**Using `arbitrum-nitro`** (official Nitro node in execution-only mode):

```yaml
paths:
  work: ./work
  outputs: ./outputs

scenarios:
  arbitrum-bench:
    client: arbitrum-nitro
    network: arbitrum
    payloads: ./arbitrum-payloads/payloads.jsonl
    snapshot_source: ./snapshots/arbitrum-nitro
    amount: 1000
    duration: 30m
    startup_wait: 60
```

Key points:
- **`client:`** — two Arbitrum clients are available:
  - `arbitrum-nethermind` — Nethermind execution engine (`--config=arbitrum-mainnet`); snapshot is a Nethermind `--datadir`
  - `arbitrum-nitro` — official Nitro node (`offchainlabs/nitro-node`) in execution-only mode (no L1 listener); snapshot is a Nitro `--persistent.global-config` directory
- **`network: arbitrum`** — enables Arbitrum mode (no FCU file required, Arbitrum method handling)
- **`fcus`** — omitted entirely (Arbitrum does not use forkchoice updates)
- JWT auth is disabled automatically for both clients
- **`amount`** — number of payloads to replay from the JSONL file
- **`duration`** — maximum wall-clock time for the benchmark run
- **`startup_wait`** — seconds to wait for the execution client to become ready

Optional tuning flags can be added via `extra_flags` (flags are client-specific):

```yaml
    # arbitrum-nethermind flags
    extra_flags:
      - --Pruning.Mode=None
      - --JsonRpc.Timeout=600000
```

```yaml
    # arbitrum-nitro flags
    extra_flags:
      - --execution.caching.archive=true
```

For all available scenario options, see the [example config](../example-expb.yaml) and [CLI usage docs](USAGE.md).

## Step 5: Run the Benchmark

Run a single scenario with per-payload metrics printed to the console:

```bash
expb execute-scenario \
  --scenario-name arbitrum-bench \
  --config-file expb.yaml \
  --print-logs \
  --per-payload-metrics-logs
```

What happens under the hood:
1. A temporary overlay snapshot is created from `snapshot_source`
2. The selected Arbitrum Docker container starts with the snapshot mounted (Nethermind for `arbitrum-nethermind`, Nitro node for `arbitrum-nitro`)
3. The tool waits for the JSON-RPC endpoint (port 8545) to become available
4. Grafana K6 sends payloads from `payloads.jsonl` to the execution client
5. After completion (or timeout), containers are stopped and logs are saved

The `--per-payload-metrics-logs` flag prints a summary table after execution showing processing time and message data size for each payload. The `--print-logs` flag streams K6 and execution client logs to the console during the run.

## Step 6: Analyze Results

After the scenario completes, outputs are saved to:

```
<outputs>/expb-executor-arbitrum-bench-<timestamp>/
├── k6-script.js          # Generated K6 test script
├── k6-config.json        # K6 script configuration
├── k6-summary.json       # K6 results summary (timings, status codes)
├── k6.log                # K6 process logs
└── arbitrum-nethermind.log   # or arbitrum-nitro.log — Execution client logs
```

Where `<outputs>` is the `paths.outputs` value from your config (`./outputs` by default). The execution client log file is named after the client type (`arbitrum-nethermind.log` or `arbitrum-nitro.log`).

**Key files to check:**

- **`k6-summary.json`** — contains aggregate metrics: request durations (min/max/avg/p90/p95), success/failure counts, and throughput
- **`arbitrum-nethermind.log`** / **`arbitrum-nitro.log`** — execution client logs for debugging errors or slow blocks
- **`k6.log`** — detailed K6 output including per-request timings

**Per-payload metrics table** (when using `--per-payload-metrics-logs`):

The table printed after execution shows one row per payload with:
- `idx` — payload index
- `processing_ms` — server-side processing time in milliseconds
- `gas_used` / `msgDataSize` — for Arbitrum, this is the base64-decoded L2 message data size in bytes

This is the quickest way to identify slow blocks or outliers without needing an external metrics stack.
