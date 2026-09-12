/* Genesis coin strip: the contract address of the fly's own coin on every page,
   with a copy button and links to Pons and the explorer. Mounts into #flycoin
   (or right after <header>). Reads /data/state.json fly.genesis; renders nothing
   until the coin is live. */
(function () {
  var host = document.getElementById("flycoin");
  if (!host) {
    host = document.createElement("div"); host.id = "flycoin";
    var header = document.querySelector("header");
    if (header && header.parentNode) header.parentNode.insertBefore(host, header.nextSibling);
    else { var main = document.querySelector("main") || document.body; main.insertBefore(host, main.firstChild); }
  }
  var css = "#flycoin{display:none;margin:0 0 18px;border:1px solid #2c3a2f;border-radius:12px;background:#0d1410;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#d8e2da}"
    + "#flycoin.on{display:block}#flycoin .row{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:10px 14px;font-size:.85rem;min-width:0}"
    + "#flycoin .sym{color:#9ef07a;font-weight:700}#flycoin .lbl{color:#8a978e}"
    + "#flycoin .ca{overflow-wrap:anywhere;word-break:break-all;color:#fff;user-select:all;min-width:0}"
    + "#flycoin button{font:inherit;font-size:.78rem;padding:4px 10px;border-radius:8px;border:1px solid #3a4a3e;background:#16211a;color:#d8e2da;cursor:pointer}"
    + "#flycoin button:hover{border-color:#9ef07a}#flycoin a{color:#9ef07a;text-decoration:none}#flycoin a:hover{text-decoration:underline}"
    + "#flycoin .pair{color:#8a978e;font-size:.78rem}"
    + "#flycoin .mc{color:#fff;font-weight:700}#flycoin .chg{font-weight:700}#flycoin .chg.up{color:#9ef07a}#flycoin .chg.down{color:#ff7a7a}";
  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  function money(v) {
    if (v == null || !isFinite(v)) return "";
    var a = Math.abs(v);
    if (a >= 1e9) return "$" + (v / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
    if (a >= 1e3) return "$" + (v / 1e3).toFixed(1) + "k";
    return "$" + v.toFixed(a >= 1 ? 2 : 4);
  }
  function market(m) {
    if (!m) return "";
    var out = "";
    if (m.mcap_usd != null) out += '<span class="lbl">MC</span><span class="mc">' + money(m.mcap_usd) + '</span>';
    else if (m.mcap_quote != null) out += '<span class="lbl">MC</span><span class="mc">' + Number(m.mcap_quote).toFixed(2) + " " + esc(m.quote || "") + '</span>';
    if (m.change_24h != null && isFinite(m.change_24h)) {
      var up = m.change_24h >= 0;
      out += '<span class="chg ' + (up ? "up" : "down") + '">' + (up ? "\u25B2 +" : "\u25BC ") + Number(m.change_24h).toFixed(1) + "%"
        + '<span class="lbl"> ' + esc(m.change_basis || "24h") + '</span></span>';
    }
    if (m.graduation_pct != null && !m.graduated) out += '<span class="lbl">' + Number(m.graduation_pct).toFixed(0) + '% to graduation</span>';
    return out;
  }
  function render(g) {
    if (!g || !g.token) return;
    host.innerHTML = '<div class="row"><span class="sym">$' + esc(g.symbol || "FLYDEV") + '</span><span class="lbl">CA</span>'
      + '<code class="ca" id="flycoin-ca">' + esc(g.token) + '</code>'
      + '<button type="button" id="flycoin-copy">copy</button>'
      + (g.pons ? '<a href="' + esc(g.pons) + '" target="_blank" rel="noopener">buy on Pons ↗</a>' : "")
      + (g.explorer_token ? '<a href="' + esc(g.explorer_token) + '" target="_blank" rel="noopener">explorer ↗</a>' : "")
      + (g.pair ? '<span class="pair">paired with ' + esc(g.pair) + '</span>' : "")
      + market(g.market) + '</div>';
    host.className = "on";
    var btn = document.getElementById("flycoin-copy");
    btn.addEventListener("click", function () {
      var done = function () { btn.textContent = "copied"; setTimeout(function () { btn.textContent = "copy"; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(g.token).then(done, function () { fallback(); });
      else fallback();
      function fallback() {
        var r = document.createRange(); r.selectNodeContents(document.getElementById("flycoin-ca"));
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
        try { document.execCommand("copy"); done(); } catch (e) {}
      }
    });
  }
  fetch("/data/state.json?t=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.json(); })
    .then(function (s) { render((s.fly || {}).genesis); }).catch(function () {});
})();
