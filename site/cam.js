/* Fly cam: live panel fed by /api/cam. Mounts into #flycam if present,
   otherwise prepends itself to <main>. Polls every 3 s. */
(function () {
  var host = document.getElementById("flycam");
  if (!host) { var main = document.querySelector("main") || document.body; host = document.createElement("div"); host.id = "flycam"; main.insertBefore(host, main.firstChild); }
  var css = "#flycam{margin:0 0 18px;border:1px solid #232a26;border-radius:12px;background:#0f1310;overflow:hidden;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}"
    + "#flycam .bar{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:8px 12px;border-bottom:1px solid #232a26;font-size:.8rem;color:#8a978e}"
    + "#flycam .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#555;margin-right:6px;vertical-align:middle}"
    + "#flycam.live .dot{background:#ff5252;box-shadow:0 0 8px #ff5252;animation:flycam-blink 1.2s infinite}"
    + "@keyframes flycam-blink{50%{opacity:.35}}"
    + "#flycam .tag{color:#d8e2da;font-weight:700}#flycam.live .tag{color:#ff8a80}"
    + "#flycam .url{color:#9ef07a;overflow-wrap:anywhere;text-decoration:none}#flycam .url:hover{text-decoration:underline}"
    + "#flycam .stage{position:relative;background:#000;min-height:120px}"
    + "#flycam img{display:block;width:100%;height:auto;max-height:70vh;object-fit:contain;object-position:top;background:#000}"
    + "#flycam .empty{padding:28px 12px;color:#8a978e;font-size:.9rem;text-align:center}"
    + "#flycam .note{padding:8px 12px;font-size:.8rem;color:#d8e2da;border-top:1px solid #232a26}";
  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  host.innerHTML = '<div class="bar"><span><span class="dot"></span><span class="tag" id="flycam-tag">FLY CAM</span></span><span id="flycam-when"></span><a class="url" id="flycam-url" target="_blank" rel="noopener"></a></div>'
    + '<div class="stage" id="flycam-stage"><div class="empty">warming up the compound eye…</div></div><div class="note" id="flycam-note" style="display:none"></div>';
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var ago = function (s) { if (s == null) return ""; if (s < 5) return "now"; if (s < 60) return s + "s ago"; if (s < 3600) return Math.round(s / 60) + " min ago"; if (s < 86400) return Math.round(s / 3600) + " h ago"; return Math.round(s / 86400) + " d ago"; };
  var lastFrame = "";
  function render(j) {
    var live = !!j.live;
    host.classList.toggle("live", live);
    document.getElementById("flycam-tag").textContent = live ? "LIVE · " + (j.phase === "searching" ? "searching" : "browsing") : "FLY CAM · idle";
    document.getElementById("flycam-when").textContent = j.at ? (live ? "" : "last seen " + ago(j.age_sec)) : "no signal yet";
    var a = document.getElementById("flycam-url"); a.textContent = j.title || j.url || ""; a.href = j.url || "#"; if (!j.url) a.removeAttribute("href");
    var stage = document.getElementById("flycam-stage");
    if (j.frame && j.frame !== lastFrame) { lastFrame = j.frame; stage.innerHTML = '<img src="' + esc(j.frame) + '" alt="What the fly is looking at right now">'; }
    else if (!j.frame && !lastFrame) { stage.innerHTML = '<div class="empty">' + (j.at ? esc(j.note || "nothing on screen") : "the fly has not gone online yet") + "</div>"; }
    var note = document.getElementById("flycam-note"); note.style.display = j.note ? "block" : "none"; note.textContent = j.note || "";
  }
  function poll() {
    fetch("/api/cam?t=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.json(); }).then(render).catch(function () {});
  }
  poll(); setInterval(poll, 3000);
})();
