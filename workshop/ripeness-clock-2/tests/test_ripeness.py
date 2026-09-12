import json

import pytest

from ripeness import model
from ripeness.cli import bar, main


def test_daily_rate_stalls_at_or_below_base():
    assert model.daily_rate(4.0) == 0.0
    assert model.daily_rate(-3.0) == 0.0


def test_daily_rate_is_linear_then_capped():
    assert model.daily_rate(22.0) == pytest.approx(18.0)
    assert model.daily_rate(40.0) == pytest.approx(model.CAP_C - model.BASE_C)


def test_accumulate_sums_a_history():
    assert model.accumulate([24.0, 24.0, 4.0]) == pytest.approx(40.0)
    assert model.accumulate([]) == 0.0


def test_stage_boundaries_are_inclusive_of_next_stage():
    ripe, feast, compost = model.thresholds("banana")
    assert model.stage_of("banana", ripe - 0.1) == "firm"
    assert model.stage_of("banana", ripe) == "ripe"
    assert model.stage_of("banana", feast) == "fly-feast"
    assert model.stage_of("banana", compost) == "compost"
    assert model.stage_of("BANANA", compost + 999) == "compost"


def test_stages_advance_monotonically_over_time():
    seen = []
    for day in range(0, 12):
        dd = model.daily_rate(24.0) * day
        seen.append(model.STAGES.index(model.stage_of("banana", dd)))
    assert seen == sorted(seen)
    assert seen[0] == 0 and seen[-1] == 3


def test_days_until_matches_the_rate():
    ripe, _, _ = model.thresholds("tomato")
    eta = model.days_until("tomato", 0.0, 24.0, "ripe")
    assert eta == pytest.approx(ripe / 20.0)
    assert model.days_until("tomato", ripe + 5, 24.0, "ripe") == 0.0


def test_fridge_means_never():
    assert model.days_until("avocado", 0.0, model.BASE_C, "ripe") is None
    assert model.days_until("avocado", 0.0, -10.0, "compost") is None


def test_bad_inputs_raise():
    with pytest.raises(model.UnknownFruit):
        model.thresholds("moon rock")
    with pytest.raises(ValueError):
        model.days_until("banana", 0.0, 20.0, "firm")


def test_forecast_shape():
    rep = model.forecast("Peach", 50.0, 20.0)
    assert rep["fruit"] == "peach"
    assert rep["stage"] == "ripe"
    assert set(rep["eta_days"]) == set(model.FUTURE_STAGES)


def test_bar_fills_and_clamps():
    assert bar(0.0, 100.0, width=4) == "░" * 4
    assert bar(500.0, 100.0, width=4) == "▓" * 4
    assert len(bar(50.0, 100.0, width=8)) == 8


def test_cli_human_output(capsys):
    assert main(["banana", "--days", "3", "--temp", "24"]) == 0
    out = capsys.readouterr().out
    assert "banana at 24.0" in out
    assert "fly-feast" in out


def test_cli_json_output(capsys):
    assert main(["mango", "--days", "2", "--temp", "30", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["fruit"] == "mango"
    assert data["degree_days"] == pytest.approx(52.0)


def test_cli_temps_history_uses_last_temp_ahead(capsys):
    assert main(["tomato", "--temps", "26,26,19,8", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["temp_c"] == pytest.approx(8.0)
    assert data["degree_days"] == pytest.approx(63.0)


def test_cli_fridge_stops_the_clock(capsys):
    assert main(["avocado", "--days", "5", "--temp", "22", "--fridge", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["eta_days"]["compost"] is None


def test_cli_list_and_errors(capsys):
    assert main(["--list"]) == 0
    assert "banana" in capsys.readouterr().out
    assert main(["moon rock"]) == 2
    assert "unknown fruit" in capsys.readouterr().err
    assert main([]) == 2
