from expb.clients.client_config import (
    CLIENT_METRICS_PORT,
    CLIENT_P2P_PORT,
    CLIENT_RPC_PORT,
    CLIENT_RPC_WS_PORT,
    CLIENTS_DATA_DIR,
    ClientConfig,
)
from expb.configs.networks import Network


class ArbitrumNethermindConfig(ClientConfig):
    def __init__(self):
        super().__init__(
            name="arbitrum-nethermind",
            default_image="nethermindeth/nethermind:master",
            default_command=[
                f"--datadir={CLIENTS_DATA_DIR}",
                f"--Network.P2PPort={CLIENT_P2P_PORT}",
                f"--Network.DiscoveryPort={CLIENT_P2P_PORT}",
                "--JsonRpc.Enabled=true",
                "--JsonRpc.Host=0.0.0.0",
                f"--JsonRpc.Port={CLIENT_RPC_PORT}",
                "--Init.WebSocketsEnabled=true",
                f"--JsonRpc.WebSocketsPort={CLIENT_RPC_WS_PORT}",
                "--JsonRpc.EnabledModules=Eth,Subscribe,Trace,TxPool,Web3,Personal,Proof,Net,Parity,Health,Rpc,Debug,Admin,NitroExecution",
                "--Metrics.Enabled=true",
                f"--Metrics.ExposePort={CLIENT_METRICS_PORT}",
                "--Metrics.ExposeHost=0.0.0.0",
                # Disable peering
                "--Init.DiscoveryEnabled=false",
                "--Network.MaxActivePeers=0",
                # Disable sync (replay only)
                "--Sync.SnapSync=false",
                "--Sync.FastSync=false",
                # Disable auth (Arbitrum uses standard RPC, not Engine API)
                "--JsonRpc.UnsecureDevNoRpcAuthentication=true",
                # Disable snapshots
                "--Snapshot.Enabled=false",
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
        command = [
            f"--Metrics.NodeName={instance}",
        ]
        if network == Network.ARBITRUM:
            command.extend(
                [
                    "--config=arbitrum-mainnet-archive",
                ]
            )
        return self.default_command + command + extra_flags
