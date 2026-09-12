"""Market readout for the fly's coins: price, market cap and the 24 h move.

Two sources, best first:
* DexScreener, once it indexes the coin (it covers Robinhood Chain), gives
  USD price, market cap, 24 h change and volume straight away.
* The bonding curve itself, read over RPC: spot price in the quote asset
  (GOOGL) from the constant-product reserves, times the fixed supply. The
  quote asset's USD price comes from a public stock quote. The 24 h change
  is computed from the fly's own snapshots, taken every tick.
Everything degrades: no USD quote means GOOGL-denominated figures, no RPC
means the last snapshot stays on the site with its timestamp.
"""

from __future__ import annotations

import time
from typing import Any, Callable

DEXSCREENER = "https://api.dexscreener.com/latest/dex/tokens/{token}"
DEX_CHAIN = "robinhood"
SUPPLY = 1_000_000_000            # Pons V2 launch config: one billion tokens
USD_CACHE_SEC = 600


def _get_json(url: str, timeout: int = 12) -> Any:
    import requests

    r = requests.get(url, timeout=timeout, headers={"user-agent": "flydev/1.0 (+https://flydev.tech)"})
    r.raise_for_status()
    return r.json()


def quote_usd(symbol: str, fetch: Callable[[str], Any] = _get_json) -> float | None:
    """USD price of the quote asset: a stock ticker (GOOGL) via a public quote,
    ETH via CoinGecko. None when nothing answers."""
    sym = (symbol or "").upper()
    if sym == "ETH":
        try:
            return float(fetch("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd")["ethereum"]["usd"])
        except Exception:
            return None
    try:
        j = fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d")
        return float(j["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        pass
    try:                                                   # stooq csv fallback: Symbol,Date,Time,Open,High,Low,Close,Volume
        import requests

        txt = requests.get(f"https://stooq.com/q/l/?s={sym.lower()}.us&f=sd2t2ohlcv&h&e=csv", timeout=12).text
        close = txt.strip().splitlines()[-1].split(",")[6]
        return float(close)
    except Exception:
        return None


def from_dexscreener(token: str, fetch: Callable[[str], Any] = _get_json) -> dict[str, Any] | None:
    try:
        j = fetch(DEXSCREENER.format(token=token))
    except Exception:
        return None
    pairs = [p for p in (j or {}).get("pairs") or [] if str(p.get("chainId", "")).lower() == DEX_CHAIN]
    if not pairs:
        return None
    best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
    try:
        mcap = best.get("marketCap") or best.get("fdv")
        return {
            "source": "dexscreener", "url": best.get("url", ""),
            "price_usd": float(best["priceUsd"]) if best.get("priceUsd") else None,
            "mcap_usd": float(mcap) if mcap else None,
            "change_24h": float((best.get("priceChange") or {}).get("h24")) if (best.get("priceChange") or {}).get("h24") is not None else None,
            "volume_24h_usd": float((best.get("volume") or {}).get("h24") or 0) or None,
        }
    except (TypeError, ValueError):
        return None


def from_curve(launchpad, curve: str, quote_symbol: str, quote_usd_price: float | None, log=None) -> dict[str, Any] | None:
    """Spot price from the curve's reserves; None when the RPC is unreachable."""
    try:
        from web3 import Web3

        from .launchpad import CURVE_ABI

        c = launchpad.w3.eth.contract(address=Web3.to_checksum_address(curve), abi=CURVE_ABI)
        quote_res, token_res = c.functions.getReserves().call()
        real = c.functions.realQuoteReserve().call()
        threshold = c.functions.graduationThreshold().call()
        graduated = bool(c.functions.graduated().call())
    except Exception as exc:
        if log:
            log(f"  market: could not read the curve {curve}: {str(exc)[:160]}")
        return None
    if not token_res:
        return None
    price_q = quote_res / token_res                        # both 18-decimal, so the ratio is unit-free
    out: dict[str, Any] = {
        "source": "curve", "quote": quote_symbol, "price_quote": price_q, "mcap_quote": price_q * SUPPLY,
        "quote_usd": quote_usd_price, "graduated": graduated,
        "graduation_pct": min(100.0, 100.0 * real / threshold) if threshold else None,
    }
    if quote_usd_price:
        out["price_usd"] = price_q * quote_usd_price
        out["mcap_usd"] = out["mcap_quote"] * quote_usd_price
    return out


def change_over(history: list[dict[str, Any]], now_value: float | None, hours: float = 24.0, key: str = "mcap_usd") -> tuple[float | None, str]:
    """Percent change of `key` versus the snapshot nearest to `hours` ago.
    Returns (pct, basis) where basis is "24h" or "since launch" when the
    history is younger than that."""
    if now_value is None or not history:
        return None, ""
    target = time.time() - hours * 3600
    older = [h for h in history if h.get(key) is not None and float(h.get("ts", 0)) <= target]
    basis = "24h"
    if older:
        ref = max(older, key=lambda h: float(h.get("ts", 0)))
    else:
        cands = [h for h in history if h.get(key) is not None]
        if not cands:
            return None, ""
        ref = min(cands, key=lambda h: float(h.get("ts", 0)))
        basis = "since launch"
    base = float(ref[key])
    if base <= 0:
        return None, ""
    return 100.0 * (now_value - base) / base, basis


class Market:
    """Takes and remembers snapshots for the fly's genesis coin."""

    HISTORY_MAX = 900                 # ~3 days at one snapshot per 5 minutes

    def __init__(self, memory, fetch: Callable[[str], Any] = _get_json, log=None):
        self.memory = memory
        self.fetch = fetch
        self.log = log
        self._usd: tuple[float, float | None] = (0.0, None)

    def _quote_usd(self, symbol: str) -> float | None:
        at, val = self._usd
        if time.time() - at < USD_CACHE_SEC and val:
            return val
        val = quote_usd(symbol, self.fetch)
        if val:
            self._usd = (time.time(), val)
        return val or self._usd[1]

    def snapshot(self, launchpad, token: str, curve: str, quote_symbol: str) -> dict[str, Any] | None:
        snap = from_dexscreener(token, self.fetch)
        if snap is None and curve:
            snap = from_curve(launchpad, curve, quote_symbol, self._quote_usd(quote_symbol), log=self.log)
        if snap is None:
            if self.log:
                self.log("  market: no readout this time (not on DexScreener yet, curve unreadable)")
            return None
        history = self.memory.data.setdefault("market", [])
        key = "mcap_usd" if snap.get("mcap_usd") is not None else "mcap_quote"
        if snap.get("change_24h") is None:
            pct, basis = change_over(history, snap.get(key), key=key)
            snap["change_24h"], snap["change_basis"] = pct, basis
        else:
            snap["change_basis"] = "24h"
        snap["token"] = token
        entry = self.memory.add("market", {k: v for k, v in snap.items() if k in
                                           ("source", "price_usd", "mcap_usd", "price_quote", "mcap_quote", "quote_usd", "graduation_pct", "graduated")})
        if len(history) > self.HISTORY_MAX:
            del history[: len(history) - self.HISTORY_MAX]
        snap["at"] = entry["at"]
        return snap

    def series(self, hours: float = 24.0, points: int = 48) -> list[dict[str, Any]]:
        """Thinned history for a sparkline: [{ts, mcap_usd|mcap_quote}]."""
        cutoff = time.time() - hours * 3600
        hist = [h for h in self.memory.data.get("market", []) if float(h.get("ts", 0)) >= cutoff]
        if len(hist) > points:
            step = len(hist) / points
            hist = [hist[int(i * step)] for i in range(points)]
        return [{"ts": h.get("ts"), "mcap_usd": h.get("mcap_usd"), "mcap_quote": h.get("mcap_quote")} for h in hist]
