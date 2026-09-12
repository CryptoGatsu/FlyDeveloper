// The fly cam. POST (from the fly's machine, authenticated with FLY_CAM_SECRET)
// stores a frame + status in Vercel Blob; GET returns the newest status for
// the site's live panel. Frames get unique names (immutable URLs, CDN-safe)
// and old ones are deleted so the store stays tiny.
"use strict";
const crypto = require("crypto");
const { put, list, del } = require("@vercel/blob");
const F = require("./_fly");

const PREFIX = "live/";
const KEEP = 3;

function authorized(req) {
  const want = process.env.FLY_CAM_SECRET || "";
  const got = String(req.headers["x-fly-cam"] || "");
  if (!want || got.length !== want.length) return false;
  return crypto.timingSafeEqual(Buffer.from(got), Buffer.from(want));
}

async function newest() {
  const { blobs } = await list({ prefix: PREFIX, limit: 100 });
  const metas = blobs.filter((b) => b.pathname.endsWith(".json")).sort((a, b) => (a.pathname < b.pathname ? 1 : -1));
  if (!metas.length) return null;
  const r = await fetch(metas[0].url, { cache: "no-store" });
  if (!r.ok) return null;
  return await r.json();
}

async function prune() {
  const { blobs } = await list({ prefix: PREFIX, limit: 200 });
  const stamps = [...new Set(blobs.map((b) => b.pathname.slice(PREFIX.length).split(".")[0]))].sort().reverse();
  const drop = new Set(stamps.slice(KEEP));
  const urls = blobs.filter((b) => drop.has(b.pathname.slice(PREFIX.length).split(".")[0])).map((b) => b.url);
  if (urls.length) await del(urls);
}

module.exports = async function handler(req, res) {
  try {
    if (!process.env.BLOB_READ_WRITE_TOKEN) return F.sendJson(res, 503, { error: "no blob store connected" });
    if (req.method === "GET") {
      const status = await newest();
      if (!status) return F.sendJson(res, 200, { phase: "idle", at: null });
      const ageSec = (Date.now() - new Date(status.at).getTime()) / 1000;
      return F.sendJson(res, 200, { ...status, age_sec: Math.round(ageSec), live: status.phase !== "idle" && ageSec < 90 });
    }
    if (req.method !== "POST") return F.sendJson(res, 405, { error: "POST a frame" });
    if (!authorized(req)) return F.sendJson(res, 401, { error: "bad cam secret" });
    const body = await F.readJson(req);
    const at = new Date().toISOString();
    const stamp = at.replace(/[-:.TZ]/g, "").slice(0, 17);
    const status = {
      at, phase: String(body.phase || "browsing").slice(0, 20), url: String(body.url || "").slice(0, 500),
      title: String(body.title || "").slice(0, 200), note: String(body.note || "").slice(0, 300), frame: "",
    };
    if (body.frame_b64) {
      const buf = Buffer.from(String(body.frame_b64), "base64");
      if (buf.length > 900_000) return F.sendJson(res, 413, { error: "frame too large" });
      const blob = await put(`${PREFIX}${stamp}.jpg`, buf, { access: "public", addRandomSuffix: false, contentType: "image/jpeg", cacheControlMaxAge: 3600 });
      status.frame = blob.url;
    }
    await put(`${PREFIX}${stamp}.json`, JSON.stringify(status), { access: "public", addRandomSuffix: false, contentType: "application/json", cacheControlMaxAge: 60 });
    prune().catch(() => {});
    return F.sendJson(res, 200, { ok: true, at, frame: status.frame });
  } catch (err) {
    return F.sendJson(res, 500, { error: String(err.message || err).slice(0, 200) });
  }
};
