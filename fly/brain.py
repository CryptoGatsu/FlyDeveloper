"""CPU emulation of the Drosophila connectome used as the fly's temperament.

This is the same leaky integrate-and-fire model with alpha synapses that the
upstream benchmark runners implement (parameters from Shiu et al., matching
`code/run_pytorch.py`), written against NumPy + SciPy so it runs on any
laptop: the full FlyWire v783 connectome (~138k neurons, ~5M synapses) at a
0.1 ms timestep costs a few seconds per 100 ms of simulated time.

The fly does not use the simulation to compute anything symbolic. It
stimulates named sensory populations (see `fly/neurons.py`), lets activity
propagate through the real wiring, and reads population statistics off the
spike trains. Those statistics become drives (see `fly/drives.py`).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import scipy.sparse as sp

# Identical to MODEL_PARAMS in code/run_pytorch.py (Brian2 default_params).
MODEL_PARAMS = {
    "tauSyn": 5.0,        # ms
    "tDelay": 1.8,        # ms
    "v0": -52.0,          # mV
    "vReset": -52.0,      # mV
    "vRest": -52.0,       # mV
    "vThreshold": -45.0,  # mV
    "tauMem": 20.0,       # ms
    "tRefrac": 2.2,       # ms
    "scalePoisson": 250,
    "wScale": 0.275,
}
DT_MS = 0.1
MAX_EVENTS = 6000


@dataclass
class Connectome:
    """Sparse pre->post weight matrix plus FlyWire ID lookups."""

    weights_pre_post: sp.csr_matrix   # shape (N, N), row = presynaptic
    flywire_ids: np.ndarray           # int64, length N
    source: str = "unknown"

    @property
    def calibration(self) -> dict[str, float]:
        """Midpoints/widths for turning breadth statistics into drives.

        The synthetic network is far smaller and denser than the real
        connectome, so a stimulus recruits a much larger fraction of it.
        """
        if self.source.startswith("synthetic"):
            return {"sugar_mid": 0.02, "sugar_w": 0.008, "walk_mid": 0.001, "walk_w": 0.0005}
        return {"sugar_mid": 0.002, "sugar_w": 0.0008, "walk_mid": 0.0002, "walk_w": 0.0001}

    @property
    def n_neurons(self) -> int:
        return int(self.weights_pre_post.shape[0])

    @property
    def n_synapses(self) -> int:
        return int(self.weights_pre_post.nnz)

    def index_of(self, flywire_ids) -> np.ndarray:
        lookup = {int(fid): i for i, fid in enumerate(self.flywire_ids.tolist())}
        idx = [lookup[int(f)] for f in flywire_ids if int(f) in lookup]
        return np.asarray(idx, dtype=np.int64)

    # -- constructors ------------------------------------------------------
    @classmethod
    def from_flywire(
        cls, completeness_csv: Path, connectivity_parquet: Path, cache_npz: Path | None = None
    ) -> "Connectome":
        if cache_npz and cache_npz.is_file():
            try:
                return cls.load_npz(cache_npz)
            except Exception:
                pass
        import pandas as pd

        comp = pd.read_csv(completeness_csv, index_col=0)
        con = pd.read_parquet(connectivity_parquet)
        n = len(comp)
        pre = con["Presynaptic_Index"].to_numpy(dtype=np.int64)
        post = con["Postsynaptic_Index"].to_numpy(dtype=np.int64)
        w = con["Excitatory x Connectivity"].to_numpy(dtype=np.float32)
        mat = sp.csr_matrix((w, (pre, post)), shape=(n, n), dtype=np.float32)
        mat.sum_duplicates()
        c = cls(mat, comp.index.to_numpy(dtype=np.int64), source=f"flywire:{completeness_csv.name}")
        if cache_npz:
            try:
                c.save_npz(cache_npz)
            except OSError:
                pass
        return c

    @classmethod
    def synthetic(cls, n_neurons: int = 3000, seed: int = 7, k_out: int = 40) -> "Connectome":
        """A random sparse network with fly-like statistics (mostly excitatory,
        ~15% inhibitory presynaptic neurons, log-normal synapse counts)."""
        rng = np.random.default_rng(seed)
        inhibitory = rng.random(n_neurons) < 0.15
        pre = np.repeat(np.arange(n_neurons), k_out)
        post = rng.integers(0, n_neurons, size=pre.size)
        counts = np.clip(rng.lognormal(mean=1.6, sigma=1.0, size=pre.size), 1, 80)
        sign = np.where(inhibitory[pre], -1.0, 1.0)
        w = (counts * sign).astype(np.float32)
        keep = pre != post
        mat = sp.csr_matrix((w[keep], (pre[keep], post[keep])), shape=(n_neurons, n_neurons))
        mat.sum_duplicates()
        ids = 720575940000000000 + np.arange(n_neurons, dtype=np.int64)
        return cls(mat, ids, source=f"synthetic:{n_neurons}")

    def save_npz(self, path: Path) -> None:
        m = self.weights_pre_post
        np.savez_compressed(
            path, data=m.data, indices=m.indices, indptr=m.indptr,
            shape=np.asarray(m.shape), flywire_ids=self.flywire_ids,
        )

    @classmethod
    def load_npz(cls, path: Path) -> "Connectome":
        z = np.load(path)
        shape = tuple(int(x) for x in z["shape"])
        m = sp.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=shape)
        return cls(m, z["flywire_ids"], source=f"cache:{path.name}")


@dataclass
class SpikeReport:
    """Population readout from one stimulation run."""

    stimulus: str
    t_run_sec: float
    n_neurons: int
    stimulated: np.ndarray
    spike_counts: np.ndarray           # spikes per neuron
    pop_rate_ms: np.ndarray            # population spikes per 1 ms bin
    isi_cv: float                      # mean coefficient of variation of ISIs
    wall_time_sec: float
    seed: int
    stats: dict = field(default_factory=dict)
    events: list = field(default_factory=list)   # (t_ms, neuron_index) for up to MAX_EVENTS spikes

    @property
    def total_spikes(self) -> int:
        return int(self.spike_counts.sum())

    @property
    def active_neurons(self) -> int:
        return int((self.spike_counts > 0).sum())

    @property
    def downstream_active(self) -> int:
        mask = self.spike_counts > 0
        mask[self.stimulated] = False
        return int(mask.sum())

    @property
    def breadth(self) -> float:
        """Fraction of the non-stimulated brain that fired at least once."""
        denom = max(1, self.n_neurons - len(self.stimulated))
        return self.downstream_active / denom

    @property
    def mean_rate_hz(self) -> float:
        active = self.spike_counts[self.spike_counts > 0]
        if active.size == 0:
            return 0.0
        return float(active.mean() / self.t_run_sec)

    @property
    def burstiness(self) -> float:
        """CV of the population rate over time: 0 = steady, >1 = bursty."""
        r = self.pop_rate_ms
        if r.size < 2 or r.mean() <= 0:
            return 0.0
        return float(r.std() / r.mean())

    @property
    def persistence(self) -> float:
        """Late-window activity divided by early-window activity."""
        r = self.pop_rate_ms
        if r.size < 4:
            return 0.0
        half = r.size // 2
        early, late = r[:half].sum(), r[half:].sum()
        if early <= 0:
            return 0.0
        return float(late / early)

    def raster(self, max_neurons: int = 160, max_events: int = 2500) -> dict:
        """Compact spike raster for the website: the most active neurons as
        rows (stimulated ones first), spikes as (row, t_ms) pairs, plus the
        population rate per millisecond."""
        counts = self.spike_counts
        stim = [int(i) for i in self.stimulated.tolist() if counts[i] > 0]
        others = [int(i) for i in np.argsort(-counts) if counts[i] > 0 and int(i) not in set(stim)]
        rows = (stim + others)[:max_neurons]
        index = {n: r for r, n in enumerate(rows)}
        spikes = [[index[n], t] for t, n in self.events if n in index][:max_events]
        return {
            "stimulus": self.stimulus, "t_run_ms": int(self.t_run_sec * 1000), "n_rows": len(rows),
            "n_stimulated": len(stim), "total_spikes": self.total_spikes, "active_neurons": self.active_neurons,
            "flywire_ids": [int(self.stats.get("flywire_ids", {}).get(n, 0)) for n in rows] if self.stats.get("flywire_ids") else [],
            "spikes": spikes, "pop_rate_ms": [int(x) for x in self.pop_rate_ms.tolist()],
        }

    def fingerprint(self) -> str:
        h = hashlib.sha256(self.spike_counts.tobytes()).hexdigest()
        return h[:16]

    def describe(self) -> str:
        return (
            f"{self.stimulus}: {self.total_spikes} spikes, {self.active_neurons} active "
            f"({self.downstream_active} downstream, breadth {self.breadth:.4f}), "
            f"mean {self.mean_rate_hz:.1f} Hz, ISI-CV {self.isi_cv:.2f}, "
            f"burstiness {self.burstiness:.2f}, persistence {self.persistence:.2f}, "
            f"{self.wall_time_sec:.1f}s wall"
        )


class FlyBrain:
    """Leaky integrate-and-fire network over a `Connectome`."""

    def __init__(self, connectome: Connectome, params: dict | None = None, dt_ms: float = DT_MS):
        self.connectome = connectome
        self.params = dict(MODEL_PARAMS, **(params or {}))
        self.dt = dt_ms
        self.W = connectome.weights_pre_post.tocsr()

    @property
    def n_neurons(self) -> int:
        return self.connectome.n_neurons

    def run(
        self,
        stimulus: str,
        exc_indices,
        rate_hz: float,
        t_run_sec: float = 0.1,
        seed: int | None = None,
        silence_indices=(),
    ) -> SpikeReport:
        p = self.params
        dt = self.dt
        n = self.n_neurons
        exc = np.asarray(list(exc_indices), dtype=np.int64)
        silence = np.asarray(list(silence_indices), dtype=np.int64)
        if seed is None:
            seed = int(time.time_ns() % (2**31 - 1))
        rng = np.random.default_rng(seed)

        W = self.W
        if silence.size:
            W = W.tolil()
            W[silence, :] = 0
            W[:, silence] = 0
            W = W.tocsr()

        n_steps = int(round(t_run_sec * 1000.0 / dt))
        steps_delay = int(round(p["tDelay"] / dt))
        base_refrac = int(round(p["tRefrac"] / dt))
        refrac_steps = np.full(n, base_refrac, dtype=np.int32)
        refrac_steps[exc] = 0                      # Poisson-driven neurons never rest
        syn_decay = 1.0 - dt / p["tauSyn"]
        mem_factor = dt / p["tauMem"]
        v_rest, v_th, v_reset = p["vRest"], p["vThreshold"], p["vReset"]
        w_scale = p["wScale"]
        poisson_kick = p["scalePoisson"] * w_scale       # mV per Poisson event
        p_spike = rate_hz * dt / 1000.0

        v = np.full(n, p["v0"], dtype=np.float32)
        g = np.zeros(n, dtype=np.float32)
        since_spike = np.full(n, 10**6, dtype=np.int32)  # steps since last spike
        delay_ring: list[np.ndarray] = [np.zeros(0, dtype=np.int64) for _ in range(steps_delay + 1)]
        spike_counts = np.zeros(n, dtype=np.int64)
        bins_per_ms = max(1, int(round(1.0 / dt)))
        pop_rate = np.zeros(max(1, n_steps // bins_per_ms), dtype=np.int64)
        events: list[tuple[float, int]] = []
        last_spike_t = np.full(n, -1.0, dtype=np.float64)
        isi_sum = np.zeros(n, dtype=np.float64)
        isi_sq = np.zeros(n, dtype=np.float64)
        isi_n = np.zeros(n, dtype=np.int64)

        t0 = time.perf_counter()
        for step in range(n_steps):
            # Recurrent input from spikes emitted `steps_delay` steps ago.
            arriving = delay_ring[step % (steps_delay + 1)]
            if arriving.size:
                inc = np.asarray(W[arriving].sum(axis=0)).ravel().astype(np.float32) * w_scale
                not_refrac = since_spike >= refrac_steps
                g += np.where(not_refrac, inc, 0.0)
            g *= syn_decay

            # External Poisson drive into membrane voltage (stimulated set only).
            if exc.size and p_spike > 0:
                kicks = rng.random(exc.size) < p_spike
                if kicks.any():
                    v[exc[kicks]] += poisson_kick

            # Membrane update for non-refractory neurons.
            not_refrac = since_spike >= refrac_steps
            v += np.where(not_refrac, mem_factor * (g - (v - v_rest)), 0.0)

            spiking = np.nonzero(v > v_th)[0]
            since_spike += 1
            if spiking.size:
                v[spiking] = v_reset
                g[spiking] = 0.0
                since_spike[spiking] = 0
                spike_counts[spiking] += 1
                pop_rate[min(step // bins_per_ms, pop_rate.size - 1)] += spiking.size
                t_ms = step * dt
                if len(events) < MAX_EVENTS:
                    events.extend((round(t_ms, 1), int(i)) for i in spiking[: MAX_EVENTS - len(events)])
                prev = last_spike_t[spiking]
                had = prev >= 0
                if had.any():
                    isi = t_ms - prev[had]
                    idx = spiking[had]
                    isi_sum[idx] += isi
                    isi_sq[idx] += isi * isi
                    isi_n[idx] += 1
                last_spike_t[spiking] = t_ms
            delay_ring[step % (steps_delay + 1)] = spiking

        wall = time.perf_counter() - t0
        ok = isi_n >= 2
        if ok.any():
            mean = isi_sum[ok] / isi_n[ok]
            var = np.maximum(isi_sq[ok] / isi_n[ok] - mean**2, 0.0)
            isi_cv = float(np.mean(np.sqrt(var) / np.maximum(mean, 1e-9)))
        else:
            isi_cv = 0.0

        return SpikeReport(
            stimulus=stimulus,
            t_run_sec=t_run_sec,
            n_neurons=n,
            stimulated=exc,
            spike_counts=spike_counts,
            pop_rate_ms=pop_rate,
            isi_cv=isi_cv,
            wall_time_sec=wall,
            seed=seed,
            stats={"n_steps": n_steps, "rate_hz": rate_hz, "source": self.connectome.source},
            events=events,
        )


def build_brain(cfg) -> FlyBrain:
    """Construct a brain from a `BrainConfig` (connectome or phantom)."""
    if cfg.mode == "connectome":
        conn = Connectome.from_flywire(cfg.completeness_csv, cfg.connectivity_parquet, cfg.cache_npz)
    else:
        conn = Connectome.synthetic(cfg.phantom_neurons, seed=cfg.seed if cfg.seed is not None else 7)
    return FlyBrain(conn)
