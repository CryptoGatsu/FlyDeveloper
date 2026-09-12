import time

from fly.market import Market, change_over, from_dexscreener, quote_usd
from fly.memory import Memory


def test_dexscreener_picks_the_deepest_robinhood_pair():
    j = {"pairs": [
        {"chainId": "base", "priceUsd": "9", "marketCap": 1, "liquidity": {"usd": 999}},
        {"chainId": "robinhood", "priceUsd": "0.00001", "marketCap": 10000, "priceChange": {"h24": 4.2}, "volume": {"h24": 500},
         "liquidity": {"usd": 100}, "url": "https://dexscreener.com/robinhood/x"},
        {"chainId": "robinhood", "priceUsd": "0.00002", "fdv": 20000, "liquidity": {"usd": 5}},
    ]}
    m = from_dexscreener("0xabc", fetch=lambda url: j)
    assert m["source"] == "dexscreener" and m["mcap_usd"] == 10000 and m["change_24h"] == 4.2 and m["price_usd"] == 0.00001
    assert from_dexscreener("0xabc", fetch=lambda url: {"pairs": []}) is None
    assert from_dexscreener("0xabc", fetch=lambda url: (_ for _ in ()).throw(RuntimeError("down"))) is None


def test_quote_usd_reads_yahoo_then_falls_back():
    assert quote_usd("GOOGL", fetch=lambda url: {"chart": {"result": [{"meta": {"regularMarketPrice": 245.5}}]}}) == 245.5
    assert quote_usd("ETH", fetch=lambda url: {"ethereum": {"usd": 3000}}) == 3000.0


def test_change_over_uses_24h_ago_or_launch():
    now = time.time()
    hist = [{"ts": now - 30 * 3600, "mcap_usd": 100.0}, {"ts": now - 25 * 3600, "mcap_usd": 200.0}, {"ts": now - 3600, "mcap_usd": 300.0}]
    pct, basis = change_over(hist, 220.0)
    assert basis == "24h" and abs(pct - 10.0) < 1e-9                     # against the 25 h old point, not the 30 h one
    pct, basis = change_over([{"ts": now - 3600, "mcap_usd": 100.0}], 150.0)
    assert basis == "since launch" and abs(pct - 50.0) < 1e-9
    assert change_over([], 1.0) == (None, "")


class FakeFn:
    def __init__(self, v): self.v = v
    def call(self): return self.v


class FakeCurveFns:
    def getReserves(self): return FakeFn((20 * 10**18, 800_000_000 * 10**18))       # 20 GOOGL vs 800M tokens
    def realQuoteReserve(self): return FakeFn(int(2.42 * 10**18))
    def graduationThreshold(self): return FakeFn(int(24.2 * 10**18))
    def graduated(self): return FakeFn(False)


class FakeLaunchpad:
    class w3:
        class eth:
            @staticmethod
            def contract(address, abi): return type("C", (), {"functions": FakeCurveFns()})()


def test_snapshot_from_curve_prices_in_quote_and_usd(tmp_path):
    mem = Memory(tmp_path / "m.json")
    calls = []

    def fetch(url):
        calls.append(url)
        if "dexscreener" in url:
            return {"pairs": []}                                     # not indexed yet
        return {"chart": {"result": [{"meta": {"regularMarketPrice": 200.0}}]}}

    mk = Market(mem, fetch=fetch)
    snap = mk.snapshot(FakeLaunchpad(), "0x" + "ab" * 20, "0x" + "cd" * 20, "GOOGL")
    assert snap["source"] == "curve" and snap["quote"] == "GOOGL"
    assert abs(snap["price_quote"] - 20 / 800_000_000) < 1e-15
    assert abs(snap["mcap_quote"] - 25.0) < 1e-9                        # 1B supply at 20/800M GOOGL each
    assert abs(snap["mcap_usd"] - 5000.0) < 1e-6 and abs(snap["graduation_pct"] - 10.0) < 1e-6
    assert snap["change_basis"] == "" and snap["change_24h"] is None     # first ever point
    snap2 = mk.snapshot(FakeLaunchpad(), "0x" + "ab" * 20, "0x" + "cd" * 20, "GOOGL")
    assert snap2["change_basis"] == "since launch" and snap2["change_24h"] == 0.0
    assert len(mem.data["market"]) == 2 and mk.series()[-1]["mcap_usd"] == 5000.0
    assert sum("yahoo" in c for c in calls) == 1                         # the USD quote is cached
