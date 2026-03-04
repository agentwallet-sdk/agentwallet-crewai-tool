"""
agentwallet-crewai-tool
~~~~~~~~~~~~~~~~~~~~~~~
Non-custodial wallet tools for CrewAI agents.

Quick start:
    from agentwallet_crewai import AgentWalletToolset

    tools = AgentWalletToolset(
        private_key="0x...",
        account_address="0x...",
        chain="base",
    ).get_tools()

    agent = Agent(role="...", tools=tools, ...)
"""

from .tools import (
    AgentWalletBalanceTool,
    AgentWalletTransferTool,
    AgentWalletSwapTool,
    AgentWalletBridgeTool,
    AgentWalletX402Tool,
)
from .wallet import AgentWalletToolset

__all__ = [
    "AgentWalletToolset",
    "AgentWalletBalanceTool",
    "AgentWalletTransferTool",
    "AgentWalletSwapTool",
    "AgentWalletBridgeTool",
    "AgentWalletX402Tool",
]

__version__ = "1.0.0"
