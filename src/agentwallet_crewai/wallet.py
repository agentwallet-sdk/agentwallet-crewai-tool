"""
wallet.py
---------
Thin bridge between Python CrewAI tools and the agentwallet-sdk TypeScript CLI.

The SDK is TypeScript-native, so this module shells out to a small Node.js CLI
wrapper (cli/wallet_cli.js) that does the actual on-chain work. Python stays in
charge of CrewAI orchestration; Node handles signing and RPC calls.

If you'd rather call your own REST endpoint wrapping the SDK, swap the
_call_cli helper for an httpx request — the interface is identical.
"""

from __future__ import annotations

import json
import os
import subprocess
import shutil
from pathlib import Path
from typing import Any

# Path to the bundled CLI entrypoint (ships with this package)
_CLI_PATH = Path(__file__).parent.parent.parent / "cli" / "wallet_cli.js"


class AgentWalletToolset:
    """
    Bundles all wallet tools for a single agent identity.

    Args:
        private_key:      Agent's signing key (hex, '0x'-prefixed).
        account_address:  Deployed AgentAccountV2 contract address.
        chain:            Chain name — 'base', 'ethereum', 'arbitrum', 'optimism',
                          'polygon', 'base-sepolia', or 'solana'.
        rpc_url:          Custom RPC endpoint. Falls back to public RPCs if omitted.
        node_binary:      Path to the 'node' binary. Auto-detected if omitted.
    """

    def __init__(
        self,
        private_key: str,
        account_address: str,
        chain: str = "base",
        rpc_url: str | None = None,
        node_binary: str | None = None,
    ) -> None:
        self.config = {
            "privateKey": private_key,
            "accountAddress": account_address,
            "chain": chain,
            "rpcUrl": rpc_url,
        }
        self._node = node_binary or shutil.which("node") or "node"

    def get_tools(self) -> list:
        """Return all five wallet tools pre-configured for this agent."""
        from .tools import (
            AgentWalletBalanceTool,
            AgentWalletTransferTool,
            AgentWalletSwapTool,
            AgentWalletBridgeTool,
            AgentWalletX402Tool,
        )
        return [
            AgentWalletBalanceTool(self),
            AgentWalletTransferTool(self),
            AgentWalletSwapTool(self),
            AgentWalletBridgeTool(self),
            AgentWalletX402Tool(self),
        ]

    def call(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Call the Node.js CLI wrapper synchronously.

        Sends a JSON payload to stdin, reads a JSON result from stdout.
        Raises RuntimeError on non-zero exit or JSON parse failure.

        Args:
            command: One of 'balance', 'transfer', 'swap', 'bridge', 'x402'.
            params:  Command-specific parameters (merged with wallet config).

        Returns:
            Parsed JSON dict from the CLI.
        """
        if not _CLI_PATH.exists():
            raise FileNotFoundError(
                f"CLI not found at {_CLI_PATH}. "
                "Run 'npm install' in the package root to build it."
            )

        payload = json.dumps({"command": command, "config": self.config, **params})

        try:
            result = subprocess.run(
                [self._node, str(_CLI_PATH)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Wallet CLI timed out after 60 seconds") from exc

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Wallet CLI failed (exit {result.returncode}): {err}")

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Wallet CLI returned invalid JSON: {result.stdout[:500]}"
            ) from exc
