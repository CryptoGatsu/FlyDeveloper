import json

import pytest

from ripeness import model
from ripeness.cli import bar, describe_temp, main


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


# --- the clock, run backwards -------------------------------------------


def test_plan_solves_for_a_holding_temperature():
    p = model.plan("banana", 0.0, 5.0)          # 55 dd over 5 days = 11/day
    assert p["status"] == "ok"
    assert p["temp_c"] == pytest.approx(15.0)
    assert p["stage"] == "ripe"


def test_plan_round_trips_through_the_forward_model():
    p = model.plan("avocado", 32.0, 4.0)
    eta = model.days_until("avocado", 32.0, p["temp_c"], "ripe")
    assert eta == pytest.approx(4.0, abs=0.05)


def test_plan_honours_the_target_stage():
    p = model.plan("banana", 40.0, 2.0, "fly-feast")   # (90-40)/2 = 25/day
    assert p["temp_c"] == pytest.approx(29.0)


def test_plan_says_too_late_instead_of_lying():
    p = model.plan("banana", 0.0, 1.0)
    assert p["status"] == "too-late"
    assert p["temp_c"] is None
    assert p["earliest_days"] == pytest.approx(55.0 / 31.0, abs=0.01)


def test_plan_notices_it_already_happened():
    p = model.plan("banana", 200.0, 3.0)
    assert p["status"] == "passed"
    assert p["temp_c"] is None


def test_plan_rejects_nonsense():
    with pytest.raises(ValueError):
        model.plan("banana", 0.0, 0.0)
    with pytest.raises(ValueError):
        model.plan("banana", 0.0, 3.0, "firm")
    with pytest.raises(model.UnknownFruit):
        model.plan("moon rock", 0.0, 3.0)


def test_describe_temp_covers_the_kitchen():
    assert describe_temp(4.0) == "the fridge"
    assert "cool room" in describe_temp(15.0)
    assert "paper bag" in describe_temp(33.0)


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


def test_cli_ready_in_plans_a_temperature(capsys):
    assert main(["banana", "--ready-in", "5", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert data["temp_c"] == pytest.approx(15.0)


def test_cli_ready_in_counts_the_soak_so_far(capsys):
    assert main(["banana", "--days", "2", "--temp", "24",
                 "--ready-in", "2", "--stage", "fly-feast", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["degree_days"] == pytest.approx(40.0)
    assert data["temp_c"] == pytest.approx(29.0)


def test_cli_ready_in_human_output(capsys):
    assert main(["avocado", "--days", "2", "--temp", "20", "--ready-in", "4"]) == 0
    out = capsys.readouterr().out
    assert "hold it at" in out
    assert "want ripe in 4 days" in out


def test_cli_ready_in_rejects_zero_days(capsys):
    assert main(["banana", "--ready-in", "0"]) == 2
    assert "positive" in capsys.readouterr().err


def test_cli_list_and_errors(capsys):
    assert main(["--list"]) == 0
    assert "banana" in capsys.readouterr().out
    assert main(["moon rock"]) == 2
    assert "unknown fruit" in capsys.readouterr().err
    assert main(["moon rock", "--ready-in", "3"]) == 2
    assert "unknown fruit" in capsys.readouterr().err
    assert main([]) == 2
