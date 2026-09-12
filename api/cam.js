// The fly cam. POST (from the fly's machine, authenticated with FLY_CAM_SECRET)
// stores a frame + status in Vercel Blob; GET returns the newest status for
// the site's live panel; GET ?frame=<pathname> streams a frame. Works with a
// private or a public store: the function reads blobs with its own token.
"use strict";
const crypto = require("crypto");
const { put, list, del } = require("@vercel/blob");
const F = require("./_fly");

const PREFIX = "live/";
const KEEP = 3;

// Auth, in order: a long-lived BLOB_READ_WRITE_TOKEN (any prefix), else the
// Vercel OIDC token + BLOB_STORE_ID that a connected store injects on Vercel.
function staticToken() {
  const name = Object.keys(process.env).find((k) => k === "BLOB_READ_WRITE_TOKEN") || Object.keys(process.env).find((k) => k.endsWith("BLOB_READ_WRITE_TOKEN"));
  return name ? process.env[name] : "";
}
const TOKEN = staticToken();
const OIDC = () => process.env.VERCEL_OIDC_TOKEN || "";
const STORE_ID = process.env.BLOB_STORE_ID || "";
const authed = () => Boolean(TOKEN || (OIDC() && STORE_ID));
const sdkOpts = () => (TOKEN ? { token: TOKEN } : {});           // SDK uses OIDC + store id itself
const bearer = () => TOKEN || OIDC();
let accessMode = process.env.FLY_BLOB_ACCESS || "";   // "public" | "private", learned on first put

function authorized(req) {
  const want = process.env.FLY_CAM_SECRET || "";
  const got = String(req.headers["x-fly-cam"] || "");
  if (!want || got.length !== want.length) return false;
  return crypto.timingSafeEqual(Buffer.from(got), Buffer.from(want));
}

async function putAny(pathname, body, contentType, maxAge) {
  const opts = { addRandomSuffix: false, contentType, cacheControlMaxAge: maxAge };
  const modes = accessMode ? [accessMode] : (TOKEN ? ["public", "private"] : ["private", "public"]);
  let lastErr;
  for (const access of modes) {
    try {
      const blob = await put(pathname, body, { ...opts, access, ...sdkOpts() });
      accessMode = access;
      return blob;
    } catch (err) { lastErr = err; }
  }
  throw lastErr;
}

async function readBlob(url) {
  return fetch(url, { cache: "no-store", headers: { authorization: `Bearer ${bearer()}` } });
}

async function listLive() {
  const { blobs } = await list({ prefix: PREFIX, limit: 200, ...sdkOpts() });
  return blobs;
}

async function newest(blobs) {
  const metas = blobs.filter((b) => b.pathname.endsWith(".json")).sort((a, b) => (a.pathname < b.pathname ? 1 : -1));
  if (!metas.length) return null;
  const r = await readBlob(metas[0].url);
  if (!r.ok) return null;
  return await r.json();
}

async function prune(blobs) {
  const stamps = [...new Set(blobs.map((b) => b.pathname.slice(PREFIX.length).split(".")[0]))].sort().reverse();
  const drop = new Set(stamps.slice(KEEP));
  const urls = blobs.filter((b) => drop.has(b.pathname.slice(PREFIX.length).split(".")[0])).map((b) => b.url);
  if (urls.length) await del(urls, sdkOpts());
}

module.exports = async function handler(req, res) {
  try {
    if (!authed()) {
      const seen = Object.keys(process.env).filter((k) => /BLOB|VERCEL_ENV|VERCEL_OIDC/.test(k));
      return F.sendJson(res, 503, { error: "blob store not reachable: need BLOB_READ_WRITE_TOKEN, or VERCEL_OIDC_TOKEN + BLOB_STORE_ID", env: process.env.VERCEL_ENV || "?", seen });
    }
    const q = new URL(req.url || "/", "http://x").searchParams;

    if (req.method === "GET" && q.get("frame")) {
      const want = String(q.get("frame"));
      if (!/^live\/\d{17}\.jpg$/.test(want)) return F.sendJson(res, 400, { error: "bad frame" });
      const hit = (await listLive()).find((b) => b.pathname === want);
      if (!hit) return F.sendJson(res, 404, { error: "gone" });
      const r = await readBlob(hit.url);
      if (!r.ok) return F.sendJson(res, 502, { error: "blob read failed" });
      res.statusCode = 200;
      res.setHeader("Content-Type", "image/jpeg");
      res.setHeader("Cache-Control", "public, max-age=3600, immutable");
      res.end(Buffer.from(await r.arrayBuffer()));
      return;
    }
    if (req.method === "GET") {
      const status = await newest(await listLive());
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
      const pathname = `${PREFIX}${stamp}.jpg`;
      await putAny(pathname, buf, "image/jpeg", 3600);
      status.frame = `/api/cam?frame=${encodeURIComponent(pathname)}`;   // served by this function
    }
    await putAny(`${PREFIX}${stamp}.json`, JSON.stringify(status), "application/json", 60);
    listLive().then(prune).catch(() => {});
    return F.sendJson(res, 200, { ok: true, at, frame: status.frame, access: accessMode });
  } catch (err) {
    return F.sendJson(res, 500, { error: String(err.message || err).slice(0, 200) });
  }
};
