"""
Tests for agentwallet-crewai-tool.

Uses mocked AgentWalletToolset.call() so no Node.js or on-chain access required.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from agentwallet_crewai import (
    AgentWalletToolset,
    AgentWalletBalanceTool,
    AgentWalletTransferTool,
    AgentWalletSwapTool,
    AgentWalletBridgeTool,
    AgentWalletX402Tool,
)


@pytest.fixture
def mock_toolset():
    ts = AgentWalletToolset(
        private_key="0xdeadbeef" + "0" * 56,
        account_address="0x" + "a" * 40,
        chain="base",
    )
    ts.call = MagicMock()
    return ts


class TestAgentWalletBalanceTool:
    def test_returns_balance_json(self, mock_toolset):
        mock_toolset.call.return_value = {
            "token": "native",
            "perTxLimit": "1000000000000000000",
            "remainingInPeriod": "5000000000000000000",
        }
        tool = AgentWalletBalanceTool(mock_toolset)
        result = tool._run()
        assert "perTxLimit" in result
        assert "remainingInPeriod" in result
        mock_toolset.call.assert_called_once_with("balance", {"token": None})

    def test_balance_with_token_symbol(self, mock_toolset):
        mock_toolset.call.return_value = {"token": "USDC", "perTxLimit": "100000000"}
        tool = AgentWalletBalanceTool(mock_toolset)
        result = tool._run(token="USDC")
        mock_toolset.call.assert_called_with("balance", {"token": "USDC"})

    def test_balance_error_handling(self, mock_toolset):
        mock_toolset.call.side_effect = RuntimeError("RPC unavailable")
        tool = AgentWalletBalanceTool(mock_toolset)
        result = tool._run()
        assert "Error checking balance" in result
        assert "RPC unavailable" in result


class TestAgentWalletTransferTool:
    def test_successful_transfer(self, mock_toolset):
        mock_toolset.call.return_value = {
            "success": True,
            "txHash": "0xabc123",
            "queued": False,
        }
        tool = AgentWalletTransferTool(mock_toolset)
        result = tool._run(to="0x" + "b" * 40, amount="1.0")
        assert "0xabc123" in result
        assert "queued" not in result.lower() or "TX hash" in result

    def test_queued_transfer_message(self, mock_toolset):
        mock_toolset.call.return_value = {
            "success": True,
            "queued": True,
            "txId": "42",
        }
        tool = AgentWalletTransferTool(mock_toolset)
        result = tool._run(to="0x" + "b" * 40, amount="999.0")
        assert "queued" in result.lower()
        assert "42" in result

    def test_transfer_with_token(self, mock_toolset):
        mock_toolset.call.return_value = {"txHash": "0xdef456", "queued": False}
        tool = AgentWalletTransferTool(mock_toolset)
        result = tool._run(to="0x" + "b" * 40, amount="50.0", token="USDC")
        mock_toolset.call.assert_called_once_with(
            "transfer",
            {"to": "0x" + "b" * 40, "amount": "50.0", "token": "USDC"},
        )

    def test_transfer_error_handling(self, mock_toolset):
        mock_toolset.call.side_effect = RuntimeError("Insufficient balance")
        tool = AgentWalletTransferTool(mock_toolset)
        result = tool._run(to="0x" + "b" * 40, amount="1.0")
        assert "Error sending transfer" in result


class TestAgentWalletSwapTool:
    def test_successful_swap(self, mock_toolset):
        mock_toolset.call.return_value = {
            "success": True,
            "txHash": "0xswap123",
            "amountOut": "99.5",
        }
        tool = AgentWalletSwapTool(mock_toolset)
        result = tool._run(token_in="ETH", token_out="USDC", amount_in="0.05")
        assert "99.5" in result
        assert "0xswap123" in result

    def test_swap_default_slippage(self, mock_toolset):
        mock_toolset.call.return_value = {"txHash": "0x1", "amountOut": "100"}
        tool = AgentWalletSwapTool(mock_toolset)
        tool._run(token_in="USDC", token_out="ETH", amount_in="100")
        call_params = mock_toolset.call.call_args[0][1]
        assert call_params["slippageBps"] == 50

    def test_swap_error_handling(self, mock_toolset):
        mock_toolset.call.side_effect = RuntimeError("No route found")
        tool = AgentWalletSwapTool(mock_toolset)
        result = tool._run(token_in="X", token_out="Y", amount_in="1")
        assert "Error executing swap" in result


class TestAgentWalletBridgeTool:
    def test_successful_bridge(self, mock_toolset):
        mock_toolset.call.return_value = {
            "success": True,
            "burnTxHash": "0xburn123",
            "estimatedSeconds": 300,
            "attestationUrl": "https://iris-api.circle.com/v2/attestations/0xburn123",
        }
        tool = AgentWalletBridgeTool(mock_toolset)
        result = tool._run(destination_chain="arbitrum", amount_usdc="100")
        assert "0xburn123" in result
        assert "300" in result

    def test_bridge_error_handling(self, mock_toolset):
        mock_toolset.call.side_effect = RuntimeError("CCTP unavailable")
        tool = AgentWalletBridgeTool(mock_toolset)
        result = tool._run(destination_chain="optimism", amount_usdc="10")
        assert "Error initiating bridge" in result


class TestAgentWalletX402Tool:
    def test_paid_request(self, mock_toolset):
        mock_toolset.call.return_value = {
            "success": True,
            "paid": True,
            "amountPaid": "10000",  # microdollars
            "status": 200,
            "responseBody": '{"data": "premium content"}',
        }
        tool = AgentWalletX402Tool(mock_toolset)
        result = tool._run(url="https://api.example.com/data", max_amount_usdc="0.01")
        assert "10000" in result
        assert "premium content" in result

    def test_free_request(self, mock_toolset):
        mock_toolset.call.return_value = {
            "success": True,
            "paid": False,
            "status": 200,
            "responseBody": '{"free": true}',
        }
        tool = AgentWalletX402Tool(mock_toolset)
        result = tool._run(url="https://api.example.com/free", max_amount_usdc="0.01")
        assert "without payment" in result

    def test_x402_error_handling(self, mock_toolset):
        mock_toolset.call.side_effect = RuntimeError("Budget exceeded")
        tool = AgentWalletX402Tool(mock_toolset)
        result = tool._run(url="https://expensive.example.com", max_amount_usdc="0.001")
        assert "Error making x402 payment" in result


class TestAgentWalletToolset:
    def test_get_tools_returns_five(self, mock_toolset):
        tools = mock_toolset.get_tools()
        assert len(tools) == 5

    def test_tool_names(self, mock_toolset):
        names = {t.name for t in mock_toolset.get_tools()}
        assert names == {
            "agent_wallet_balance",
            "agent_wallet_transfer",
            "agent_wallet_swap",
            "agent_wallet_bridge",
            "agent_wallet_x402_pay",
        }

    def test_all_tools_are_base_tool_instances(self, mock_toolset):
        from crewai.tools import BaseTool
        for tool in mock_toolset.get_tools():
            assert isinstance(tool, BaseTool)
