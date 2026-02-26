from expb.clients.client_config import (
    CLIENT_RPC_PORT,
    CLIENT_RPC_WS_PORT,
    CLIENTS_DATA_DIR,
    ClientConfig,
)
from expb.configs.networks import Network


class ArbitrumNitroConfig(ClientConfig):
    def __init__(self):
        super().__init__(
            name="arbitrum-nitro",
            default_image="offchainlabs/nitro-node:v3.10.0-rc.3-26d4dc2",
            default_entrypoint="/usr/local/bin/nitro",
            default_command=[
                # Chain config (mainnet defaults)
                "--chain.id=42161",
                "--parent-chain.id=1",
                # Data directory (matches CLIENTS_DATA_DIR constant)
                f"--persistent.global-config={CLIENTS_DATA_DIR}",
                # Init config
                "--init.empty=true",
                "--init.validate-genesis-assertion=false",
                # Node config (execution-only, no L1)
                "--node.dangerous.no-l1-listener=true",
                "--node.parent-chain-reader.enable=false",
                "--node.sequencer=false",
                "--node.batch-poster.enable=false",
                "--node.staker.enable=false",
                "--node.feed.input.url=",
                # RPC config
                "--execution.rpc-server.enable=true",
                "--execution.rpc-server.public=true",
                "--execution.rpc-server.authenticated=false",
                # WebSocket (using standard port)
                "--ws.addr=0.0.0.0",
                f"--ws.port={CLIENT_RPC_WS_PORT}",
                "--ws.api=net,web3,eth,arb,nitroexecution",
                # HTTP (using standard port)
                "--http.addr=0.0.0.0",
                f"--http.port={CLIENT_RPC_PORT}",
                "--http.vhosts=*",
                "--http.api=net,web3,eth,arb,nitroexecution",
                # Logging
                "--log-level=INFO",
                # Disable auth
                "--auth.addr="
            ],
            prometheus_metrics_path="/metrics",
            default_env={},
        )

    def get_command(
        self,
        instance: str,
        network: Network,
        extra_flags: list[str] = [],
    ) -> list[str]:
        return self.default_command + extra_flags
