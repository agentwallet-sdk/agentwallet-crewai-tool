"""
tools.py
--------
Five CrewAI tools that give agents a non-custodial wallet.

Each tool inherits from crewai.tools.BaseTool and calls AgentWalletToolset.call()
to execute on-chain operations via the agentwallet-sdk TypeScript CLI.

Tools:
    AgentWalletBalanceTool  — check token balances + remaining budget
    AgentWalletTransferTool — send ERC-20 or native tokens
    AgentWalletSwapTool     — swap tokens via SmartSwapRouter (Uniswap V3)
    AgentWalletBridgeTool   — cross-chain USDC transfer via CCTP V2
    AgentWalletX402Tool     — pay x402 HTTP endpoints (micropayments)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .wallet import AgentWalletToolset


# ─── Input schemas ───────────────────────────────────────────────────────────


class BalanceInput(BaseModel):
    token: Optional[str] = Field(
        default=None,
        description=(
            "Token symbol (ETH, USDC, USDT) or ERC-20 contract address. "
            "Omit for native token balance."
        ),
    )


class TransferInput(BaseModel):
    to: str = Field(description="Recipient address (0x-prefixed hex).")
    amount: str = Field(
        description="Amount to send as a decimal string, e.g. '1.5' for 1.5 USDC."
    )
    token: Optional[str] = Field(
        default=None,
        description="Token symbol or address. Omit to send native ETH/SOL.",
    )


class SwapInput(BaseModel):
    token_in: str = Field(description="Token to sell — symbol or address.")
    token_out: str = Field(description="Token to buy — symbol or address.")
    amount_in: str = Field(
        description="Amount to sell as a decimal string, e.g. '100' for 100 USDC."
    )
    slippage_bps: Optional[int] = Field(
        default=50,
        description="Max slippage in basis points (50 = 0.5%). Default 50.",
    )


class BridgeInput(BaseModel):
    destination_chain: str = Field(
        description=(
            "Target chain name: 'ethereum', 'arbitrum', 'optimism', 'polygon', "
            "'base', 'solana', or any of the 17 CCTP V2 supported chains."
        )
    )
    amount_usdc: str = Field(
        description="USDC amount to bridge as a decimal string, e.g. '50'."
    )
    recipient: Optional[str] = Field(
        default=None,
        description="Recipient address on the destination chain. Defaults to agent's own address.",
    )


class X402Input(BaseModel):
    url: str = Field(
        description="The HTTP endpoint that requires an x402 payment (returns 402 status)."
    )
    max_amount_usdc: str = Field(
        description="Max USDC to spend on this request, e.g. '0.01'."
    )
    method: Optional[str] = Field(
        default="GET",
        description="HTTP method — GET, POST, etc.",
    )
    body: Optional[str] = Field(
        default=None,
        description="Request body as a JSON string (for POST/PUT).",
    )


# ─── Tool classes ─────────────────────────────────────────────────────────────


class AgentWalletBalanceTool(BaseTool):
    name: str = "agent_wallet_balance"
    description: str = (
        "Check token balances and remaining autonomous spend budget for the agent's "
        "non-custodial wallet. Returns current balance plus per-transaction and "
        "period limits set by the wallet owner."
    )
    args_schema: Type[BaseModel] = BalanceInput

    _toolset: Any  # AgentWalletToolset, typed as Any to avoid circular import

    def __init__(self, toolset: "AgentWalletToolset") -> None:
        super().__init__()
        self._toolset = toolset

    def _run(self, token: Optional[str] = None) -> str:
        try:
            result = self._toolset.call("balance", {"token": token})
            return json.dumps(result, indent=2)
        except Exception as exc:
            return f"Error checking balance: {exc}"


class AgentWalletTransferTool(BaseTool):
    name: str = "agent_wallet_transfer"
    description: str = (
        "Send ERC-20 tokens or native ETH/SOL from the agent's non-custodial wallet. "
        "Enforces spend limits — transactions over the per-tx or period cap are queued "
        "for owner approval instead of reverting."
    )
    args_schema: Type[BaseModel] = TransferInput

    _toolset: Any

    def __init__(self, toolset: "AgentWalletToolset") -> None:
        super().__init__()
        self._toolset = toolset

    def _run(self, to: str, amount: str, token: Optional[str] = None) -> str:
        try:
            result = self._toolset.call("transfer", {"to": to, "amount": amount, "token": token})
            if result.get("queued"):
                return (
                    f"Transaction queued for owner approval (over spend limit). "
                    f"Pending TX ID: {result.get('txId')}. "
                    f"This is expected — the wallet owner will approve it."
                )
            return f"Transfer sent. TX hash: {result.get('txHash')}"
        except Exception as exc:
            return f"Error sending transfer: {exc}"


class AgentWalletSwapTool(BaseTool):
    name: str = "agent_wallet_swap"
    description: str = (
        "Swap tokens on-chain via SmartSwapRouter (Uniswap V3 on Base/EVM chains). "
        "Routes across multiple pools to get the best price. "
        "Slippage defaults to 0.5% (50 bps)."
    )
    args_schema: Type[BaseModel] = SwapInput

    _toolset: Any

    def __init__(self, toolset: "AgentWalletToolset") -> None:
        super().__init__()
        self._toolset = toolset

    def _run(
        self,
        token_in: str,
        token_out: str,
        amount_in: str,
        slippage_bps: int = 50,
    ) -> str:
        try:
            result = self._toolset.call(
                "swap",
                {
                    "tokenIn": token_in,
                    "tokenOut": token_out,
                    "amountIn": amount_in,
                    "slippageBps": slippage_bps,
                },
            )
            return (
                f"Swap complete. Got {result.get('amountOut')} {token_out}. "
                f"TX: {result.get('txHash')}"
            )
        except Exception as exc:
            return f"Error executing swap: {exc}"


class AgentWalletBridgeTool(BaseTool):
    name: str = "agent_wallet_bridge"
    description: str = (
        "Transfer USDC cross-chain via Circle's CCTP V2 protocol. "
        "Supports 17 chains including Base, Ethereum, Arbitrum, Optimism, Polygon, and Solana. "
        "Funds arrive on the destination chain in 2–20 minutes depending on finality."
    )
    args_schema: Type[BaseModel] = BridgeInput

    _toolset: Any

    def __init__(self, toolset: "AgentWalletToolset") -> None:
        super().__init__()
        self._toolset = toolset

    def _run(
        self,
        destination_chain: str,
        amount_usdc: str,
        recipient: Optional[str] = None,
    ) -> str:
        try:
            result = self._toolset.call(
                "bridge",
                {
                    "destinationChain": destination_chain,
                    "amountUsdc": amount_usdc,
                    "recipient": recipient,
                },
            )
            return (
                f"Bridge initiated. Burn TX: {result.get('burnTxHash')}. "
                f"Estimated arrival: {result.get('estimatedSeconds', '?')}s. "
                f"Track attestation: {result.get('attestationUrl')}"
            )
        except Exception as exc:
            return f"Error initiating bridge: {exc}"


class AgentWalletX402Tool(BaseTool):
    name: str = "agent_wallet_x402_pay"
    description: str = (
        "Pay for HTTP API calls that use the x402 payment protocol. "
        "When an API returns HTTP 402 Payment Required, this tool handles the "
        "USDC micropayment and retries the request automatically. "
        "Use this to access paid AI APIs, data feeds, and agent services."
    )
    args_schema: Type[BaseModel] = X402Input

    _toolset: Any

    def __init__(self, toolset: "AgentWalletToolset") -> None:
        super().__init__()
        self._toolset = toolset

    def _run(
        self,
        url: str,
        max_amount_usdc: str,
        method: str = "GET",
        body: Optional[str] = None,
    ) -> str:
        try:
            result = self._toolset.call(
                "x402",
                {
                    "url": url,
                    "maxAmountUsdc": max_amount_usdc,
                    "method": method,
                    "body": body,
                },
            )
            if result.get("paid"):
                return (
                    f"Payment of {result.get('amountPaid')} USDC sent. "
                    f"Response status: {result.get('status')}. "
                    f"Body: {result.get('responseBody', '')[:500]}"
                )
            return f"Request completed without payment. Response: {result.get('responseBody', '')[:500]}"
        except Exception as exc:
            return f"Error making x402 payment: {exc}"
