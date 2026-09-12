// The brain feed. POST (FLY_CAM_SECRET) stores the latest spike rasters in
// Vercel Blob; GET returns them for the home page's live raster. One object,
// overwritten each tick, served through this function (private-store safe).
"use strict";
const crypto = require("crypto");
const { put, list } = require("@vercel/blob");
const F = require("./_fly");

const PATH = "brain/latest.json";
function staticToken() {
  const name = Object.keys(process.env).find((k) => k === "BLOB_READ_WRITE_TOKEN") || Object.keys(process.env).find((k) => k.endsWith("BLOB_READ_WRITE_TOKEN"));
  return name ? process.env[name] : "";
}
const TOKEN = staticToken();
const sdkOpts = () => (TOKEN ? { token: TOKEN } : {});
let cache = { at: 0, body: "" };

function authorized(req) {
  const want = process.env.FLY_CAM_SECRET || "";
  const got = String(req.headers["x-fly-cam"] || "");
  return want && got.length === want.length && crypto.timingSafeEqual(Buffer.from(got), Buffer.from(want));
}
async function bearer(req) {
  if (TOKEN) return TOKEN;
  const h = req && req.headers && req.headers["x-vercel-oidc-token"];
  if (h) return String(h);
  try { const { getVercelOidcToken } = require("@vercel/oidc"); return await getVercelOidcToken(); } catch { return ""; }
}

module.exports = async function handler(req, res) {
  try {
    if (!TOKEN && !process.env.BLOB_STORE_ID) return F.sendJson(res, 503, { error: "blob store not connected" });
    if (req.method === "GET") {
      if (Date.now() - cache.at < 3000 && cache.body) { res.statusCode = 200; res.setHeader("Content-Type", "application/json"); res.setHeader("Cache-Control", "no-store"); return res.end(cache.body); }
      const { blobs } = await list({ prefix: "brain/", limit: 10, ...sdkOpts() });
      const hit = blobs.find((b) => b.pathname === PATH);
      if (!hit) return F.sendJson(res, 200, { at: null, rasters: {} });
      const r = await fetch(hit.url, { cache: "no-store", headers: { authorization: `Bearer ${await bearer(req)}` } });
      if (!r.ok) return F.sendJson(res, 502, { error: "blob read failed" });
      const body = await r.text();
      cache = { at: Date.now(), body };
      res.statusCode = 200; res.setHeader("Content-Type", "application/json"); res.setHeader("Cache-Control", "no-store");
      return res.end(body);
    }
    if (req.method !== "POST") return F.sendJson(res, 405, { error: "POST rasters" });
    if (!authorized(req)) return F.sendJson(res, 401, { error: "bad cam secret" });
    const body = await F.readJson(req);
    if (!body || typeof body !== "object" || !body.rasters) return F.sendJson(res, 400, { error: "no rasters" });
    const text = JSON.stringify({ ...body, received_at: new Date().toISOString() });
    if (text.length > 900_000) return F.sendJson(res, 413, { error: "too large" });
    let blob;
    try { blob = await put(PATH, text, { access: "public", addRandomSuffix: false, allowOverwrite: true, contentType: "application/json", cacheControlMaxAge: 60, ...sdkOpts() }); }
    catch { blob = await put(PATH, text, { access: "private", addRandomSuffix: false, allowOverwrite: true, contentType: "application/json", cacheControlMaxAge: 60, ...sdkOpts() }); }
    cache = { at: Date.now(), body: text };
    return F.sendJson(res, 200, { ok: true, url: blob.url });
  } catch (err) {
    return F.sendJson(res, 500, { error: String(err.message || err).slice(0, 200) });
  }
};
