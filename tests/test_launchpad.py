from fly.config import LaunchpadConfig
from fly.launchpad import (
    LaunchGuard, PonsLaunchpad, TokenParams, ZERO_ADDRESS, make_salt, FACTORY_ABI,
)
from fly.memory import Memory


def _lp(**kw):
    cfg = LaunchpadConfig(rpc_url="http://127.0.0.1:9", **kw)  # unreachable on purpose
    return PonsLaunchpad(cfg)


def _params(**kw):
    base = dict(name="Fly Window Coin", symbol="FLYWIN", logo="https://example.com/fly.png",
                description="A joke token created by an autonomous fly-brain agent.", salt=make_salt("t"))
    base.update(kw)
    return TokenParams(**base)


def test_launch_token_selector_matches_solidity_signature():
    from web3 import Web3

    sig = "launchToken((string,string,string,string,(string,string,string,string,string),address,uint16,bool,bytes32,bytes32),uint256,address)"
    expected = Web3.keccak(text=sig)[:4].hex()
    lp = _lp()
    plan = lp.plan(_params())
    assert plan.calldata[2:10] == expected


def test_dry_run_never_sends_and_reports_no_rpc():
    lp = _lp()
    plan = lp.execute(lp.plan(_params(), initial_buy_eth=0.001))
    assert plan.status == "planned"
    assert plan.live is False
    assert plan.tx_hash == ""
    assert plan.fee_wei is None
    assert plan.calldata.startswith("0x")


def test_live_requires_env_flag_key_and_rpc():
    lp = _lp(live=False)
    plan = lp.execute(lp.plan(_params(), live=True))
    assert plan.live is False           # cfg.live is False so it stays a dry run
    lp2 = _lp(live=True)
    plan2 = lp2.execute(lp2.plan(_params(), live=True))
    assert plan2.status == "blocked"
    joined = " ".join(plan2.problems)
    assert "FLY_WALLET_PRIVATE_KEY" in joined
    assert "rpc unreachable" in joined


def test_guard_rejects_unhosted_logo_and_promises(tmp_path):
    lp = _lp()
    mem = Memory(path=tmp_path / "m.json")
    plan = lp.plan(_params(logo="/local/file.png", description="guaranteed 100x"))
    problems = LaunchGuard(lp.cfg).check(plan, mem)
    joined = " ".join(problems)
    assert "hosted URL" in joined
    assert "financial promise" in joined


def test_guard_daily_cap(tmp_path):
    lp = _lp(max_launches_per_day=1)
    mem = Memory(path=tmp_path / "m.json")
    mem.add("launches", {"live": True, "symbol": "A"})
    plan = lp.plan(_params())
    assert any("daily launch cap" in p for p in LaunchGuard(lp.cfg).check(plan, mem))


def test_params_byte_limits():
    p = _params(name="x" * 65, symbol="Y" * 17)
    probs = p.problems()
    assert any("name" in s for s in probs) and any("symbol" in s for s in probs)
    assert _params().problems() == []
    assert _params().as_abi_tuple()[5] == ZERO_ADDRESS


def test_buy_dry_run_encodes_calldata():
    lp = _lp(max_initial_buy_eth=0.01)
    data = lp.buy("0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e", 0.001)
    assert data.startswith("0x") and len(data) == 2 + 8 + 64 * 3


def test_abi_has_event():
    assert any(e.get("name") == "TokenLaunched" for e in FACTORY_ABI)


def test_guard_allows_disclaimers_but_not_promises(tmp_path):
    lp = _lp()
    mem = Memory(path=tmp_path / "m.json")
    ok = lp.plan(_params(description="No utility, no roadmap, not an investment. Zero returns promised."))
    assert not [p for p in LaunchGuard(lp.cfg).check(ok, mem) if "promise" in p]
    bad = lp.plan(_params(description="Early holders get guaranteed returns. Will moon."))
    assert len([p for p in LaunchGuard(lp.cfg).check(bad, mem) if "promise" in p]) >= 2


def test_token_launched_event_decodes():
    """The receipt parser used after a live launch must understand the V2 event."""
    from web3 import Web3
    from eth_abi import encode

    lp = _lp()
    token = "0x" + "11" * 20
    curve = "0x" + "22" * 20
    deployer = "0x" + "33" * 20
    topic0 = Web3.keccak(text="TokenLaunched(address,address,address,address,uint256,uint256)")
    log = {
        "address": Web3.to_checksum_address(lp.cfg.factory),
        "topics": [topic0, bytes(12) + bytes.fromhex(token[2:]), bytes(12) + bytes.fromhex(curve[2:]), bytes(12) + bytes.fromhex(deployer[2:])],
        "data": encode(["address", "uint256", "uint256"], [ZERO_ADDRESS, 0, 10**18]),
        "blockHash": bytes(32), "blockNumber": 1, "logIndex": 0, "transactionHash": bytes(32), "transactionIndex": 0,
    }
    events = lp.factory.events.TokenLaunched().process_receipt({"logs": [log]})
    assert events[0]["args"]["token"] == Web3.to_checksum_address(token)
    assert events[0]["args"]["curve"] == Web3.to_checksum_address(curve)


def test_readiness_offline_lists_blockers():
    lp = _lp()
    checks = lp.readiness("none: launches will stay dry runs")
    assert any(not ok for ok, _ in checks)
    assert any("wallet key" in msg for _, msg in checks)


def test_rpc_token_is_masked():
    from fly.launchpad import mask_rpc

    assert mask_rpc("https://x.quiknode.pro/abc123/") == "https://x.quiknode.pro/<token hidden>"
    assert mask_rpc("https://rpc.mainnet.chain.robinhood.com") == "https://rpc.mainnet.chain.robinhood.com"
