# Execution Payloads Benchmarks

## Requirements

* [uv](https://docs.astral.sh/uv/getting-started/installation/)
* [Docker](https://docs.docker.com/engine/install/)

## Installation

From Github:

```bash
uv tool install --from git+https://github.com/NethermindEth/execution-payloads-benchmarks expb
```

## Usage

1. Create a copy of the [example configuration file](example-expb.yaml).
2. Edit the configuration file.
3. Execute one or multiple scenarios.

### Scenarios Execution

#### Single Scenario

```bash
expb execute-scenario --scenario-name example --config-file expb.yaml
```

#### Multiple Scenarios

```bash
expb execute-scenarios --config-file expb.yaml --loop
```

#### Single Scenario with duration metrics per payload

```bash
expb execute-scenario --scenario-name example --config-file expb.yaml --per-payload-metrics
```

#### Single Scenario with per-payload metric table logs

```bash
expb execute-scenario --scenario-name example --config-file expb.yaml --print-logs --per-payload-metrics-logs
```

### Arbitrum Nitro Benchmarking

#### 1. Convert Arbitrum RPC recordings

Convert recorded Arbitrum Nitro RPC traffic files (`rpc.<N>.txt`) into the benchmark JSONL format:

```bash
expb convert-arbitrum-payloads \
  --input-dir ~/rpc \
  --output-dir ./arbitrum-payloads \
  --start-block 0 \
  --end-block 99
```

This produces `./arbitrum-payloads/payloads.jsonl` with one `digestMessage` call per line. By default only `nitroexecution_digestMessage` calls are extracted; use `--methods` to include additional methods.

#### 2. Configure an Arbitrum scenario

```yaml
scenarios:
  arbitrum-bench:
    client: arbitrum-nethermind
    network: arbitrum
    payloads: ./arbitrum-payloads/payloads.jsonl
    # fcus: omitted (not used for Arbitrum)
    disable_auth: true
    snapshot_source: ./snapshots/arbitrum-nethermind
    amount: 1000
    duration: 30m
    startup_wait: 60
```

Key differences from Ethereum scenarios:
- `network: arbitrum` — enables Arbitrum mode
- `fcus` field is omitted (Arbitrum does not use forkchoice updates)
- `disable_auth: true` — skips JWT authentication (optional, Arbitrum supports JWT but typically runs without it)
- `client: arbitrum-nethermind` — uses Arbitrum-specific Nethermind configuration

#### 3. Run the benchmark

```bash
expb execute-scenario --scenario-name arbitrum-bench --config-file expb.yaml --per-payload-metrics
```

For other use cases or more details see [CLI usage docs](docs/USAGE.md).

## Outputs

After the execution of an scenario the outputs will be stored inside the specified `paths.outputs` [configuration](example-expb.yaml) option. The outputs directory structure will looks like this:

* Scenario output directory: `<outputs-directory>/expb-executor-<scenario-name>-<timestamp>`.
  * Grafana K6 script generated for the test: `k6-script.js`.
  * Grafana K6 script configuration generated for the test: `k6-config.json`.
  * Grafana K6 results summary: `k6-summary.json`.
  * Grafana K6 process logs: `k6.log`.
  * Grafana Alloy generated configuration: `config.alloy`.
  * Execution client logs: `<client_type>.log`.
  * Execution client additional docker volumes directory for any additional volume thats requires it: `volumes`.
    * If no source directory/file is specified then a `<volume-name>` directory will be created.
  * Execution client additional commands outputs directory if required: `commands`
    * Additional commands outputs: `cmd-<index>.log`

### Streamed Outputs

In addition to the previous outputs, metrics about clients and its performance are streamed based in the configured outputs. These includes:

* Grafana K6 results metrics: These are either stored in a `k6-results.jsonl` file with resultant metrics in the [Grafana K6 format](https://grafana.com/docs/k6/latest/results-output/real-time/json/) or sent to the configured Prometheus Remote Write API.
* Execution client metrics. If a Prometheus service is configured these metrics are sent to the Remote Write API.
* Execution client profiling data: If a Grafana Pyroscope service is configured the profiling data is sent to the configured Pyroscope instance. (WIP)
