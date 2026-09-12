"""Pons V2 launchpad client for Robinhood Chain.

Pons (github.com/ponsdotdev/ponsfamily) is a non-custodial launchpad: the
`PonsV2LaunchFactory` mints a fixed-supply ERC-20 straight onto a
constant-product bonding curve that later graduates into a locked Uniswap V4
pool. Launching is one `launchToken` call carrying the factory's `launchFee`
as `msg.value`.

Safety model
------------
* Everything is a dry run unless BOTH `FLY_LIVE_LAUNCH=1` is set and the
  caller passes `live=True`. Dry runs encode the exact calldata and value so
  they can be inspected.
* A launch needs a hosted logo URL, a name/symbol within the deployer's
  byte limits, a daily launch cap and a fee cap. `LaunchGuard` enforces it.
* The fly never sells. There is no `sell` here on purpose.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import LaunchpadConfig

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_NAME_BYTES, MAX_SYMBOL_BYTES, MAX_LOGO_BYTES, MAX_DESCRIPTION_BYTES, MAX_SOCIAL_BYTES = 64, 16, 512, 2048, 256

SOCIALS_TUPLE = "(string,string,string,string,string)"
TOKEN_PARAMS_TUPLE = f"(string,string,string,string,{SOCIALS_TUPLE},address,uint16,bool,bytes32,bytes32)"

FACTORY_ABI: list[dict[str, Any]] = [
    {
        "type": "function", "name": "launchToken", "stateMutability": "payable",
        "inputs": [
            {"name": "params", "type": "tuple", "components": [
                {"name": "name", "type": "string"},
                {"name": "symbol", "type": "string"},
                {"name": "logo", "type": "string"},
                {"name": "description", "type": "string"},
                {"name": "socials", "type": "tuple", "components": [
                    {"name": "twitter", "type": "string"},
                    {"name": "telegram", "type": "string"},
                    {"name": "discord", "type": "string"},
                    {"name": "website", "type": "string"},
                    {"name": "farcaster", "type": "string"},
                ]},
                {"name": "creatorFeeRecipient", "type": "address"},
                {"name": "creatorTaxBps", "type": "uint16"},
                {"name": "buybackEnabled", "type": "bool"},
                {"name": "expectedEconomics", "type": "bytes32"},
                {"name": "salt", "type": "bytes32"},
            ]},
            {"name": "launchConfigId", "type": "uint256"},
            {"name": "pairToken", "type": "address"},
        ],
        "outputs": [{"name": "token", "type": "address"}, {"name": "curve", "type": "address"}],
    },
    {"type": "function", "name": "launchFee", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "feeEscrow", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"type": "function", "name": "approvedPairTokens", "stateMutability": "view",
     "inputs": [{"name": "pairToken", "type": "address"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "pairTokenEconomics", "stateMutability": "view",
     "inputs": [{"name": "pairToken", "type": "address"}],
     "outputs": [{"name": "phantomQuote", "type": "uint256"}, {"name": "graduationThreshold", "type": "uint256"},
                 {"name": "decimals", "type": "uint8"}]},
    {"type": "function", "name": "launchEnabled", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "maxCreatorTaxBps", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "canLaunch", "stateMutability": "view", "inputs": [{"name": "launcher", "type": "address"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "launchConfigCount", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {
        "type": "function", "name": "getLaunchConfig", "stateMutability": "view",
        "inputs": [{"name": "id", "type": "uint256"}],
        "outputs": [{"type": "tuple", "components": [
            {"name": "supply", "type": "uint256"},
            {"name": "curveFeeBps", "type": "uint256"},
            {"name": "phantomQuote", "type": "uint256"},
            {"name": "graduationThreshold", "type": "uint256"},
            {"name": "poolFee", "type": "uint24"},
            {"name": "tickSpacing", "type": "int24"},
            {"name": "enabled", "type": "bool"},
        ]}],
    },
    {
        "type": "function", "name": "previewLaunchEconomics", "stateMutability": "view",
        "inputs": [{"name": "launchConfigId", "type": "uint256"}, {"name": "pairToken", "type": "address"}],
        "outputs": [{"type": "bytes32"}],
    },
    {
        "type": "event", "name": "TokenLaunched", "anonymous": False,
        "inputs": [
            {"name": "token", "type": "address", "indexed": True},
            {"name": "curve", "type": "address", "indexed": True},
            {"name": "deployer", "type": "address", "indexed": True},
            {"name": "pairToken", "type": "address", "indexed": False},
            {"name": "launchConfigId", "type": "uint256", "indexed": False},
            {"name": "graduationThreshold", "type": "uint256", "indexed": False},
        ],
    },
]

CURVE_ABI: list[dict[str, Any]] = [
    {
        "type": "function", "name": "buy", "stateMutability": "payable",
        "inputs": [
            {"name": "quoteIn", "type": "uint256"},
            {"name": "minTokensOut", "type": "uint256"},
            {"name": "recipient", "type": "address"},
        ],
        "outputs": [{"name": "tokensOut", "type": "uint256"}],
    },
    {"type": "function", "name": "getReserves", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}, {"type": "uint256"}]},
    {"type": "function", "name": "sweepFees", "stateMutability": "nonpayable", "inputs": [{"name": "minBuybackTokensOut", "type": "uint256"}], "outputs": []},
    {"type": "function", "name": "quoteFeeBalance", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "creatorTaxBalance", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "buybackEnabled", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "readyToGraduate", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "graduated", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]},
]


def mask_rpc(url: str) -> str:
    """Hide provider tokens embedded in RPC URLs when printing."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if parts.path.strip("/") or parts.query:
        return f"{parts.scheme}://{parts.netloc}/<token hidden>"
    return url


ESCROW_ABI: list[dict[str, Any]] = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view", "inputs": [{"name": "recipient", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "balanceOfToken", "stateMutability": "view",
     "inputs": [{"name": "recipient", "type": "address"}, {"name": "token", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "claim", "stateMutability": "nonpayable", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "claimToken", "stateMutability": "nonpayable", "inputs": [{"name": "token", "type": "address"}], "outputs": [{"type": "uint256"}]},
]

ERC20_ABI: list[dict[str, Any]] = [
    {"type": "function", "name": "symbol", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
    {"type": "function", "name": "decimals", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
    {"type": "function", "name": "balanceOf", "stateMutability": "view", "inputs": [{"name": "owner", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "allowance", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "approve", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "outputs": [{"type": "bool"}]},
]


class LaunchError(RuntimeError):
    pass


@dataclass
class TokenParams:
    name: str
    symbol: str
    logo: str
    description: str
    website: str = ""
    twitter: str = ""
    telegram: str = ""
    discord: str = ""
    farcaster: str = ""
    creator_fee_recipient: str = ZERO_ADDRESS
    creator_tax_bps: int = 0
    buyback_enabled: bool = True
    expected_economics: bytes = b"\x00" * 32
    salt: bytes = b"\x00" * 32

    def problems(self) -> list[str]:
        out = []
        b = lambda s: len(s.encode("utf-8"))
        if not self.name or b(self.name) > MAX_NAME_BYTES:
            out.append(f"name must be 1..{MAX_NAME_BYTES} bytes")
        if not self.symbol or b(self.symbol) > MAX_SYMBOL_BYTES:
            out.append(f"symbol must be 1..{MAX_SYMBOL_BYTES} bytes")
        if b(self.logo) > MAX_LOGO_BYTES:
            out.append(f"logo must be <= {MAX_LOGO_BYTES} bytes")
        if b(self.description) > MAX_DESCRIPTION_BYTES:
            out.append(f"description must be <= {MAX_DESCRIPTION_BYTES} bytes")
        for label in ("website", "twitter", "telegram", "discord", "farcaster"):
            if b(getattr(self, label)) > MAX_SOCIAL_BYTES:
                out.append(f"{label} must be <= {MAX_SOCIAL_BYTES} bytes")
        if not (0 <= self.creator_tax_bps <= 1000):
            out.append("creatorTaxBps must be within 0..1000 (protocol cap is 10%)")
        if len(self.expected_economics) != 32 or len(self.salt) != 32:
            out.append("expectedEconomics and salt must be 32 bytes")
        return out

    def as_abi_tuple(self) -> tuple:
        return (
            self.name, self.symbol, self.logo, self.description,
            (self.twitter, self.telegram, self.discord, self.website, self.farcaster),
            self.creator_fee_recipient, int(self.creator_tax_bps), bool(self.buyback_enabled),
            self.expected_economics, self.salt,
        )

    def as_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["expected_economics"] = "0x" + self.expected_economics.hex()
        d["salt"] = "0x" + self.salt.hex()
        return d


def make_salt(*parts: str) -> bytes:
    return hashlib.sha256("|".join([*parts, str(time.time_ns())]).encode()).digest()


@dataclass
class LaunchPlan:
    params: TokenParams
    launch_config_id: int
    pair_token: str
    chain_id: int
    factory: str
    calldata: str = ""
    fee_wei: int | None = None
    initial_buy_wei: int = 0
    live: bool = False
    sender: str = ""
    tx_hash: str = ""
    token: str = ""
    curve: str = ""
    buy_tx_hash: str = ""
    status: str = "planned"        # planned | blocked | sent | confirmed | failed
    problems: list[str] = field(default_factory=list)
    chain_status: dict[str, Any] = field(default_factory=dict)
    pair_symbol: str = "ETH"

    def as_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["params"] = self.params.as_json()
        return d

    def describe(self) -> str:
        fee = f"{self.fee_wei / 1e18:.6f} ETH" if self.fee_wei is not None else "unknown (rpc unreachable)"
        lines = [
            f"{'LIVE' if self.live else 'DRY RUN'} launch of {self.params.name} ({self.params.symbol}) on chain {self.chain_id}",
            f"  factory {self.factory}, launchConfigId {self.launch_config_id}, pairToken {self.pair_token} ({self.pair_symbol})",
            f"  trades in {self.pair_symbol}; launch fee {fee}, initial buy {self.initial_buy_wei / 1e18:.6f} {self.pair_symbol}",
            f"  logo {self.params.logo or '(none)'}",
            f"  status {self.status}",
        ]
        if self.problems:
            lines.append("  problems: " + "; ".join(self.problems))
        if self.tx_hash:
            lines.append(f"  tx {self.tx_hash} token {self.token} curve {self.curve}")
        return "\n".join(lines)


class PonsLaunchpad:
    def __init__(self, cfg: LaunchpadConfig):
        from web3 import Web3

        self.cfg = cfg
        self.w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 30}))
        self.factory = self.w3.eth.contract(address=Web3.to_checksum_address(cfg.factory), abi=FACTORY_ABI)
        self._account = None
        if cfg.private_key:
            from eth_account import Account

            self._account = Account.from_key(cfg.private_key)

    # -- read side -----------------------------------------------------------
    @property
    def address(self) -> str:
        return self._account.address if self._account else ""

    def connected(self) -> bool:
        try:
            return int(self.w3.eth.chain_id) == int(self.cfg.chain_id)
        except Exception:
            return False

    def pair_info(self) -> dict[str, Any]:
        """What the quote asset looks like on chain: symbol, decimals, whether
        Pons accepts it as a pair token, and its curve economics."""
        from web3 import Web3

        if self.cfg.pair_is_native:
            return {"native": True, "symbol": "ETH", "decimals": 18, "approved": True, "address": ZERO_ADDRESS}
        addr = Web3.to_checksum_address(self.cfg.pair_token)
        out: dict[str, Any] = {"native": False, "address": addr, "expected_symbol": self.cfg.pair_symbol}
        token = self.w3.eth.contract(address=addr, abi=ERC20_ABI)
        try:
            out["symbol"] = token.functions.symbol().call()
            out["decimals"] = int(token.functions.decimals().call())
        except Exception as exc:
            out["error"] = f"pair token unreadable: {exc}"
            return out
        try:
            out["approved"] = bool(self.factory.functions.approvedPairTokens(addr).call())
            pq, gt, dec = self.factory.functions.pairTokenEconomics(addr).call()
            scale = 10 ** int(dec or out["decimals"])
            out["economics"] = {"phantomQuote": pq / scale, "graduationThreshold": gt / scale, "decimals": int(dec)}
        except Exception as exc:
            out["error"] = f"factory pair read failed: {exc}"
        if self.address:
            try:
                out["walletBalance"] = token.functions.balanceOf(self.address).call() / 10 ** out["decimals"]
            except Exception:
                pass
        return out

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {"rpc": mask_rpc(self.cfg.rpc_url), "factory": self.cfg.factory, "wallet": self.address or None}
        if not self.connected():
            out["connected"] = False
            return out
        out["connected"] = True
        f = self.factory.functions
        for name, call in (
            ("launchEnabled", f.launchEnabled()),
            ("launchFee", f.launchFee()),
            ("maxCreatorTaxBps", f.maxCreatorTaxBps()),
            ("launchConfigCount", f.launchConfigCount()),
        ):
            try:
                out[name] = call.call()
            except Exception as exc:
                out[name] = f"error: {exc}"
        if self.address:
            try:
                out["canLaunch"] = f.canLaunch(self.address).call()
                out["balanceEth"] = float(self.w3.from_wei(self.w3.eth.get_balance(self.address), "ether"))
            except Exception as exc:
                out["canLaunch"] = f"error: {exc}"
        try:
            out["pair"] = self.pair_info()
        except Exception as exc:
            out["pair"] = f"error: {exc}"
        keys = ("supply", "curveFeeBps", "phantomQuote", "graduationThreshold", "poolFee", "tickSpacing", "enabled")
        try:
            out["launchConfig"] = dict(zip(keys, f.getLaunchConfig(self.cfg.launch_config_id).call()))
        except Exception as exc:
            out["launchConfig"] = f"error: {exc}"
        count = out.get("launchConfigCount")
        if isinstance(count, int) and count > 1:
            out["allLaunchConfigs"] = {}
            for i in range(min(count, 8)):
                try:
                    out["allLaunchConfigs"][i] = dict(zip(keys, f.getLaunchConfig(i).call()))
                except Exception as exc:
                    out["allLaunchConfigs"][i] = f"error: {exc}"
        return out

    def readiness(self, hosting_status: str = "") -> list[tuple[bool, str]]:
        """Checklist for a real launch: (ok, message) pairs."""
        checks: list[tuple[bool, str]] = []
        checks.append((bool(self._account), "wallet key set (FLY_WALLET_PRIVATE_KEY)"))
        connected = self.connected()
        checks.append((connected, f"RPC reachable and on chain {self.cfg.chain_id} ({mask_rpc(self.cfg.rpc_url)})"))
        st = self.status() if connected else {}
        fee = st.get("launchFee")
        if isinstance(fee, int):
            checks.append((fee <= int(self.cfg.max_launch_fee_eth * 1e18),
                           f"launch fee {fee / 1e18:.6f} ETH within FLY_MAX_LAUNCH_FEE_ETH={self.cfg.max_launch_fee_eth}"))
        else:
            checks.append((False, "launch fee readable"))
        checks.append((st.get("launchEnabled") is True, "factory launching enabled"))
        checks.append((st.get("canLaunch") is True, "this wallet may launch (canLaunch)"))
        lc = st.get("launchConfig")
        checks.append((isinstance(lc, dict) and bool(lc.get("enabled")), f"launch config {self.cfg.launch_config_id} enabled"))
        pair = st.get("pair") if isinstance(st.get("pair"), dict) else {}
        if not self.cfg.pair_is_native:
            sym = str(pair.get("symbol", "?"))
            checks.append((bool(pair) and "error" not in pair and sym.upper() == self.cfg.pair_symbol.upper(),
                           f"pair token {self.cfg.pair_token} is {sym} (expected {self.cfg.pair_symbol})"
                           + (f": {pair['error']}" if pair.get("error") else "")))
            checks.append((pair.get("approved") is True, f"Pons accepts {self.cfg.pair_symbol} as a pair token (approvedPairTokens)"))
            econ = pair.get("economics") or {}
            checks.append((bool(econ.get("graduationThreshold")),
                           f"{self.cfg.pair_symbol} curve economics set (graduates at {econ.get('graduationThreshold', '?')} {self.cfg.pair_symbol})"))
        bal = st.get("balanceEth")
        buy_eth = self.cfg.initial_buy_eth if self.cfg.pair_is_native else 0.0
        need = (fee if isinstance(fee, int) else 0) / 1e18 + buy_eth + 0.0005
        checks.append((isinstance(bal, float) and bal >= need, f"balance {bal if isinstance(bal, float) else '?'} ETH >= {need:.6f} needed (fee + gas)"))
        if not self.cfg.pair_is_native and self.cfg.initial_buy_eth > 0:
            have = pair.get("walletBalance")
            checks.append((isinstance(have, float) and have >= self.cfg.initial_buy_eth,
                           f"wallet holds {have if isinstance(have, float) else '?'} {self.cfg.pair_symbol} for the initial buy of {self.cfg.initial_buy_eth}"))
        checks.append((self.cfg.live, "FLY_LIVE_LAUNCH=1"))
        checks.append(("authenticated" in hosting_status or hosting_status.startswith("github:"), f"image host ready ({hosting_status})"))
        return checks

    # -- planning ------------------------------------------------------------
    def plan(self, params: TokenParams, initial_buy_eth: float = 0.0, live: bool = False) -> LaunchPlan:
        from web3 import Web3

        pair = Web3.to_checksum_address(self.cfg.pair_token)
        if params.creator_fee_recipient == ZERO_ADDRESS and self.cfg.creator_fee_recipient:
            params.creator_fee_recipient = Web3.to_checksum_address(self.cfg.creator_fee_recipient)
        plan = LaunchPlan(
            params=params, launch_config_id=self.cfg.launch_config_id, pair_token=pair,
            chain_id=self.cfg.chain_id, factory=self.cfg.factory,
            initial_buy_wei=int(initial_buy_eth * 1e18), live=bool(live and self.cfg.live), sender=self.address,
            pair_symbol=self.cfg.quote,
        )
        plan.problems.extend(params.problems())
        if self.connected():
            plan.chain_status = self.status()
            fee = plan.chain_status.get("launchFee")
            if isinstance(fee, int):
                plan.fee_wei = fee
            try:
                params.expected_economics = bytes(self.factory.functions.previewLaunchEconomics(plan.launch_config_id, pair).call())
            except Exception as exc:
                plan.problems.append(f"previewLaunchEconomics failed: {exc}")
        try:
            plan.calldata = self.factory.encode_abi("launchToken", args=[params.as_abi_tuple(), plan.launch_config_id, pair])
        except Exception as exc:
            plan.problems.append(f"abi encoding failed: {exc}")
        return plan

    # -- execution -----------------------------------------------------------
    def execute(self, plan: LaunchPlan, guard: "LaunchGuard | None" = None, memory=None) -> LaunchPlan:
        guard = guard or LaunchGuard(self.cfg)
        plan.problems = list(dict.fromkeys(plan.problems + guard.check(plan, memory)))
        if not plan.live:
            plan.status = "planned"
            return plan
        if plan.problems:
            plan.status = "blocked"
            return plan
        if not self._account:
            plan.problems.append("no wallet key")
            plan.status = "blocked"
            return plan

        w3 = self.w3
        try:
            fn = self.factory.functions.launchToken(plan.params.as_abi_tuple(), plan.launch_config_id, plan.pair_token)
            tx = self._build_tx(fn, value=int(plan.fee_wei or 0))
            signed = self._account.sign_transaction(tx)
            plan.tx_hash = w3.eth.send_raw_transaction(_raw(signed)).hex()
            plan.status = "sent"
            receipt = w3.eth.wait_for_transaction_receipt(plan.tx_hash, timeout=240)
            if receipt.get("status") != 1:
                plan.status = "failed"
                plan.problems.append("launch transaction reverted")
                return plan
            for ev in self.factory.events.TokenLaunched().process_receipt(receipt):
                plan.token = ev["args"]["token"]
                plan.curve = ev["args"]["curve"]
            plan.status = "confirmed"
        except Exception as exc:
            plan.status = "failed"
            plan.problems.append(f"launch failed: {exc}")
            return plan

        if plan.initial_buy_wei > 0 and plan.curve:
            try:
                plan.buy_tx_hash = self.buy(plan.curve, plan.initial_buy_wei / 1e18, live=True)
            except Exception as exc:
                plan.problems.append(f"initial buy failed: {exc}")
        return plan

    def buy(self, curve_address: str, eth_amount: float, live: bool = False, min_tokens_out: int = 0) -> str:
        """Buy from a launch's bonding curve with its quote asset: native ETH,
        or the ERC-20 pair token (approved first, sent with no value). The
        amount is in whole units of that asset. Returns the tx hash, or the
        encoded calldata when not live."""
        from web3 import Web3

        if eth_amount <= 0 or eth_amount > self.cfg.max_initial_buy_eth:
            raise LaunchError(f"buy amount must be within (0, {self.cfg.max_initial_buy_eth}] {self.cfg.quote}")
        curve_addr = Web3.to_checksum_address(curve_address)
        curve = self.w3.eth.contract(address=curve_addr, abi=CURVE_ABI)
        native = self.cfg.pair_is_native
        decimals = 18
        if not native:
            try:
                decimals = int(self.pair_info().get("decimals", 18))
            except Exception:
                pass
        amount = int(eth_amount * 10 ** decimals)
        recipient = self.address or ZERO_ADDRESS
        if not (live and self.cfg.live and self._account):
            return curve.encode_abi("buy", args=[amount, min_tokens_out, recipient])
        if not native:
            token = self.w3.eth.contract(address=Web3.to_checksum_address(self.cfg.pair_token), abi=ERC20_ABI)
            if token.functions.allowance(self.address, curve_addr).call() < amount:
                approve = self._build_tx(token.functions.approve(curve_addr, amount), value=0)
                self.w3.eth.wait_for_transaction_receipt(
                    self.w3.eth.send_raw_transaction(_raw(self._account.sign_transaction(approve))).hex(), timeout=240)
        tx = self._build_tx(curve.functions.buy(amount, min_tokens_out, recipient), value=amount if native else 0)
        signed = self._account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(_raw(signed)).hex()
        self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
        return tx_hash


    # -- creator fees ----------------------------------------------------------
    def fees(self, curves: list[str] | None = None) -> dict[str, Any]:
        """Creator-fee picture for the launch wallet: pending on each curve and
        claimable in the Pons fee escrow."""
        from web3 import Web3

        out: dict[str, Any] = {"wallet": self.address or None, "curves": {}}
        if not self.connected():
            out["error"] = "rpc unreachable"
            return out
        try:
            escrow_addr = self.factory.functions.feeEscrow().call()
            out["escrow"] = escrow_addr
            if self.address:
                escrow = self.w3.eth.contract(address=Web3.to_checksum_address(escrow_addr), abi=ESCROW_ABI)
                out["claimableEth"] = escrow.functions.balanceOf(self.address).call() / 1e18
                if not self.cfg.pair_is_native:
                    info = self.pair_info()
                    scale = 10 ** int(info.get("decimals", 18))
                    pair = Web3.to_checksum_address(self.cfg.pair_token)
                    out["claimable" + self.cfg.quote] = escrow.functions.balanceOfToken(self.address, pair).call() / scale
        except Exception as exc:
            out["error"] = f"escrow read failed: {exc}"
        out["quote"] = self.cfg.quote
        for c in curves or []:
            try:
                curve = self.w3.eth.contract(address=Web3.to_checksum_address(c), abi=CURVE_ABI)
                out["curves"][c] = {
                    "pendingFee": curve.functions.quoteFeeBalance().call() / 1e18,
                    "pendingCreatorTax": curve.functions.creatorTaxBalance().call() / 1e18,
                    "unit": self.cfg.quote,
                    "buybackEnabled": curve.functions.buybackEnabled().call(),
                    "graduated": curve.functions.graduated().call(),
                }
            except Exception as exc:
                out["curves"][c] = f"error: {exc}"
        return out

    def sweep_fees(self, curve_address: str, live: bool = False, min_buyback_tokens_out: int = 0) -> str:
        """Move a curve's pending fees into the escrow (permissionless). With
        buyback enabled the curve demands a non-zero output floor."""
        from web3 import Web3

        curve = self.w3.eth.contract(address=Web3.to_checksum_address(curve_address), abi=CURVE_ABI)
        if not (live and self.cfg.live and self._account):
            return curve.encode_abi("sweepFees", args=[min_buyback_tokens_out])
        tx = self._build_tx(curve.functions.sweepFees(min_buyback_tokens_out), value=0)
        signed = self._account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(_raw(signed)).hex()
        self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
        return tx_hash

    def claim_fees(self, live: bool = False, token: str = "") -> str:
        """Claim the wallet's escrow balance: in ETH, or in an ERC-20 pair
        token when `token` is given (the fees of a GOOGL-paired coin are GOOGL)."""
        from web3 import Web3

        escrow_addr = self.factory.functions.feeEscrow().call()
        escrow = self.w3.eth.contract(address=Web3.to_checksum_address(escrow_addr), abi=ESCROW_ABI)
        if token:
            fn = escrow.functions.claimToken(Web3.to_checksum_address(token))
            encoded = escrow.encode_abi("claimToken", args=[Web3.to_checksum_address(token)])
        else:
            fn = escrow.functions.claim()
            encoded = escrow.encode_abi("claim", args=[])
        if not (live and self.cfg.live and self._account):
            return encoded
        tx = self._build_tx(fn, value=0)
        signed = self._account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(_raw(signed)).hex()
        self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
        return tx_hash

    def _build_tx(self, fn, value: int) -> dict:
        base = {
            "from": self.address, "value": int(value),
            "nonce": self.w3.eth.get_transaction_count(self.address), "chainId": self.cfg.chain_id,
        }
        try:
            return fn.build_transaction(base)            # EIP-1559 fields filled by web3
        except Exception:
            return fn.build_transaction({**base, "gasPrice": self.w3.eth.gas_price})


def _raw(signed) -> bytes:
    return getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")


class LaunchGuard:
    """Refuses launches that are unsafe, unfunded, over budget or unhosted."""

    def __init__(self, cfg: LaunchpadConfig):
        self.cfg = cfg

    def check(self, plan: LaunchPlan, memory=None) -> list[str]:
        problems: list[str] = []
        p = plan.params
        if not p.logo.startswith(("https://", "ipfs://", "http://")):
            problems.append("logo must be a hosted URL (set FLY_IMAGE_HOST)")
        if plan.live:
            if not self.cfg.live:
                problems.append("FLY_LIVE_LAUNCH is not set")
            if not plan.sender:
                problems.append("FLY_WALLET_PRIVATE_KEY is not set")
            if plan.fee_wei is None:
                problems.append("launch fee unknown: rpc unreachable")
            elif plan.fee_wei > int(self.cfg.max_launch_fee_eth * 1e18):
                problems.append(f"launch fee exceeds FLY_MAX_LAUNCH_FEE_ETH={self.cfg.max_launch_fee_eth}")
            cs = plan.chain_status
            if cs.get("launchEnabled") is False:
                problems.append("factory reports launching disabled")
            if cs.get("canLaunch") is False:
                problems.append("factory reports this wallet cannot launch")
            lc = cs.get("launchConfig")
            if isinstance(lc, dict) and not lc.get("enabled", True):
                problems.append("selected launch config is disabled")
            need = int(plan.fee_wei or 0) + plan.initial_buy_wei
            bal = cs.get("balanceEth")
            if isinstance(bal, float) and bal * 1e18 < need * 1.05:
                problems.append("wallet balance too low for fee + buy + gas")
        if plan.initial_buy_wei > int(self.cfg.max_initial_buy_eth * 1e18):
            problems.append(f"initial buy exceeds FLY_MAX_INITIAL_BUY_ETH={self.cfg.max_initial_buy_eth}")
        if memory is not None:
            today = memory.count_since("launches", 24.0, live=True)
            if today >= self.cfg.max_launches_per_day:
                problems.append(f"daily launch cap reached ({today}/{self.cfg.max_launches_per_day})")
        forbidden = ("guaranteed", "risk-free", "investment", "will moon", "100x", "returns", "profit")
        negations = ("no ", "not ", "never ", "zero ", "isn't", "aren't")
        for sentence in re.split(r"[.!?\n]+", (p.name + ". " + p.description).lower()):
            if any(neg in sentence for neg in negations):
                continue                     # "not an investment" is a disclaimer, not a promise
            for word in forbidden:
                if word in sentence:
                    problems.append(f"description contains a financial promise: '{word}'")
        return problems


def plan_to_json(plan: LaunchPlan) -> str:
    return json.dumps(plan.as_json(), indent=2, default=str)
