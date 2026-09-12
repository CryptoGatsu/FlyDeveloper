import json
import time

from fly.health import Health


def test_breaker_trips_after_three_failures(tmp_path):
    h = Health(tmp_path, log=lambda m: None)
    assert h.allowed("build")
    assert not h.failed("build", "boom") and not h.failed("build", "boom")
    assert h.failed("build", "boom") is True
    assert not h.allowed("build") and "build" in h.suspended()
    h.state.breakers["build"].open_until = time.time() - 1
    assert h.allowed("build")
    h.succeeded("build")
    assert h.state.breakers["build"].failures == 0


def test_memory_backup_and_restore(tmp_path):
    (tmp_path / "data").mkdir()
    mem = tmp_path / "data" / "fly_memory.json"
    mem.write_text(json.dumps({"journal": []}))
    h = Health(tmp_path, log=lambda m: None)
    assert h.check_memory() == []
    assert (tmp_path / "data" / "fly_memory.bak.json").is_file()
    mem.write_text("{corrupt")
    notes = h.check_memory()
    assert any("restored" in n for n in notes)
    assert json.loads(mem.read_text()) == {"journal": []}


def test_health_persists_incidents_and_restarts(tmp_path):
    h1 = Health(tmp_path, log=lambda m: None)
    h1.incident("test", "something", fixed="nothing")
    h2 = Health(tmp_path, log=lambda m: None)
    assert h2.state.restarts == 2 and h2.state.incidents[-1]["kind"] == "test"
    assert h2.summary()["restarts"] == 2
