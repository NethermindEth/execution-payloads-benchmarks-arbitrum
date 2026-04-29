# Arbitrum Nitro Benchmarking — Quickstart

This guide walks through the full workflow for benchmarking Arbitrum execution clients (`arbitrum-nethermind` or `arbitrum-nitro`): recording RPC traffic, converting payloads, and running a benchmark scenario.

## Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Docker](https://docs.docker.com/engine/install/)
- Access to an Arbitrum Nitro node running Nethermind (for recording RPC traffic)
- A synced Arbitrum Nethermind datadir (used as the snapshot source)

Note: ask nethermind arbitrum team for an access to `nethermind.jfrog.io`

## Step 1: Record RPC Traffic

Recordings are captured by Nethermind itself (the execution engine inside Nitro), not by the Nitro node directly. Enable recording by adding these flags to Nethermind:

```
--JsonRpc.RpcRecorderState=Request
--JsonRpc.RpcRecorderBaseFilePath=/app/nethermind_db/logs/rpc/rpc.{counter}.txt
```

This produces files named `rpc.0.txt`, `rpc.1.txt`, `rpc.2.txt`, etc. under the configured path. Each file corresponds to a single RPC session and contains one JSON-RPC request per line.

> **Note:** `{counter}` is a sequential counter — it is **not** the actual block number. The mapping between file index and block number depends on when each session was opened.

For the step you will need both EL and CL. Here is a `docker-compose.yml`

```yaml
services:
  nethermind-l2:
    image: nethermind.jfrog.io/core-oci-local-dev/nethermind-arbitrum:latest
    container_name: nethermind-l2
    user: "1000:1000"
    restart: 'no'
    ports:
      - 20545:20545
      - 20551:20551
      - 30303:30303/tcp
      - 30303:30303/udp
      - 8008:8008
    volumes:
      - /mnt/nvme3/snapshots_unpacked/neth:/app/nethermind_db
    command:
      - -c=arbitrum-mainnet
      - --data-dir=/app/nethermind_db
      - --JsonRpc.Host=0.0.0.0
      - --JsonRpc.EngineHost=0.0.0.0
      - --Arbitrum.BlockProcessingTimeout=60000
      - --Init.DiscoveryEnabled=false
      - --Network.MaxActivePeers=0
      - --Sync.SnapSync=false
      - --Sync.FastSync=false
      - --Pruning.Mode=Hybrid
      - --Pruning.MaxUnpersistedBlockCount=5000
      - --Pruning.MinUnpersistedBlockCount=500
      - --Pruning.MaxBufferedCommitCount=5000
      - --Snapshot.Enabled=false
      - --VerifyBlockHash.ArbNodeRpcUrl=https://arb1.arbitrum.io/rpc
      - --Seq.MinLevel=Info
      - --Sync.PivotNumber=0
      - --JsonRpc.UnsecureDevNoRpcAuthentication=true
      - --JsonRpc.RpcRecorderState=Request
      - --JsonRpc.RpcRecorderBaseFilePath=/app/nethermind_db/logs/rpc/rpc.{counter}.txt
    networks:
      - nethermind-network
    healthcheck:
      test:
        - CMD-SHELL
        - timeout 5 bash -c '</dev/tcp/localhost/20545' || exit 1
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
  nitro:
    image: nethermind.jfrog.io/core-oci-local-dev/arbitrum-nitro:nethermind
    container_name: nitro
    user: "1000:1000"
    depends_on:
      nethermind-l2:
        condition: service_healthy
    restart: 'no'
    ports: []
    volumes:
      - /mnt/nvme3/snapshots_unpacked/nitro:/tmp/nitro-data
      - /mnt/nvme3/snapshots_unpacked/neth:/nethermind-data:ro
    command:
      - --persistent.global-config=/tmp/nitro-data
      - --chain.id=${CHAIN_ID:-42161}
      - --execution.forwarding-target=null
      - --log-level=${LOG_LEVEL:-INFO}
      - --node.execution-rpc-client.url=http://nethermind-l2:20551
      - --node.sequencer=false
      # - --parent-chain.connection.url=# http://YOUR_CONENCTION_IP:8545
      # - --parent-chain.blob-client.beacon-url=https://lb.drpc.live/eth-beacon-chain/....
    networks:
      - nethermind-network
networks:
  nethermind-network:
    name: nethermind-network
```

## Step 2: Convert Recordings to Benchmark Format

Use the `convert-arbitrum-payloads` command to extract `nitroexecution_digestMessage` calls from the recorded files and produce a `payloads.jsonl` suitable for benchmarking:

```bash
expb convert-arbitrum-payloads \
  --input-dir ~/rpc \
  --output-dir ./arbitrum-payloads \
  --start-block 0 \
  --end-block 9999
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

## Step 4.1: Fix snapshot synchonization issues

To be able to compare two client we need to have snapshots for both clients which start on the same block.
But sometimes there may be a difference and to fix it we need to reset the blockchain head.

To do this for nethermind, start the client without CL
Imagine the last block is `0x12abf243` and we need to reset it to `0x12abf242`

1.Get the chain head number

``` bash
curl http://0.0.0.0:20545   -X POST   -H "Content-Type: application/json"   --data '{"jsonrpc": "2.0","id": 0,"method": "eth_blockNumber", "params": []}'
{"jsonrpc":"2.0","result":"0x12abf243","id":0}
```

2.Get block hash by number

``` bash
curl http://0.0.0.0:20545 \
  -X POST \
  -H "Content-Type: application/json" \
  --data '{
      "jsonrpc": "2.0",
      "id": 0,
      "method": "eth_getBlockByNumber",
      "params": ["0x12abf242", false]
    }'
```

3.Reset head (do twice due to a bug)

```bash
curl http://0.0.0.0:20545   -X POST   -H "Content-Type: application/json"   --data '{
      "jsonrpc": "2.0",
      "id": 0,
      "method": "debug_resetHead",
      "params": ["0x9756d5e12f388dbe7e9fe7fad5bd84b07adb067e5edc51d6d6c38569ce85aae0"]
    }'
```

4.Perform `debug_deleteChainSlice` to remove the old blocks from the database

```bash
curl http://0.0.0.0:20545 \
  -X POST \
  -H "Content-Type: application/json" \
  --data '{
      "jsonrpc": "2.0",
      "id": 0,
      "method": "debug_deleteChainSlice",
      "params": ["0x12abf242", true]
    }'
```

5.Restart nethermind client, check logs and confirm the chain head has been changed

``` bash
curl http://0.0.0.0:20545   -X POST   -H "Content-Type: application/json"   --data '{"jsonrpc": "2.0","id": 0,"method": "eth_blockNumber", "params": []}'
{"jsonrpc":"2.0","result":"0x12abf242","id":0}
```

6.Re-execute Step 1: Record RPC Traffic and Step 2: Convert Recordings to Benchmark Format. Save the output to a different location

Now you can use different payloads for the clients

## Step 4.2: Migrate Nethermind snapshot to FlatDB

1.[Optional] Copy the original snapshot to a separate location

```bash
cp -r /mnt/nvme3/snapshots_unpacked/neth/ /mnt/nvme2/snapshots_backup
```

2.Create a separate docker compose file without el. Add following to nethermind startup command:

```
  - --FlatDb.Enabled=true
  - --FlatDb.ImportFromPruningTrieState=true
```
And update snapshot volume

3.Start the new docker compose

Example of the docker compose:

```yaml
services:
  nethermind-l2:
    image: nethermind.jfrog.io/core-oci-local-dev/nethermind-arbitrum:latest
    container_name: nethermind-l2
    user: "1000:1000"
    restart: 'no'
    ports:
      - 20545:20545
      - 20551:20551
      - 30303:30303/tcp
      - 30303:30303/udp
      - 8008:8008
    volumes:
      - /mnt/nvme2/snapshots_backup/neth:/app/nethermind_db
    command:
      - -c=arbitrum-mainnet
      - --data-dir=/app/nethermind_db
      - --JsonRpc.Host=0.0.0.0
      - --JsonRpc.EngineHost=0.0.0.0
      - --Arbitrum.BlockProcessingTimeout=60000
      - --Init.DiscoveryEnabled=false
      - --Network.MaxActivePeers=0
      - --Sync.SnapSync=false
      - --Sync.FastSync=false
      - --Pruning.Mode=Hybrid
      - --Pruning.MaxUnpersistedBlockCount=5000
      - --Pruning.MinUnpersistedBlockCount=500
      - --Pruning.MaxBufferedCommitCount=5000
      - --Snapshot.Enabled=false
      - --VerifyBlockHash.ArbNodeRpcUrl=https://arb1.arbitrum.io/rpc
      - --Seq.MinLevel=Info
      - --Sync.PivotNumber=0
      - --JsonRpc.UnsecureDevNoRpcAuthentication=true
      - --FlatDb.Enabled=true
      - --FlatDb.ImportFromPruningTrieState=true
    networks:
      - nethermind-network
    healthcheck:
      test:
        - CMD-SHELL
        - timeout 5 bash -c '</dev/tcp/localhost/20545' || exit 1
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
networks:
  nethermind-network:
    name: nethermind-network

```

## Step 5: Run the Benchmark

Run a single scenario with per-payload metrics printed to the console:

```bash
sudo bash -c "$(which uv) run expb execute-scenario --scenario-name arbitrum-flatdb-test --config-file arbitrum-test.yaml --print-logs --per-payload-metrics-logs"
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
