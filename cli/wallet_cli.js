#!/usr/bin/env node
/**
 * wallet_cli.js
 * -------------
 * Thin CLI wrapper around agentwallet-sdk for use by Python CrewAI tools.
 *
 * Protocol:
 *   stdin  → JSON: { command, config: { privateKey, accountAddress, chain, rpcUrl }, ...params }
 *   stdout → JSON: { success: true, ...result } or { success: false, error: string }
 *   exit 0 on success, exit 1 on error
 *
 * Commands: balance | transfer | swap | bridge | x402
 */

import { privateKeyToAccount } from "viem/accounts";
import { createWalletClient, http, parseUnits, formatUnits } from "viem";
import { base, baseSepolia, mainnet, arbitrum, optimism, polygon } from "viem/chains";
import {
  createWallet,
  checkBudget,
  agentExecute,
  agentTransferToken,
  SmartSwapRouter,
  createBridge,
  createX402Client,
  NATIVE_TOKEN,
  BASE_TOKENS,
} from "agentwallet-sdk";

const CHAINS = { base, "base-sepolia": baseSepolia, ethereum: mainnet, arbitrum, optimism, polygon };

function respond(data) {
  process.stdout.write(JSON.stringify(data) + "\n");
}

function fail(error) {
  process.stdout.write(JSON.stringify({ success: false, error: String(error) }) + "\n");
  process.exit(1);
}

async function main() {
  let raw = "";
  for await (const chunk of process.stdin) raw += chunk;

  let input;
  try {
    input = JSON.parse(raw);
  } catch (e) {
    fail("Invalid JSON on stdin");
    return;
  }

  const { command, config, ...params } = input;

  if (!config?.privateKey || !config?.accountAddress) {
    fail("config.privateKey and config.accountAddress are required");
    return;
  }

  const chain = CHAINS[config.chain || "base"];
  if (!chain) { fail(`Unsupported chain: ${config.chain}`); return; }

  const account = privateKeyToAccount(config.privateKey);
  const walletClient = createWalletClient({ account, chain, transport: http(config.rpcUrl) });
  const wallet = createWallet({ ...config, walletClient });

  try {
    switch (command) {
      case "balance": {
        const tokenAddr = resolveToken(params.token, chain.id) || NATIVE_TOKEN;
        const budget = await checkBudget(wallet, tokenAddr);
        respond({
          success: true,
          token: params.token || "native",
          perTxLimit: budget.perTxLimit.toString(),
          remainingInPeriod: budget.remainingInPeriod.toString(),
        });
        break;
      }

      case "transfer": {
        const tokenAddr = resolveToken(params.token, chain.id);
        const decimals = params.token ? 6 : 18; // USDC=6, native=18
        const amount = parseUnits(params.amount, decimals);

        if (tokenAddr && tokenAddr !== NATIVE_TOKEN) {
          const hash = await agentTransferToken(wallet, { token: tokenAddr, to: params.to, amount });
          respond({ success: true, txHash: hash, queued: false });
        } else {
          const result = await agentExecute(wallet, { to: params.to, value: amount });
          respond({ success: true, txHash: result.txHash, queued: !result.executed });
        }
        break;
      }

      case "swap": {
        const router = new SmartSwapRouter({ wallet, chain: config.chain });
        const result = await router.swap({
          tokenIn: resolveToken(params.tokenIn, chain.id) || NATIVE_TOKEN,
          tokenOut: resolveToken(params.tokenOut, chain.id) || NATIVE_TOKEN,
          amountIn: parseUnits(params.amountIn, 18),
          slippageBps: params.slippageBps || 50,
        });
        respond({
          success: true,
          txHash: result.txHash,
          amountOut: formatUnits(result.amountOut || 0n, 18),
        });
        break;
      }

      case "bridge": {
        const bridge = await createBridge({
          sourceChain: config.chain,
          walletClient,
          rpcUrl: config.rpcUrl,
        });
        const result = await bridge.bridge({
          destinationChain: params.destinationChain,
          amountUsdc: parseUnits(params.amountUsdc, 6),
          recipient: params.recipient || account.address,
        });
        respond({
          success: true,
          burnTxHash: result.burnTxHash,
          estimatedSeconds: result.estimatedSeconds,
          attestationUrl: result.attestationUrl,
        });
        break;
      }

      case "x402": {
        const client = createX402Client({
          wallet,
          maxBudgetUsdc: params.maxAmountUsdc,
        });
        const response = await client.fetch(params.url, {
          method: params.method || "GET",
          body: params.body || undefined,
        });
        const text = await response.text();
        respond({
          success: true,
          paid: client.lastPayment != null,
          amountPaid: client.lastPayment?.amount?.toString() || "0",
          status: response.status,
          responseBody: text,
        });
        break;
      }

      default:
        fail(`Unknown command: ${command}`);
    }
  } catch (err) {
    fail(err?.message || String(err));
  }
}

function resolveToken(symbolOrAddress, chainId) {
  if (!symbolOrAddress) return null;
  if (symbolOrAddress.startsWith("0x")) return symbolOrAddress;
  // Simple symbol lookup for Base chain tokens
  const SYMBOLS = {
    USDC: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    USDT: "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
    WETH: "0x4200000000000000000000000000000000000006",
  };
  return SYMBOLS[symbolOrAddress.toUpperCase()] || null;
}

main().catch(fail);
