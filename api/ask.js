// POST /api/ask  { message, history: [{role, content}] }  -> { reply, turns_left }
// GET  /api/ask  -> { turns_left, free_turns, burn: {token, amount, turns} }
"use strict";
const Anthropic = require("@anthropic-ai/sdk");
const F = require("./_fly");

const MODEL = process.env.FLY_CHAT_MODEL || "claude-opus-5";

module.exports = async function handler(req, res) {
  try {
    const allowance = F.readAllowance(req);
    if (req.method === "GET") {
      const state = await F.loadState().catch(() => ({}));
      const coin = F.genesisCoin(state);
      return F.sendJson(res, 200, {
        turns_left: F.turnsLeft(allowance), free_turns: F.FREE_TURNS,
        burn: { token: coin ? coin.token : "", symbol: coin ? coin.symbol : "FLYDEV", amount: F.BURN_AMOUNT, turns: F.BURN_TURNS,
                chain_id: 4663, explorer: "https://robinhoodchain.blockscout.com" },
        mood: (state.now || {}).mood || "",
      });
    }
    if (req.method !== "POST") return F.sendJson(res, 405, { error: "POST a message" });

    const body = await F.readJson(req);
    const message = String(body.message || "").trim().slice(0, 1500);
    if (!message) return F.sendJson(res, 400, { error: "say something" });

    if (F.turnsLeft(allowance) <= 0) {
      const state = await F.loadState().catch(() => ({}));
      const coin = F.genesisCoin(state);
      return F.sendJson(res, 402, {
        need_burn: true, turns_left: 0,
        burn: { token: coin ? coin.token : "", symbol: coin ? coin.symbol : "FLYDEV", amount: F.BURN_AMOUNT, turns: F.BURN_TURNS },
        reply: coin ? `That was your ${F.FREE_TURNS} free questions. Burn ${F.BURN_AMOUNT} $${coin.symbol} and I'll answer ${F.BURN_TURNS} more.`
                    : `That was your ${F.FREE_TURNS} free questions. Once $FLYDEV is live you can burn some for more; until then, come back tomorrow.`,
      });
    }
    const braked = F.brake(req);
    if (braked) return F.sendJson(res, 429, { error: braked, turns_left: F.turnsLeft(allowance) });

    const state = await F.loadState();
    const history = Array.isArray(body.history) ? body.history.slice(-10) : [];
    const messages = [];
    for (const h of history) {
      if ((h.role === "user" || h.role === "assistant") && typeof h.content === "string" && h.content.trim()) {
        messages.push({ role: h.role, content: h.content.slice(0, 1500) });
      }
    }
    if (messages.length && messages[0].role !== "user") messages.shift();
    messages.push({ role: "user", content: message });

    const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const response = await client.messages.create({
      model: MODEL,
      max_tokens: 700,
      output_config: { effort: "low" },
      system: [{ type: "text", text: F.persona(state), cache_control: { type: "ephemeral" } }],
      messages,
    });
    let reply = "";
    for (const block of response.content) if (block.type === "text") reply += block.text;
    if (response.stop_reason === "refusal" || !reply.trim()) reply = "The fly rubbed its legs together and declined that one. Ask something else.";

    // spend a turn: free first, then burned extras
    if (allowance.used < F.FREE_TURNS) allowance.used += 1; else allowance.extra = Math.max(0, allowance.extra - 1);
    F.writeAllowance(res, allowance);
    return F.sendJson(res, 200, { reply: reply.trim(), turns_left: F.turnsLeft(allowance), mood: (state.now || {}).mood || "" });
  } catch (err) {
    return F.sendJson(res, 500, { error: String(err.message || err).slice(0, 200) });
  }
};
