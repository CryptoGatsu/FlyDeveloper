import os

from fly.config import FlyConfig, config_warnings, load_dotenv


def test_dotenv_strips_inline_comments(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        'FLY_MIND=claude            # claude | offline\n'
        'FLY_WEBSITE="https://x.test/#frag"\n'
        'export FLY_EFFORT=low\n'
        'FLY_TWITTER=\n'
    )
    for k in ("FLY_MIND", "FLY_WEBSITE", "FLY_EFFORT", "FLY_TWITTER"):
        monkeypatch.delenv(k, raising=False)
    load_dotenv(env)
    assert os.environ["FLY_MIND"] == "claude"
    assert os.environ["FLY_WEBSITE"] == "https://x.test/#frag"
    assert os.environ["FLY_EFFORT"] == "low"
    assert os.environ["FLY_TWITTER"] == ""


def test_warnings_catch_address_as_key_and_fractional_bps(monkeypatch):
    monkeypatch.setenv("FLY_WALLET_PRIVATE_KEY", "0x" + "ab" * 20)   # 40 hex chars = an address
    monkeypatch.setenv("FLY_CREATOR_TAX_BPS", "2.5")
    monkeypatch.setenv("FLY_MIND", "offline")
    cfg = FlyConfig.from_env()
    joined = " ".join(config_warnings(cfg))
    assert "wallet ADDRESS" in joined
    assert "2.5% = 250" in joined
    assert cfg.launchpad.creator_tax_bps == 0
