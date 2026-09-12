"""Configuration for the fly, loaded from environment variables and `.env`.

Nothing here ever holds a secret in source: private keys, API tokens and
JWTs are read from the environment at runtime only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Robinhood Chain mainnet (Arbitrum Orbit L2).
ROBINHOOD_CHAIN_ID = 4663
ROBINHOOD_RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
ROBINHOOD_EXPLORER = "https://robinhoodchain.blockscout.com"

# Pons launchpad factories, from github.com/ponsdotdev/ponsfamily README.
# Always verify deployed bytecode against the verified sources before
# trusting an address.
PONS_V1_FACTORY = "0xA5aAb3F0c6EeadF30Ef1D3Eb997108E976351feB"
PONS_V2_FACTORY = "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader: KEY=VALUE lines, no expansion, never overrides."""
    path = path or REPO_ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if value[:1] in ('"', "'") and value.endswith(value[0]) and len(value) >= 2:
            value = value[1:-1]                      # quoted: keep everything inside
        elif " #" in value or "\t#" in value:
            value = value.split("#", 1)[0].strip()   # unquoted: drop inline comment
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class BrainConfig:
    # "connectome": run the FlyWire v783 LIF model on CPU (needs data/).
    # "phantom": a small synthetic connectome, for machines without the data.
    mode: str = "connectome"
    t_run_sec: float = 0.1
    seed: int | None = None
    completeness_csv: Path = REPO_ROOT / "data" / "2025_Completeness_783.csv"
    connectivity_parquet: Path = REPO_ROOT / "data" / "2025_Connectivity_783.parquet"
    cache_npz: Path = REPO_ROOT / "data" / "fly_connectome_cache.npz"
    phantom_neurons: int = 3000


@dataclass
class MindConfig:
    # "claude": Anthropic API. "offline": deterministic templates, no network.
    mode: str = "claude"
    model: str = "claude-opus-5"
    effort: str = "high"
    max_tokens: int = 16000
    code_max_tokens: int = 24000


@dataclass
class BrowserConfig:
    user_agent: str = "FlyDeveloper/0.1 (+https://github.com/CryptoGatsu/FlyDeveloper)"
    timeout_sec: float = 20.0
    max_pages_per_session: int = 6
    max_chars_per_page: int = 6000
    seeds: list[str] = field(default_factory=lambda: [
        "small tools people wish existed",
        "fruit fly research news",
        "open source developer tools trending",
        "problems with everyday software",
    ])


@dataclass
class LaunchpadConfig:
    rpc_url: str = ROBINHOOD_RPC_URL
    chain_id: int = ROBINHOOD_CHAIN_ID
    factory: str = PONS_V2_FACTORY
    explorer: str = ROBINHOOD_EXPLORER
    private_key: str = ""            # FLY_WALLET_PRIVATE_KEY
    live: bool = False               # FLY_LIVE_LAUNCH=1 arms real transactions
    launch_config_id: int = 0
    pair_token: str = "0x0000000000000000000000000000000000000000"  # native ETH quote
    creator_tax_bps: int = 0
    buyback_enabled: bool = True
    max_launches_per_day: int = 1
    initial_buy_eth: float = 0.0     # optional first curve buy, in ETH
    max_initial_buy_eth: float = 0.01
    max_launch_fee_eth: float = 0.01 # refuse to launch if the factory fee exceeds this
    creator_fee_recipient: str = ""  # defaults to the launching wallet
    website: str = "https://flydev.tech"
    twitter: str = "https://x.com/TheFlyDev_"
    telegram: str = ""
    # The fly's own coin: used for its first live launch. Empty name disables.
    genesis_name: str = "The Fly Dev"
    genesis_symbol: str = "FLYDEV"
    # Genesis creator fees stay in the fly's wallet (they fund the project):
    # buyback stays OFF for it. Other coins follow coin_fee_mode:
    #   "buyback": creator-bucket slice buys the coin back and locks it (on-chain)
    #   "wallet":  creator fees accrue to the fly's wallet like the genesis coin
    genesis_buyback: bool = False
    coin_fee_mode: str = "buyback"


@dataclass
class XConfig:
    handle: str = "@TheFlyDev_"
    api_key: str = ""            # X_API_KEY (consumer key)
    api_secret: str = ""         # X_API_SECRET
    access_token: str = ""       # X_ACCESS_TOKEN (the account's)
    access_secret: str = ""      # X_ACCESS_SECRET
    post: bool = False           # FLY_X_POST=1 sends posts; otherwise dry runs
    max_posts_per_day: int = 6
    max_replies_per_day: int = 30
    hype_every_hours: float = 8.0   # at most one unprompted $FLYDEV post per this many hours
    metrics_every_hours: float = 3.0


@dataclass
class HostingConfig:
    # "none" | "pinata" | "github"
    provider: str = "none"
    pinata_jwt: str = ""
    pinata_gateway: str = "https://gateway.pinata.cloud/ipfs"
    github_token: str = ""
    github_repo: str = ""            # owner/name
    github_branch: str = "main"
    github_dir: str = "memes"


def config_warnings(cfg: "FlyConfig") -> list[str]:
    """Human-readable problems with the loaded configuration."""
    out: list[str] = []
    key = cfg.launchpad.private_key.strip()
    if key:
        hexpart = key[2:] if key.lower().startswith("0x") else key
        if len(hexpart) == 40:
            out.append("FLY_WALLET_PRIVATE_KEY looks like a wallet ADDRESS (40 hex chars); it must be the private key (64 hex chars)")
        elif len(hexpart) != 64 or any(c not in "0123456789abcdefABCDEF" for c in hexpart):
            out.append("FLY_WALLET_PRIVATE_KEY is not a 64-hex-char private key")
    raw_tax = os.environ.get("FLY_CREATOR_TAX_BPS", "")
    if raw_tax and not raw_tax.strip().isdigit():
        out.append(f"FLY_CREATOR_TAX_BPS must be whole basis points (2.5% = 250), got '{raw_tax}'; using 0")
    if cfg.launchpad.coin_fee_mode not in ("buyback", "wallet"):
        out.append(f"FLY_COIN_FEE_MODE must be 'buyback' or 'wallet', got '{cfg.launchpad.coin_fee_mode}'")
    if cfg.launchpad.creator_tax_bps > 1000:
        out.append("FLY_CREATOR_TAX_BPS above the protocol cap of 1000 (10%)")
    for name in ("FLY_INITIAL_BUY_ETH", "FLY_MAX_INITIAL_BUY_ETH", "FLY_MAX_LAUNCH_FEE_ETH", "FLY_BRAIN_T_RUN"):
        raw = os.environ.get(name, "")
        if raw:
            try:
                float(raw)
            except ValueError:
                out.append(f"{name} is not a number: '{raw}'")
    if cfg.mind.mode == "offline" and os.environ.get("FLY_MIND", "claude") == "claude":
        out.append("no ANTHROPIC_API_KEY found, mind fell back to offline templates")
    if cfg.hosting.provider == "none" and cfg.launchpad.live:
        out.append("FLY_LIVE_LAUNCH=1 but FLY_IMAGE_HOST=none: launches will be blocked")
    return out


@dataclass
class FlyConfig:
    root: Path = REPO_ROOT
    workshop_dir: Path = REPO_ROOT / "workshop"
    memes_dir: Path = REPO_ROOT / "memes"
    memory_path: Path = REPO_ROOT / "data" / "fly_memory.json"
    brain: BrainConfig = field(default_factory=BrainConfig)
    mind: MindConfig = field(default_factory=MindConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    launchpad: LaunchpadConfig = field(default_factory=LaunchpadConfig)
    hosting: HostingConfig = field(default_factory=HostingConfig)
    x: XConfig = field(default_factory=XConfig)
    tick_interval_sec: int = 0       # 0 = free will: the fly paces itself
    max_actions_per_day: int = 80    # cost guard for the mind
    publish: str = "site"      # "none" | "site" (export site/data) | "git" (export + commit + push)
    site_domain: str = "flydev.tech"   # FLY_SITE_DOMAIN: writes site/CNAME for GitHub Pages custom domains
    site_url: str = "https://flydev.tech"
    cam_secret: str = ""               # FLY_CAM_SECRET: shared with the Vercel function; empty disables the cam

    @classmethod
    def from_env(cls, root: Path | None = None) -> "FlyConfig":
        load_dotenv()
        root = root or REPO_ROOT
        cfg = cls(root=root)
        cfg.workshop_dir = Path(_env("FLY_WORKSHOP_DIR", str(root / "workshop")))
        cfg.memes_dir = Path(_env("FLY_MEMES_DIR", str(root / "memes")))
        cfg.memory_path = Path(_env("FLY_MEMORY_PATH", str(root / "data" / "fly_memory.json")))
        cfg.tick_interval_sec = _env_int("FLY_TICK_INTERVAL_SEC", 0)
        cfg.max_actions_per_day = _env_int("FLY_MAX_ACTIONS_PER_DAY", 80)
        cfg.publish = _env("FLY_PUBLISH", "site").strip().lower()
        cfg.site_domain = _env("FLY_SITE_DOMAIN", "flydev.tech").strip()
        cfg.site_url = _env("FLY_SITE_URL", "https://flydev.tech").strip()
        cfg.cam_secret = _env("FLY_CAM_SECRET", "").strip()

        b = cfg.brain
        b.mode = _env("FLY_BRAIN", "connectome")
        b.t_run_sec = _env_float("FLY_BRAIN_T_RUN", 0.1)
        seed = _env("FLY_BRAIN_SEED", "")
        b.seed = int(seed) if seed.strip() else None
        b.completeness_csv = root / "data" / "2025_Completeness_783.csv"
        b.connectivity_parquet = root / "data" / "2025_Connectivity_783.parquet"
        b.cache_npz = root / "data" / "fly_connectome_cache.npz"
        if b.mode == "connectome" and not (
            b.completeness_csv.is_file() and b.connectivity_parquet.is_file()
        ):
            b.mode = "phantom"

        m = cfg.mind
        m.mode = _env("FLY_MIND", "claude")
        m.model = _env("FLY_MODEL", "claude-opus-5")
        m.effort = _env("FLY_EFFORT", "high")
        if m.mode == "claude" and not (
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        ):
            # The SDK can also resolve an `ant auth login` profile; we only
            # downgrade automatically when the user asked for it explicitly.
            if _env_bool("FLY_OFFLINE_IF_NO_KEY", True):
                m.mode = "offline"

        w = cfg.browser
        w.timeout_sec = _env_float("FLY_HTTP_TIMEOUT", 20.0)
        w.max_pages_per_session = _env_int("FLY_MAX_PAGES", 6)

        lp = cfg.launchpad
        lp.rpc_url = _env("FLY_RPC_URL", ROBINHOOD_RPC_URL)
        lp.chain_id = _env_int("FLY_CHAIN_ID", ROBINHOOD_CHAIN_ID)
        lp.factory = _env("FLY_PONS_FACTORY", PONS_V2_FACTORY)
        lp.private_key = _env("FLY_WALLET_PRIVATE_KEY", "")
        lp.live = _env_bool("FLY_LIVE_LAUNCH", False)
        lp.launch_config_id = _env_int("FLY_LAUNCH_CONFIG_ID", 0)
        lp.pair_token = _env("FLY_PAIR_TOKEN", lp.pair_token)
        lp.creator_tax_bps = _env_int("FLY_CREATOR_TAX_BPS", 0)
        lp.buyback_enabled = _env_bool("FLY_BUYBACK_ENABLED", True)
        lp.max_launches_per_day = _env_int("FLY_MAX_LAUNCHES_PER_DAY", 1)
        lp.initial_buy_eth = _env_float("FLY_INITIAL_BUY_ETH", 0.0)
        lp.max_initial_buy_eth = _env_float("FLY_MAX_INITIAL_BUY_ETH", 0.01)
        lp.max_launch_fee_eth = _env_float("FLY_MAX_LAUNCH_FEE_ETH", 0.01)
        lp.creator_fee_recipient = _env("FLY_CREATOR_FEE_RECIPIENT", "")
        lp.website = _env("FLY_WEBSITE", lp.website)
        lp.twitter = _env("FLY_TWITTER", lp.twitter)
        lp.telegram = _env("FLY_TELEGRAM", "")
        lp.genesis_name = _env("FLY_GENESIS_NAME", lp.genesis_name)
        lp.genesis_symbol = _env("FLY_GENESIS_SYMBOL", lp.genesis_symbol)
        lp.genesis_buyback = _env_bool("FLY_GENESIS_BUYBACK", False)
        lp.coin_fee_mode = _env("FLY_COIN_FEE_MODE", "buyback").strip().lower()

        xc = cfg.x
        xc.handle = _env("FLY_X_HANDLE", xc.handle)
        xc.api_key = _env("X_API_KEY", "")
        xc.api_secret = _env("X_API_SECRET", "")
        xc.access_token = _env("X_ACCESS_TOKEN", "")
        xc.access_secret = _env("X_ACCESS_SECRET", "")
        xc.post = _env_bool("FLY_X_POST", False)
        xc.max_posts_per_day = _env_int("FLY_X_MAX_POSTS_PER_DAY", 6)
        xc.max_replies_per_day = _env_int("FLY_X_MAX_REPLIES_PER_DAY", 30)
        xc.hype_every_hours = _env_float("FLY_X_HYPE_EVERY_HOURS", 8.0)

        h = cfg.hosting
        h.provider = _env("FLY_IMAGE_HOST", "none")
        h.pinata_jwt = _env("PINATA_JWT", "")
        h.pinata_gateway = _env("PINATA_GATEWAY", h.pinata_gateway)
        h.github_token = _env("FLY_GITHUB_TOKEN", _env("GITHUB_TOKEN", ""))
        h.github_repo = _env("FLY_GITHUB_REPO", "")
        h.github_branch = _env("FLY_GITHUB_BRANCH", "main")
        h.github_dir = _env("FLY_GITHUB_DIR", "memes")
        return cfg
