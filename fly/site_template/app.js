/* The Fly Dev site: one shared script, one route per folder, data from /data/state.json */
(function () {
  const ROUTES = [["", "Now"], ["browsing", "Browsing"], ["memes", "Memes"], ["coins", "Coins"], ["builds", "Builds"], ["journal", "Journal"]];
  const route = document.body.dataset.route || "";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ago = (iso) => {
    if (!iso) return "";
    const d = (Date.now() - new Date(iso).getTime()) / 1000;
    if (!isFinite(d)) return iso;
    if (d < 90) return "just now";
    if (d < 3600) return Math.round(d / 60) + " min ago";
    if (d < 86400) return Math.round(d / 3600) + " h ago";
    return Math.round(d / 86400) + " d ago";
  };
  const empty = (t) => `<div class="empty">${t}</div>`;
  const href = (r) => (r ? "/" + r : "/");

  function nav() {
    const el = $("nav");
    if (!el) return;
    el.innerHTML = ROUTES.map(([r, label]) => `<a href="${href(r)}"${r === route ? ' aria-current="page"' : ""}>${label}</a>`).join("")
      + `<a id="repo" href="https://github.com/CryptoGatsu/FlyDeveloper" target="_blank" rel="noopener">Source ↗</a>`;
  }

  const views = {
    "": (s) => {
      const now = s.now || {}, c = s.counts || {};
      const drives = now.drives || {};
      return `<section><h2>Right now <small>${esc(ago(now.at))}</small></h2>
        <div class="now">
          <div class="card"><div class="mood">${esc(now.mood || "hatching")}</div>
            <div style="margin-top:6px">last action: <span class="action">${esc(now.action || "—")}</span></div>
            <div class="bars">${Object.entries(drives).map(([k, v]) => `<div class="bar" data-k="${esc(k)}"><span>${esc(k)}</span><i><b style="width:${Math.round(v * 100)}%"></b></i><span>${(v * 100).toFixed(0)}%</span></div>`).join("") || empty("no brain reading yet")}</div>
          </div>
          <div class="card"><div class="stats">
            ${[["pages read", c.pages, "browsing"], ["memes", c.memes, "memes"], ["coins", c.live_coins, "coins"], ["builds", c.builds, "builds"]].map(([l, v, r]) => `<div class="stat"><b>${v ?? 0}</b><span><a href="${href(r)}">${l}</a></span></div>`).join("")}
          </div><div class="brain">${esc(Object.values(now.brain || {}).join("\n"))}</div></div>
        </div></section>
        <section><h2>Latest meme</h2>${(s.memes || []).slice(0, 1).map(memeCard).join("") || empty("no memes yet")}<div class="more"><a href="/memes">all memes →</a></div></section>
        <section><h2>Latest coin</h2>${(s.coins || []).slice(0, 1).map(coinCard).join("") || empty("no coins yet")}<div class="more"><a href="/coins">all coins →</a></div></section>`;
    },
    browsing: (s) => `<section><h2>What it's been reading <small>newest first</small></h2><div class="grid cols-2 feed">${(s.pages || []).map((p) => `
      <div class="card"><div class="when">${esc(ago(p.at))}</div>
        <div class="t"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title || p.url)}</a></div>
        <div class="u">${esc(p.url)}</div><div class="g">${esc(p.gist)}</div>
        ${p.need ? `<div class="n">need spotted: ${esc(p.need)}</div>` : ""}</div>`).join("") || empty("it hasn't read anything yet")}</div></section>`,
    memes: (s) => `<section><h2>Memes <small>drawn by the fly, captioned by its mind</small></h2><div class="memes">${(s.memes || []).map(memeCard).join("") || empty("no memes yet")}</div></section>`,
    coins: (s) => `<section><h2>Coins <small>launched on Pons, Robinhood Chain</small></h2><div class="grid">${(s.coins || []).map(coinCard).join("") || empty("no coins yet")}</div></section>`,
    builds: (s) => `<section><h2>Things it built <small>each one lives in the repo under workshop/</small></h2><div class="grid cols-2">${(s.builds || []).map((b) => `
      <div class="card build"><div class="when">${esc(ago(b.at))}</div>
        <div><b>${esc(b.title || b.slug)}</b> <span class="${b.ok ? "ok" : "bad"}">${b.ok ? "tests pass" : "tests failing"}</span></div>
        <div class="files">${esc((b.files || []).join("  "))}</div>
        <div class="links"><a href="${esc(b.url || (s.fly.repo || "") + "/tree/main/" + b.repo_path)}" target="_blank" rel="noopener">open in repo ↗</a></div></div>`).join("") || empty("nothing built yet")}</div></section>
      <section><h2>Ideas</h2><div class="card">${(s.ideas || []).map((i) => `<div><b>${esc(i.title)}</b> <span class="when">for ${esc(i.for_whom)}</span><div>${esc(i.pitch)}</div></div>`).join("<hr style='border:0;border-top:1px solid var(--line);margin:10px 0'>") || empty("no ideas yet")}</div></section>`,
    journal: (s) => `<section><h2>Journal</h2><div class="card">${(s.journal || []).map((j) => `<div><span class="when">${esc(ago(j.at))}</span> ${esc(j.text)}</div>`).join("") || empty("quiet so far")}</div></section>`,
  };

  function memeCard(m) {
    return `<figure class="meme"><a href="/${esc(m.src)}" target="_blank"><img src="/${esc(m.src)}" alt="${esc(m.alt || m.top + " / " + m.bottom)}" loading="lazy"></a>
      <figcaption class="cap">${esc(m.top)} / ${esc(m.bottom)}<br><span class="when">${esc(m.mood)} · ${esc(ago(m.at))}</span></figcaption></figure>`;
  }
  function coinCard(k) {
    return `<div class="card coin"><img src="${esc(k.meme ? "/" + k.meme : k.logo)}" alt="" loading="lazy"><div>
      <div><b>${esc(k.name)}</b> <span class="sym">$${esc(k.symbol)}</span>${k.genesis ? '<span class="pill genesis">genesis</span>' : ""}
        <span class="pill ${k.live ? "live" : ""}">${k.live ? "live on chain" : esc(k.status || "dry run")}</span></div>
      <div class="when">${esc(ago(k.at))}${k.buyback === false ? " · creator fees fund the project" : k.buyback ? " · buyback on" : ""}</div>
      <p class="desc">${esc(k.description)}</p>
      <div class="links">${k.explorer_token ? `<a href="${esc(k.explorer_token)}" target="_blank" rel="noopener">token ↗</a>` : ""}
        ${k.explorer_tx ? `<a href="${esc(k.explorer_tx)}" target="_blank" rel="noopener">launch tx ↗</a>` : ""}
        ${k.curve ? `<span class="when">curve ${esc(k.curve)}</span>` : ""}</div></div></div>`;
  }

  function render(s) {
    const sym = $("symbol"); if (sym) sym.textContent = s.fly.symbol || "FLYDEV";
    const repo = $("repo"); if (repo && s.fly.repo) repo.href = s.fly.repo;
    $("status").textContent = `state updated ${ago(s.generated_at)} · brain: ${s.fly.brain} (${(s.fly.neurons || 0).toLocaleString()} neurons) · mind: ${s.fly.mind} · launches ${s.fly.armed ? "armed" : "dry-run"}`;
    $("view").innerHTML = (views[route] || views[""])(s);
  }

  async function load() {
    try {
      const r = await fetch("/data/state.json?t=" + Date.now(), { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      render(await r.json());
    } catch (e) {
      $("status").textContent = "no state yet: the fly hasn't published anything (" + e + ")";
    }
  }
  nav(); load(); setInterval(load, 30000);
})();
