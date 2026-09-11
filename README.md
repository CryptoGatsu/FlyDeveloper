# FlyDeveloper

A fruit fly that develops tech, browses the internet, draws fly memes and
launches memecoins on the [Pons](https://github.com/ponsdotdev/ponsfamily)
launchpad on Robinhood Chain.

It is a fork of [eonsystemspbc/fly-brain](https://github.com/eonsystemspbc/fly-brain),
the whole-brain leaky integrate-and-fire emulation of the adult *Drosophila*
built from the FlyWire connectome (~138k neurons). That emulation is still
here, unchanged, under `code/`, `data/` and `main.py`; its documentation moved
to [docs/FLY-BRAIN.md](docs/FLY-BRAIN.md). What this repository adds is a body
for the brain: the `fly/` package.

```
        connectome (FlyWire v783, LIF, 0.1 ms steps, CPU)
                 │  spikes → breadth, burstiness, ISI irregularity, persistence
                 ▼
   drives: curiosity · craft · humor · appetite · boldness · fatigue
                 │  + world pressure (hours since last build, unlaunched memes …)
                 ▼
     policy ──► browse │ build │ meme │ launch │ rest
                 │        │       │       │
              internet  workshop/  memes/  Pons V2 factory (dry-run by default)
```

## How the fly thinks

1. **Perceive.** Each tick the fly stimulates two named populations of the
   real connectome: the sugar-sensing gustatory neurons (200 Hz) and the P9
   forward-walking descending neurons (100 Hz), the same experiments the
   upstream benchmarks run. Activity propagates through ~15M synapses for
   100 ms of simulated time (about a second of wall time on a laptop).
2. **Feel.** Population statistics become drives (`fly/drives.py`): how far
   the sugar stimulus spread sets appetite, how far walking spread sets
   curiosity, spike-train irregularity sets humor, late-window persistence
   sets craft, population burstiness sets boldness. World pressure (time
   since the last build, notes never used, memes never launched) is mixed in.
3. **Decide.** A softmax over the drives, sampled with a seed derived from the
   spike fingerprint, picks one of browse / build / meme / launch / rest.
4. **Act.**
   * **browse** searches the web and the Hacker News front page, reads a few
     pages, and asks the mind (Claude) what need each page reveals.
   * **build** asks the mind for one small, complete piece of technology
     that flies or humans may need, writes it into `workshop/<slug>/`,
     byte-compiles it and runs its tests.
   * **meme** asks for a two-line caption and renders a procedurally drawn fly
     into `memes/`.
   * **launch** turns an unlaunched meme into a token concept, hosts the image
     (Pinata or GitHub), and prepares a `PonsV2LaunchFactory.launchToken`
     call. Without `FLY_LIVE_LAUNCH=1 … --live` this is a dry run that records
     the exact calldata.
5. **Remember.** Everything lands in `data/fly_memory.json` and feeds the next
   tick's context.

## Quickstart

```bash
pip install -r requirements-fly.txt
cp .env.example .env            # add ANTHROPIC_API_KEY and, later, wallet/hosting
python fly.py status
python fly.py brain             # stimulate the connectome, print drives
python fly.py tick              # one heartbeat, chosen by the brain
python fly.py tick --force build
python fly.py live --interval 1800
```

No API key? Set `FLY_MIND=offline` for a deterministic template mind. No
connectome data? `FLY_BRAIN=phantom` uses a small synthetic network. The
first connectome run builds `data/fly_connectome_cache.npz` (~50 MB) so later
loads take under a second.

## The website: flydev.tech

The fly designs and writes its own website. `python fly.py website` (or the
first tick, if `site/` is empty) hands the mind a brief: six clean routes
(`/`, `/browsing`, `/memes`, `/coins`, `/builds`, `/journal`, never `.html`
or `#` links), always dark, one shared `app.js` reading `/data/state.json`,
responsive to 400 px. The result is checked (routes present, links clean,
JavaScript parses), rendered headless in Chrome at desktop and phone widths,
and the screenshots are shown back to the fly so it can revise; a phone
overflow detector forces one more pass. If its site still fails, the
built-in template (`fly/site_template/`) is used so the page never breaks.

After every tick the fly exports `site/data/state.json` (`FLY_PUBLISH=site`,
the default) and, with `FLY_PUBLISH=git`, commits `site/` and `workshop/` and
pushes, so the host redeploys on its own.

```bash
python fly.py website          # the fly (re)designs its site
python fly.py serve            # watch locally at http://127.0.0.1:8642
python fly.py publish --push   # export + commit + push by hand
python fly.py sync             # pull updates without conflicts on state.json
```

Hosting the domain: `vercel.json` serves `site/` with clean URLs (import the
repo at vercel.com/new, add `flydev.tech` under Domains); or GitHub Pages via
`.github/workflows/pages.yml` (Settings → Pages → Source: GitHub Actions,
custom domain `flydev.tech`; the fly writes `site/CNAME` from
`FLY_SITE_DOMAIN`). Either redeploys whenever the fly pushes.

## X profile

`python fly.py brand` has the fly write a tagline and bio and draw its own
profile picture (500×500) and banner (1500×500) into `site/brand/`, so they
are also served at `/brand/pfp.png` and `/brand/banner.png`. The X account is
[@TheFlyDev_](https://x.com/TheFlyDev_).

## Launching on Pons

Pons V2 (`0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` on Robinhood Chain,
chain id 4663) mints a fixed-supply ERC-20 onto a bonding curve that later
graduates into a locked Uniswap V4 pool. A launch is one `launchToken` call
that pays the factory's `launchFee`. The fly's client (`fly/launchpad.py`)
carries a minimal ABI for that call, the read-only status functions and the
`TokenLaunched` event; verify it against the
[verified sources](https://github.com/ponsdotdev/ponsfamily) before trusting
it with money.

```bash
python fly.py wallet                     # address + balance of the launch wallet
python fly.py host-test                  # upload a test image to Pinata and verify it serves
python fly.py launch-status              # factory state + a readiness checklist
python fly.py tick --force launch        # dry run: concept + hosted logo + calldata
FLY_LIVE_LAUNCH=1 python fly.py tick --force launch --live   # real transaction
```

Image hosting through Pinata: create a free account, make an API key with
the Files "write" scope, copy its JWT into `PINATA_JWT`, and set
`PINATA_GATEWAY` to your dedicated gateway
(`https://<name>.mypinata.cloud/ipfs`). Uploads go through the v3 Files
API with a fallback to the legacy pinning endpoint.

When launches are armed and the fly has not launched its own coin yet, its
appetite drive is pinned high: the next tick is the genesis launch, done by
the fly, on camera if you like (`python fly.py live --live`).

The fly's first live launch is always its own coin, **The Fly Dev ($FLYDEV)**
(`FLY_GENESIS_NAME` / `FLY_GENESIS_SYMBOL`; leave the name empty to
disable). After that, every coin comes from a meme it drew. You can also
force a launch by hand:

```bash
python fly.py launch --name "The Fly Dev" --symbol FLYDEV            # dry run
python fly.py launch --name "The Fly Dev" --symbol FLYDEV --live     # send it
```

**Creator fees.** Pons charges a 1% curve fee (plus any creator tax you set)
and credits the creator's share to a claim-based fee escrow in ETH. The
genesis coin launches with buyback **off**, so every creator fee stays
claimable by the fly's wallet and funds the project. Later coins follow
`FLY_COIN_FEE_MODE`: `buyback` (default) lets Pons spend the creator slice
buying the coin back and locking it in the five-year vault; `wallet` keeps
fees claimable like the genesis coin. Collect with:

```bash
python fly.py fees                         # pending on each curve + claimable in escrow
python fly.py fees --sweep --claim --live  # push curve fees to escrow, claim to the wallet
```

Guard rails that cannot be turned off from the command line:

* a live launch needs `FLY_LIVE_LAUNCH=1` **and** `--live`, a wallet key, a
  reachable RPC, and a logo hosted at an `https://` or `ipfs://` URL;
* at most `FLY_MAX_LAUNCHES_PER_DAY` real launches (default 1);
* the factory fee must be at or below `FLY_MAX_LAUNCH_FEE_ETH`, any first buy
  at or below `FLY_MAX_INITIAL_BUY_ETH`;
* descriptions with financial promises are refused;
* there is no sell function. The fly creates; it does not dump.

Memecoins are jokes with a ticker. Use a dedicated hot wallet holding only what
you are willing to lose, and check the laws that apply to you.

## Layout

```
fly.py                  entrypoint
fly/
  brain.py              CPU LIF emulation of the connectome (NumPy/SciPy)
  neurons.py            named stimulus populations (sugar GRNs, P9)
  drives.py             spikes + world → drives → action
  mind.py               Claude (structured outputs) + offline template mind
  browser.py            search, Hacker News, page reading
  developer.py          workshop: write, compile and test generated projects
  memes.py              procedural fly meme renderer (Pillow)
  hosting.py            Pinata / GitHub image hosting for token logos
  launchpad.py          Pons V2 client, dry-run by default, guard rails
  memory.py             JSON journal
  agent.py              the tick loop
  cli.py                command line
workshop/               what the fly built
memes/                  what the fly drew
tests/                  pytest suite (runs offline, phantom brain)
code/ data/ main.py     upstream fly-brain benchmark suite (see docs/FLY-BRAIN.md)
```

## Safety notes

* Generated projects are executed locally (compile + their own tests). Run the
  fly in a container or VM.
* The mind runs on `claude-opus-5` with adaptive thinking and server-side
  refusal fallbacks enabled; set `FLY_MODEL` to change it.
* Nothing in this repository is financial advice.

## License

GPL-2.0-or-later, as upstream. See [LICENSE](LICENSE). The Shiu et al. Brian2
materials keep their MIT license; Pons contracts are referenced by address and
ABI only.
