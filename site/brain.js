/* Fly brain: live spike raster. Mounts into #flybrain (or prepends to <main>).
   Polls /api/brain every 5 s; falls back to /data/state.json brain_live. Replays the
   latest 100 ms of connectome activity on a loop, labelled with when it was recorded. */
(function () {
  var host = document.getElementById("flybrain");
  if (!host) { var main = document.querySelector("main") || document.body; host = document.createElement("div"); host.id = "flybrain"; main.insertBefore(host, main.firstChild); }
  var css = "#flybrain{margin:0 0 18px;border:1px solid #232a26;border-radius:12px;background:#0a0d0b;overflow:hidden;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}"
    + "#flybrain .bar{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:8px 12px;border-bottom:1px solid #232a26;font-size:.8rem;color:#8a978e}"
    + "#flybrain .tag{color:#d8e2da;font-weight:700}#flybrain .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#9ef07a;box-shadow:0 0 8px #9ef07a;margin-right:6px;vertical-align:middle;animation:flybrain-pulse 1s infinite}"
    + "@keyframes flybrain-pulse{50%{opacity:.4}}"
    + "#flybrain canvas{display:block;width:100%;height:auto;background:#050706}"
    + "#flybrain .legend{display:flex;flex-wrap:wrap;gap:6px 16px;padding:6px 12px;font-size:.75rem;color:#8a978e;border-top:1px solid #232a26}"
    + "#flybrain .legend b{color:#d8e2da}#flybrain .sw{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:middle;margin-right:5px}";
  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  host.innerHTML = '<div class="bar"><span><span class="dot"></span><span class="tag">CONNECTOME</span></span><span id="flybrain-when">loading the last brain reading…</span></div>'
    + '<canvas id="flybrain-canvas" width="1200" height="420"></canvas>'
    + '<div class="legend"><span><span class="sw" style="background:#ffb347"></span>sugar-sensing neurons (stimulated at 200 Hz)</span><span><span class="sw" style="background:#7fb3ff"></span>P9 walking neurons (100 Hz)</span><span><span class="sw" style="background:#9ef07a"></span>downstream neurons recruited through real synapses</span><span id="flybrain-stats"></span></div>';
  var canvas = document.getElementById("flybrain-canvas"), ctx = canvas.getContext("2d");
  var data = null, lastAt = "", t0 = performance.now(), LOOP_MS = 5000;
  var ago = function (iso) { if (!iso) return ""; var s = (Date.now() - new Date(iso).getTime()) / 1000; if (!isFinite(s)) return iso; if (s < 60) return "just now"; if (s < 3600) return Math.round(s / 60) + " min ago"; if (s < 86400) return Math.round(s / 3600) + " h ago"; return Math.round(s / 86400) + " d ago"; };

  function take(j) {
    if (!j || !j.rasters || !Object.keys(j.rasters).length) return;
    var at = j.at || j.received_at || "";
    if (at === lastAt && data) return;
    lastAt = at; data = j; t0 = performance.now();
    var total = 0, active = 0;
    Object.keys(j.rasters).forEach(function (k) { total += j.rasters[k].total_spikes || 0; active += j.rasters[k].active_neurons || 0; });
    document.getElementById("flybrain-when").textContent = "last reading " + ago(at) + " · replaying 100 ms of activity on a loop · mood " + (j.mood || "?") + " → " + (j.action || "?");
    document.getElementById("flybrain-stats").innerHTML = "<b>" + total.toLocaleString() + "</b> spikes across <b>" + active.toLocaleString() + "</b> of 138,639 neurons";
  }
  function poll() {
    fetch("/api/brain?t=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); }).then(take)
      .catch(function () { return fetch("/data/state.json?t=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (s) { take(s.brain_live); }).catch(function () {}); });
  }
  function draw() {
    requestAnimationFrame(draw);
    var W = canvas.width, H = canvas.height;
    ctx.fillStyle = "#050706"; ctx.fillRect(0, 0, W, H);
    if (!data) { ctx.fillStyle = "#8a978e"; ctx.font = "16px ui-monospace, monospace"; ctx.fillText("waiting for the first brain reading…", 20, 40); return; }
    var keys = Object.keys(data.rasters), lanes = keys.length || 1, laneH = H / lanes;
    var phase = ((performance.now() - t0) % LOOP_MS) / LOOP_MS;    // 0..1 across the 100 ms window
    keys.forEach(function (k, li) {
      var r = data.rasters[k], top = li * laneH, rows = Math.max(1, r.n_rows || 1), rowH = Math.max(1, (laneH - 24) / rows);
      var tmax = r.t_run_ms || 100, nowMs = phase * tmax;
      var col = k === "sugar" ? "#ffb347" : k === "walk" ? "#7fb3ff" : "#9ef07a";
      ctx.fillStyle = "#8a978e"; ctx.font = "12px ui-monospace, monospace";
      ctx.fillText(k === "sugar" ? "sugar → taste circuits" : k === "walk" ? "P9 → walking circuits" : k, 8, top + 14);
      // population rate strip (bottom of the lane)
      var pr = r.pop_rate_ms || [], pmax = 1; for (var i = 0; i < pr.length; i++) if (pr[i] > pmax) pmax = pr[i];
      for (var i = 0; i < pr.length; i++) { var x = (i / pr.length) * W, h = (pr[i] / pmax) * 18; ctx.fillStyle = i / pr.length <= phase ? col : "#1c231e"; ctx.fillRect(x, top + laneH - h - 2, Math.max(1, W / pr.length - 1), h); }
      // spikes: past ones dim, the ones at the playhead flash
      var sp = r.spikes || [];
      for (var i = 0; i < sp.length; i++) {
        var row = sp[i][0], t = sp[i][1]; if (t > nowMs) continue;
        var age = (nowMs - t) / tmax, x = (t / tmax) * W, y = top + 20 + row * rowH;
        var stim = row < (r.n_stimulated || 0);
        ctx.fillStyle = stim ? col : "#9ef07a";
        ctx.globalAlpha = age < 0.03 ? 1 : Math.max(0.18, 0.9 - age * 1.2);
        var s = age < 0.03 ? 3 : 1.6;
        ctx.fillRect(x, y, s, Math.max(1, Math.min(rowH, s)));
      }
      ctx.globalAlpha = 1;
      // playhead
      ctx.fillStyle = "rgba(216,226,218,.5)"; ctx.fillRect(phase * W, top, 1, laneH);
      if (li) { ctx.fillStyle = "#232a26"; ctx.fillRect(0, top, W, 1); }
    });
  }
  poll(); setInterval(poll, 5000); draw();
})();
