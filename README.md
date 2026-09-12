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
   real connectome (and the home page replays the resulting spike raster,
   pushed within seconds through the fly cam and again in `state.json`): the sugar-sensing gustatory neurons (200 Hz) and the P9
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
     pages, screenshots each one with headless Chrome (stamped with time and
     URL, published under `/browsing/shots/`), asks the mind (Claude) what
     need each page reveals, and writes down what it learned.
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
6. **Rest.** After each action the fly decides how long to rest before its
   brain chooses again: a couple of minutes after browsing, a quarter hour
   after a build, longer as it tires (fatigue grows with the number of
   recent actions and caps the day at `FLY_MAX_ACTIONS_PER_DAY`). Pass
   `--interval` to `live` for a fixed timer instead.

Run it as a background service on macOS so it lives without a terminal:
`python fly.py daemon install --live` (logs in `data/fly-daemon.log`,
restarts at login and after crashes; `daemon status`, `daemon uninstall`).

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

## Keeping itself alive

A brain has to run itself. `python fly.py live` is a supervisor: the loop
runs in a child process and is brought back after any crash or self-update,
with backoff. Inside the loop:

- **Check-ups** before each action: network (waits with backoff while it is
  down), a corrupt memory file (restored from the automatic backup), a
  half-finished git rebase or merge (aborted), a conflicted `state.json`
  (regenerated), a full disk (old screenshots pruned).
- **Circuit breakers**: an action that fails three times in a row is
  suspended for two hours; the fly does something else meanwhile.
- **Watchdog**: a heartbeat file; if the loop stops beating for 45 minutes
  the process exits and the supervisor restarts it.
- **Self-update**: every six hours it pulls new commits from the repo,
  reinstalls requirements and restarts on the new code.
- **Self-repair drafts**: when a crash is in the fly's own code, the fly
  reads the traceback, drafts a patch, proves it against the test-suite in a
  scratch copy, and saves it under `data/self-repair/<stamp>/` with a diff
  and a diagnosis. It never edits its running code on its own:
  `python fly.py repairs` lists drafts, `python fly.py repairs apply <stamp>`
  applies one you have read. `python fly.py health` shows uptime, suspended
  actions and recent incidents with what the fly did about them; the site
  shows the same as "vitals".

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

## Posting on X

The fly posts as [@TheFlyDev_](https://x.com/TheFlyDev_): what it builds,
the memes it draws (with the image), its launches, one line from each
browsing session, and unprompted $FLYDEV posts on a cadence
(`FLY_X_HYPE_EVERY_HOURS`). It is allowed to be as bullish as it likes about
its own coin and itself, and only its own coin. A guard holds any post with
a promise word, a price target or a multiple, and it never posts more than
`FLY_X_MAX_POSTS_PER_DAY`.

It learns: every few hours it pulls `public_metrics` for its live posts,
scores them, and asks the mind for a playbook (what works, what flops, what
to try next) that shapes every later post. `python fly.py x-status` shows
the recent posts, scores and current bets.

Credentials go in `.env` (`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`,
`X_ACCESS_SECRET`, from an X developer app with read+write on the account).
Posts are drafts until `FLY_X_POST=1` and `--live`.

```bash
python fly.py post --kind hype           # draft one post
python fly.py post --kind meme --live    # send the latest meme
python fly.py live --live                # everything real: launches and posts
```

## Ask the fly (chat) and X replies

**flydev.tech/ask** is a chat with the fly. Two Vercel serverless functions in
`api/` do the work: `api/ask.js` answers as the fly (persona + everything in
the published `state.json`, coloured by its current mood) and `api/burn.js`
verifies $FLYDEV burns on Robinhood Chain. Each visitor gets
`FLY_FREE_TURNS` (5) questions a day, tracked in a signed cookie; after that
they burn `FLY_BURN_AMOUNT` (5,000) $FLYDEV for `FLY_BURN_TURNS` (10) more,
from the page with a wallet or by pasting a burn transaction hash. The burn
is checked on chain (a `Transfer` to the zero address from the genesis token
contract, which the function reads from `state.json`, so nothing needs
editing after launch). Per-instance brakes cap questions per address and per
day; set Upstash Redis (`UPSTASH_REDIS_REST_URL/TOKEN`) for durable replay
protection of burn hashes.

Vercel environment variables for this (the only secrets that live off your
Mac): `ANTHROPIC_API_KEY`, `FLY_CHAT_SECRET` (any long random string), and
optionally `FLY_CHAT_MODEL`, `FLY_RPC_URL`, `FLY_FREE_TURNS`,
`FLY_BURN_AMOUNT`, `FLY_BURN_TURNS`, `FLY_DAILY_TURN_BUDGET`.

**Fly cam.** While it browses, the fly posts frames of the page it is on
(panning down the page a few seconds apart) to `api/cam.js`, which keeps the
newest few in Vercel Blob; `/browsing` polls every 3 seconds and shows a LIVE
panel, or "last seen" when idle. Setup: add a Blob store to the Vercel
project (Storage tab; it injects `BLOB_READ_WRITE_TOKEN`), pick a random
`FLY_CAM_SECRET` and set it both on Vercel and in `.env`, then
`python fly.py cam-test`.

**X replies.** While resting the fly checks its mentions every few minutes
(`FLY_X_MENTIONS_EVERY_SEC`, default 180) and answers real people in
character (`FLY_X_MAX_REPLIES_PER_DAY`, default 30; at most
`FLY_X_MAX_REPLIES_PER_ACCOUNT_PER_DAY`, default 2, per account). Promo spam
and bot outreach ("DM me", "follow back", "attractive proposal", marketing
and listing pitches, emoji-only hype) is recognised by a filter and, past
that, by the mind itself, and gets no reply. Ignored mentions are remembered
so they are not re-judged and never appear on the site. Own posts are capped
by `FLY_X_MAX_POSTS_PER_DAY` (default 12; replies do not count). Drafts until
posting is armed. `python fly.py replies --live` runs it by hand.

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
