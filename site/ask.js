/* Ask the Fly: talks to /api/ask, and /api/burn for more questions. */
(function () {
  const $ = (id) => document.getElementById(id);
  const log = $("log"), form = $("form"), q = $("q"), send = $("send"), left = $("left"), hint = $("hint");
  const burn = $("burn"), burnStatus = $("burnStatus");
  let history = [];
  let burnInfo = { token: "", symbol: "FLYDEV", amount: 5000, turns: 10 };

  function add(role, text) {
    const div = document.createElement("div");
    div.className = "msg " + (role === "user" ? "me" : "fly");
    const who = document.createElement("div"); who.className = "who"; who.textContent = role === "user" ? "YOU" : "THE FLY";
    div.appendChild(who); div.appendChild(document.createTextNode(text));
    log.appendChild(div); log.scrollTop = log.scrollHeight;
  }
  function showBurn(on) {
    burn.classList.toggle("on", !!on);
    $("burnAmount").textContent = burnInfo.amount; $("burnSymbol").textContent = burnInfo.symbol; $("burnTurns").textContent = burnInfo.turns;
    $("tokenAddr").textContent = burnInfo.token || "(not launched yet)";
    $("noCoin").style.display = burnInfo.token ? "none" : "block";
    $("burnWallet").disabled = !burnInfo.token; $("verify").disabled = !burnInfo.token;
  }
  async function status() {
    try {
      const r = await fetch("/api/ask", { credentials: "same-origin" });
      const j = await r.json();
      left.textContent = j.turns_left; $("mood").textContent = j.mood || "unknown";
      if (j.burn) burnInfo = j.burn;
      showBurn(j.turns_left <= 0);
    } catch (e) { hint.textContent = "(chat is only live on flydev.tech; this copy has no brain attached)"; left.textContent = "–"; }
  }
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = q.value.trim(); if (!text) return;
    add("user", text); q.value = ""; send.disabled = true; hint.textContent = "the fly is thinking…";
    try {
      const r = await fetch("/api/ask", { method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: text, history }) });
      const j = await r.json();
      if (r.status === 402) { burnInfo = j.burn || burnInfo; add("fly", j.reply); left.textContent = 0; showBurn(true); }
      else if (!r.ok) { add("fly", "(" + (j.error || r.status) + ")"); }
      else {
        add("fly", j.reply); history.push({ role: "user", content: text }, { role: "assistant", content: j.reply }); history = history.slice(-10);
        left.textContent = j.turns_left; if (j.mood) $("mood").textContent = j.mood; showBurn(j.turns_left <= 0);
      }
    } catch (e) { add("fly", "(network trouble: " + e + ")"); }
    send.disabled = false; hint.textContent = "";
  });
  async function verifyHash(hash) {
    burnStatus.textContent = "verifying on chain…";
    const r = await fetch("/api/burn", { method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" }, body: JSON.stringify({ txHash: hash }) });
    const j = await r.json();
    if (!r.ok) { burnStatus.textContent = j.error || ("error " + r.status); return; }
    burnStatus.textContent = "burned " + j.burned + " $" + burnInfo.symbol + ": +" + j.turns_added + " questions"; left.textContent = j.turns_left; showBurn(false);
    add("fly", "You burned " + j.burned + " $" + burnInfo.symbol + ". Respect. " + j.turns_added + " more questions. Go.");
  }
  $("verify").addEventListener("click", () => { const h = $("txHash").value.trim(); if (/^0x[0-9a-fA-F]{64}$/.test(h)) verifyHash(h); else burnStatus.textContent = "paste a transaction hash"; });
  $("burnWallet").addEventListener("click", async () => {
    const eth = window.ethereum; if (!eth) { burnStatus.textContent = "no wallet found in this browser; use the manual burn below"; return; }
    try {
      const [from] = await eth.request({ method: "eth_requestAccounts" });
      const chain = await eth.request({ method: "eth_chainId" });
      if (parseInt(chain, 16) !== 4663) {
        try { await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: "0x1237" }] }); }
        catch (e) { burnStatus.textContent = "switch your wallet to Robinhood Chain (4663) and try again"; return; }
      }
      // burn(uint256) selector 0x42966c68, amount in wei (18 decimals)
      const amount = BigInt(Math.round(burnInfo.amount)) * (10n ** 18n);
      const data = "0x42966c68" + amount.toString(16).padStart(64, "0");
      burnStatus.textContent = "confirm the burn in your wallet…";
      const hash = await eth.request({ method: "eth_sendTransaction", params: [{ from, to: burnInfo.token, data }] });
      burnStatus.textContent = "sent " + hash.slice(0, 12) + "… waiting for confirmation";
      for (let i = 0; i < 30; i++) { await new Promise((r) => setTimeout(r, 4000)); try { await verifyHash(hash); if (!burn.classList.contains("on")) return; } catch (e) {} }
      burnStatus.textContent = "still confirming; paste the hash below in a moment";
      $("txHash").value = hash;
    } catch (e) { burnStatus.textContent = (e && e.message) ? e.message.slice(0, 120) : String(e); }
  });
  add("fly", "Hi. I'm a fly. Ask me something worth the neurons.");
  status();
})();
