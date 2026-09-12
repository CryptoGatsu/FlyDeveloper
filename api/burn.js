// POST /api/burn { txHash }  -> verifies an ERC-20 burn of $FLYDEV on Robinhood
// Chain (a Transfer to the zero address from the genesis token contract) and
// grants FLY_BURN_TURNS more questions per FLY_BURN_AMOUNT burned.
"use strict";
const F = require("./_fly");

const RPC = process.env.FLY_RPC_URL || "https://rpc.mainnet.chain.robinhood.com";
const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const ZERO_TOPIC = "0x" + "0".repeat(64);
const usedHashes = new Set();   // best-effort replay brake; use Upstash for a durable one

async function rpc(method, params) {
  const r = await fetch(RPC, { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) });
  const j = await r.json();
  if (j.error) throw new Error(j.error.message || "rpc error");
  return j.result;
}

async function storeHas(key) {
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const tok = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!url || !tok) return usedHashes.has(key);
  const r = await fetch(`${url}/get/${encodeURIComponent(key)}`, { headers: { Authorization: `Bearer ${tok}` } });
  const j = await r.json().catch(() => ({}));
  return j.result != null;
}
async function storeSet(key) {
  usedHashes.add(key);
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const tok = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!url || !tok) return;
  await fetch(`${url}/set/${encodeURIComponent(key)}/1`, { headers: { Authorization: `Bearer ${tok}` } });
}

module.exports = async function handler(req, res) {
  try {
    if (req.method !== "POST") return F.sendJson(res, 405, { error: "POST { txHash }" });
    const body = await F.readJson(req);
    const txHash = String(body.txHash || "").trim().toLowerCase();
    if (!/^0x[0-9a-f]{64}$/.test(txHash)) return F.sendJson(res, 400, { error: "that is not a transaction hash" });

    const state = await F.loadState();
    const coin = F.genesisCoin(state);
    if (!coin) return F.sendJson(res, 409, { error: "$FLYDEV is not live yet" });
    const token = coin.token.toLowerCase();

    if (await storeHas(`burn:${txHash}`)) return F.sendJson(res, 409, { error: "that burn was already used" });
    const receipt = await rpc("eth_getTransactionReceipt", [txHash]);
    if (!receipt) return F.sendJson(res, 404, { error: "transaction not found yet; wait for it to confirm" });
    if (receipt.status !== "0x1") return F.sendJson(res, 400, { error: "that transaction failed" });

    let burnedWei = 0n;
    for (const log of receipt.logs || []) {
      if ((log.address || "").toLowerCase() !== token) continue;
      if (!log.topics || log.topics[0] !== TRANSFER_TOPIC || log.topics.length < 3) continue;
      if (log.topics[2].toLowerCase() !== ZERO_TOPIC) continue;          // to == 0x0 : a burn
      burnedWei += BigInt(log.data);
    }
    const burned = Number(burnedWei / 10n ** 18n);
    const passes = Math.floor(burned / F.BURN_AMOUNT);
    if (passes < 1) return F.sendJson(res, 400, { error: `that transaction burned ${burned} $${coin.symbol}; ${F.BURN_AMOUNT} buys ${F.BURN_TURNS} questions` });

    await storeSet(`burn:${txHash}`);
    const allowance = F.readAllowance(req);
    allowance.extra += passes * F.BURN_TURNS;
    allowance.passes = [...(allowance.passes || []), txHash].slice(-20);
    F.writeAllowance(res, allowance);
    return F.sendJson(res, 200, { ok: true, burned, turns_added: passes * F.BURN_TURNS, turns_left: F.turnsLeft(allowance) });
  } catch (err) {
    return F.sendJson(res, 500, { error: String(err.message || err).slice(0, 200) });
  }
};
