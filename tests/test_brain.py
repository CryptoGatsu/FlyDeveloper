import numpy as np

from fly.brain import Connectome, FlyBrain, MODEL_PARAMS


def test_synthetic_connectome_shape():
    c = Connectome.synthetic(500, seed=1)
    assert c.n_neurons == 500
    assert c.n_synapses > 0
    assert c.calibration["sugar_mid"] > 0


def test_stimulated_neurons_fire_and_propagate():
    c = Connectome.synthetic(1500, seed=3)
    b = FlyBrain(c)
    r = b.run("sugar", np.arange(20), 200.0, t_run_sec=0.05, seed=11)
    assert r.total_spikes > 0
    assert r.active_neurons >= 20
    assert r.downstream_active >= 1
    assert 0.0 <= r.breadth <= 1.0
    assert r.stats["n_steps"] == 500


def test_no_stimulus_is_silent():
    c = Connectome.synthetic(800, seed=2)
    b = FlyBrain(c)
    r = b.run("none", [], 0.0, t_run_sec=0.02, seed=1)
    assert r.total_spikes == 0
    assert r.burstiness == 0.0


def test_same_seed_same_fingerprint():
    c = Connectome.synthetic(800, seed=2)
    b = FlyBrain(c)
    r1 = b.run("sugar", np.arange(10), 150.0, 0.03, seed=5)
    r2 = b.run("sugar", np.arange(10), 150.0, 0.03, seed=5)
    assert r1.fingerprint() == r2.fingerprint()


def test_silencing_removes_downstream_activity():
    c = Connectome.synthetic(1200, seed=4)
    b = FlyBrain(c)
    exc = np.arange(15)
    r = b.run("sugar", exc, 200.0, 0.05, seed=9)
    downstream = np.nonzero(r.spike_counts > 0)[0]
    downstream = [i for i in downstream if i not in set(exc.tolist())]
    silenced = b.run("sugar", exc, 200.0, 0.05, seed=9, silence_indices=downstream)
    assert silenced.downstream_active <= r.downstream_active


def test_params_match_upstream_pytorch_defaults():
    assert MODEL_PARAMS["vThreshold"] == -45.0
    assert MODEL_PARAMS["tauMem"] == 20.0
    assert MODEL_PARAMS["wScale"] == 0.275


def test_npz_roundtrip(tmp_path):
    c = Connectome.synthetic(300, seed=1)
    c.save_npz(tmp_path / "c.npz")
    d = Connectome.load_npz(tmp_path / "c.npz")
    assert d.n_neurons == 300
    assert d.n_synapses == c.n_synapses
    assert d.index_of([c.flywire_ids[5]]).tolist() == [5]


def test_events_and_raster():
    c = Connectome.synthetic(1200, seed=3)
    b = FlyBrain(c)
    r = b.run("sugar", np.arange(20), 200.0, t_run_sec=0.05, seed=11)
    assert r.events and all(len(e) == 2 for e in r.events)
    ras = r.raster(max_neurons=50, max_events=500)
    assert ras["n_rows"] <= 50 and ras["n_stimulated"] <= 20
    assert all(0 <= s[0] < ras["n_rows"] and 0 <= s[1] <= 50 for s in ras["spikes"])
    assert len(ras["pop_rate_ms"]) == 50
