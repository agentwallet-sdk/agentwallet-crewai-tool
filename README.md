# agentwallet-crewai-tool

Non-custodial wallet tools for [CrewAI](https://github.com/crewAIInc/crewAI) agents. Give your crew members real on-chain wallets with spend limits — so no single agent can drain the treasury without owner sign-off.

Built on [agentwallet-sdk](https://www.npmjs.com/package/agentwallet-sdk).

## What you get

Five CrewAI tools, one toolset class:

| Tool | What it does |
|------|-------------|
| `agent_wallet_balance` | Check token balances + remaining autonomous spend budget |
| `agent_wallet_transfer` | Send ERC-20 or native tokens (auto-queues if over spend limit) |
| `agent_wallet_swap` | Swap tokens via SmartSwapRouter (Uniswap V3 on Base) |
| `agent_wallet_bridge` | Move USDC cross-chain via CCTP V2 (17 chains) |
| `agent_wallet_x402_pay` | Pay HTTP 402 endpoints via x402 micropayments |

Every transfer respects the spend policy set by the wallet owner. If an agent tries to send more than the per-tx or period cap, the transaction is **queued for owner approval** rather than reverting. Agents can't go rogue.

## Install

```bash
pip install agentwallet-crewai-tool
```

You also need Node.js ≥18 installed (the tools shell out to the TypeScript SDK via a CLI wrapper):

```bash
node --version  # should be v18+
npm install -g agentwallet-sdk
```

## Quick start

```python
from crewai import Agent, Task, Crew
from agentwallet_crewai import AgentWalletToolset

# One toolset per agent identity
wallet_tools = AgentWalletToolset(
    private_key="0x...",          # agent's signing key
    account_address="0x...",      # deployed AgentAccountV2 contract
    chain="base",                 # base | ethereum | arbitrum | optimism | polygon | solana
).get_tools()

payment_agent = Agent(
    role="Payment Processor",
    goal="Handle all payment operations for the crew",
    backstory="Specialist in on-chain payments and cross-chain asset management.",
    tools=wallet_tools,
    verbose=True,
)

task = Task(
    description="Check our USDC balance and send 10 USDC to 0xRecipient...",
    expected_output="Confirmation of balance check and transfer hash",
    agent=payment_agent,
)

crew = Crew(agents=[payment_agent], tasks=[task])
result = crew.kickoff()
```

## Architecture

CrewAI is Python. The wallet SDK is TypeScript. This package bridges them:

```
CrewAI Agent
    │
    └─ Python tool (_run method)
            │
            └─ subprocess → wallet_cli.js (Node.js)
                    │
                    └─ agentwallet-sdk
                            │
                            └─ EVM/Solana RPC
```

The CLI wrapper takes a JSON payload on stdin, runs the SDK operation, and returns JSON on stdout. Clean separation — the SDK stays as the single source of truth for signing and chain interactions.

## Spend limits

The wallet contract enforces spend limits at the smart contract level:

```python
# Set limits via the SDK directly (TypeScript) or via the contract owner
# Per-tx max: 50 USDC
# Period max: 500 USDC/day
# After that, transactions are queued — not rejected
```

The `agent_wallet_transfer` tool tells the agent when a transfer was queued vs executed, so it can inform the user and wait for owner approval.

## Chains

EVM: Base, Ethereum, Arbitrum, Optimism, Polygon, Base Sepolia  
Solana: mainnet (bridge only — for full Solana wallet, use `SolanaWallet` from the SDK directly)

## Configuration

| Param | Type | Description |
|-------|------|-------------|
| `private_key` | `str` | Agent's 0x-prefixed hex private key |
| `account_address` | `str` | Deployed `AgentAccountV2` contract address |
| `chain` | `str` | Chain name (default: `"base"`) |
| `rpc_url` | `str` | Custom RPC URL (optional — uses public RPCs if omitted) |
| `node_binary` | `str` | Path to `node` binary (auto-detected) |

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests mock the CLI subprocess — no Node.js or live RPC needed to run them.

## Related packages

- [agentwallet-sdk](https://www.npmjs.com/package/agentwallet-sdk) — core TypeScript SDK
- [agentwallet-langchain](https://www.npmjs.com/package/agentwallet-langchain) — LangChain StructuredTool toolkit
- [elizaos-plugin-agentwallet](https://www.npmjs.com/package/elizaos-plugin-agentwallet) — ElizaOS plugin

## License

MIT
