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


# --- chill lines: cold is not a pause button for everything -------------


def test_chill_floor_defaults_and_overrides():
    assert model.chill_floor("banana") == 13.0
    assert model.chill_floor(" Mango ") == 12.0
    assert model.chill_floor("Apple") == model.BASE_C
    assert model.chill_floor("strawberry") == model.BASE_C
    with pytest.raises(model.UnknownFruit):
        model.chill_floor("moon rock")


def test_forecast_flags_chilling_injury_only_while_firm():
    firm = model.forecast("banana", 0.0, model.BASE_C)
    assert firm["chill_safe_c"] == 13.0
    assert firm["chill_risk"] is True

    ripe = model.forecast("banana", 60.0, model.BASE_C)
    assert ripe["chill_risk"] is False  # cold after ripening is only cosmetic


def test_forecast_does_not_cry_chill_for_fridge_safe_fruit():
    rep = model.forecast("strawberry", 0.0, model.BASE_C)
    assert rep["chill_safe_c"] == model.BASE_C
    assert rep["chill_risk"] is False


def test_forecast_warm_enough_is_never_a_chill_risk():
    assert model.forecast("banana", 0.0, 21.0)["chill_risk"] is False


# --- cold that already happened -----------------------------------------


def test_chill_exposure_counts_cold_days_while_firm():
    # two warm days, three in the fridge, one more warm: still firm throughout
    assert model.chill_exposure("banana", [22, 22, 4, 4, 4, 22]) == 3.0


def test_chill_exposure_ignores_cold_after_ripening():
    # 55 dd banana: three days at 24C makes it ripe, then cold is cosmetic
    assert model.chill_exposure("banana", [24, 24, 24, 4, 4]) == 0.0


def test_chill_exposure_ignores_cold_that_is_not_cold_enough():
    assert model.chill_exposure("banana", [14, 14, 14]) == 0.0
    assert model.chill_exposure("avocado", [9, 9]) == 0.0  # 7C line


def test_chill_exposure_is_zero_for_fridge_safe_fruit():
    assert model.chill_exposure("strawberry", [4, 4, 4]) == 0.0
    assert model.chill_exposure("apple", [0, 0]) == 0.0


def test_chill_exposure_handles_empty_history_and_bad_fruit():
    assert model.chill_exposure("banana", []) == 0.0
    with pytest.raises(model.UnknownFruit):
        model.chill_exposure("moon rock", [4])


def test_forecast_carries_history_damage():
    rep = model.forecast("banana", 54.0, 22.0, chilled_days=3.0)
    assert rep["chilled_days"] == 3.0
    assert rep["chill_injury"] is True
    assert rep["chill_risk"] is False  # the temperature ahead is fine


def test_forecast_defaults_to_no_history_damage():
    rep = model.forecast("banana", 20.0, 22.0)
    assert rep["chilled_days"] == 0.0
    assert rep["chill_injury"] is False


# --- cold that already happened, as one steady stint ---------------------


def test_chill_exposure_steady_counts_a_fridge_stint():
    assert model.chill_exposure_steady("banana", 3.0, 4.0) == 3.0
    assert model.chill_exposure_steady("banana", 0.5, 0.0) == 0.5


def test_chill_exposure_steady_is_quiet_when_warm_enough():
    assert model.chill_exposure_steady("banana", 3.0, 21.0) == 0.0
    assert model.chill_exposure_steady("banana", 3.0, 13.0) == 0.0


def test_chill_exposure_steady_stops_counting_once_it_ripens():
    # 10C banana banks 6 dd/day; it hits 55 dd (ripe) after 9.17 days, and
    # cold after that is only cosmetic.
    assert model.chill_exposure_steady("banana", 12.0, 10.0) == pytest.approx(
        55.0 / 6.0, abs=0.01)
    assert model.chill_exposure_steady("banana", 5.0, 10.0) == 5.0


def test_chill_exposure_steady_ignores_fruit_that_is_already_ripe():
    assert model.chill_exposure_steady("banana", 4.0, 4.0, degree_days=60.0) == 0.0


def test_chill_exposure_steady_edges():
    assert model.chill_exposure_steady("strawberry", 5.0, 1.0) == 0.0
    assert model.chill_exposure_steady("banana", 0.0, 4.0) == 0.0
    assert model.chill_exposure_steady("banana", -3.0, 4.0) == 0.0
    with pytest.raises(model.UnknownFruit):
        model.chill_exposure_steady("moon rock", 3.0, 4.0)


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
    assert p["counter_days"] is None
    assert p["earliest_days"] == pytest.approx(55.0 / 31.0, abs=0.01)


def test_plan_notices_it_already_happened():
    p = model.plan("banana", 200.0, 3.0)
    assert p["status"] == "passed"
    assert p["temp_c"] is None
    assert p["counter_days"] is None


def test_plan_rejects_nonsense():
    with pytest.raises(ValueError):
        model.plan("banana", 0.0, 0.0)
    with pytest.raises(ValueError):
        model.plan("banana", 0.0, 3.0, "firm")
    with pytest.raises(model.UnknownFruit):
        model.plan("moon rock", 0.0, 3.0)


def test_plan_flags_a_hold_below_the_chill_line():
    p = model.plan("banana", 0.0, 8.0)     # 55/8 = 6.9/day -> 10.9C
    assert p["status"] == "ok"
    assert p["temp_c"] < p["chill_safe_c"]
    assert p["chill_risk"] is True
    # ...and the safe way out is still offered
    assert p["counter_days"] is not None


def test_plan_is_quiet_when_the_hold_is_warm_enough():
    p = model.plan("banana", 0.0, 5.0)     # 15C, above the 13C line
    assert p["chill_risk"] is False
    p2 = model.plan("apple", 0.0, 20.0)    # 6C hold, but apples don't mind
    assert p2["chill_risk"] is False


def test_plan_carries_chill_fields_in_every_status():
    assert model.plan("banana", 200.0, 3.0)["chill_risk"] is False
    assert model.plan("banana", 0.0, 1.0)["chill_safe_c"] == 13.0


def test_plan_reports_where_the_fruit_is_now():
    assert model.plan("banana", 0.0, 5.0)["current_stage"] == "firm"
    assert model.plan("banana", 68.0, 5.0, "fly-feast")["current_stage"] == "ripe"
    assert model.plan("banana", 200.0, 3.0)["current_stage"] == "compost"
    assert model.plan("banana", 0.0, 1.0)["current_stage"] == "firm"


def test_plan_does_not_cry_chill_once_the_fruit_is_ripe():
    # 68 dd banana is already ripe; coasting it to fly-feast over 6 days needs
    # a 7.7C hold, under the 13C line -- but chilling injury needs firm fruit.
    p = model.plan("banana", 68.0, 6.0, "fly-feast")
    assert p["status"] == "ok"
    assert p["temp_c"] < p["chill_safe_c"]
    assert p["current_stage"] == "ripe"
    assert p["chill_risk"] is False


def test_plan_still_cries_chill_for_firm_fruit_aimed_past_ripe():
    p = model.plan("banana", 0.0, 20.0, "fly-feast")
    assert p["current_stage"] == "firm"
    assert p["temp_c"] < p["chill_safe_c"]
    assert p["chill_risk"] is True


# --- counter, then fridge -----------------------------------------------


def test_plan_offers_a_counter_then_fridge_split():
    p = model.plan("banana", 0.0, 5.0, counter_c=21.0)  # 55/17 = 3.24 days out
    assert p["counter_c"] == pytest.approx(21.0)
    assert p["counter_days"] == pytest.approx(3.2, abs=0.05)
    assert p["fridge_days"] == pytest.approx(1.8, abs=0.05)
    assert p["counter_days"] + p["fridge_days"] == pytest.approx(5.0, abs=0.1)


def test_counter_leg_actually_reaches_the_target():
    p = model.plan("avocado", 32.0, 4.0, counter_c=20.0)
    soaked = 32.0 + model.daily_rate(20.0) * p["counter_days"]
    assert soaked == pytest.approx(model.target_for("avocado", "ripe"), abs=1.0)
    assert model.stage_of("avocado", soaked) in ("ripe", "firm")


def test_no_split_when_the_counter_is_too_cold_to_make_it():
    p = model.plan("banana", 0.0, 3.0, counter_c=12.0)  # 55/8 = 6.9 days > 3
    assert p["status"] == "ok"
    assert p["temp_c"] is not None
    assert p["counter_days"] is None
    assert p["fridge_days"] is None


def test_no_split_when_the_counter_is_below_base():
    p = model.plan("banana", 0.0, 5.0, counter_c=model.BASE_C)
    assert p["counter_days"] is None


def test_no_split_when_it_is_exactly_leave_it_out():
    # 55 dd at 21C takes 3.235 days; asking for that is not a two-step plan.
    p = model.plan("banana", 0.0, 55.0 / 17.0, counter_c=21.0)
    assert p["counter_days"] is None


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
    assert "chill" not in out


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


def test_cli_warns_before_fridging_a_firm_banana(capsys):
    assert main(["banana", "--days", "1", "--temp", "21", "--fridge"]) == 0
    out = capsys.readouterr().out
    assert "13°C chill line" in out
    assert "stop ripening for good" in out


def test_cli_softens_the_chill_note_once_it_is_ripe(capsys):
    assert main(["banana", "--days", "4", "--temp", "21", "--fridge"]) == 0
    out = capsys.readouterr().out
    assert "already ripe" in out
    assert "only costs looks" in out
    assert "stop ripening for good" not in out


def test_cli_no_chill_note_for_fridge_safe_fruit(capsys):
    assert main(["strawberry", "--days", "1", "--temp", "20", "--fridge"]) == 0
    assert "chill" not in capsys.readouterr().out


def test_cli_json_carries_the_chill_fields(capsys):
    assert main(["banana", "--days", "1", "--temp", "21", "--fridge",
                 "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["chill_safe_c"] == 13.0
    assert data["chill_risk"] is True


# --- history damage, through the CLI ------------------------------------


def test_cli_flags_a_banana_that_was_fridged_while_firm(capsys):
    assert main(["banana", "--temps", "22,22,4,4,4,22"]) == 0
    out = capsys.readouterr().out
    assert "3 days of its history" in out
    assert "may never ripen properly" in out


def test_cli_history_damage_is_singular_for_one_day(capsys):
    assert main(["tomato", "--temps", "26,26,19,8"]) == 0
    out = capsys.readouterr().out
    assert "1 day of its history" in out


def test_cli_json_carries_the_history_damage(capsys):
    assert main(["banana", "--temps", "22,22,4,4,4,22", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["chilled_days"] == pytest.approx(3.0)
    assert data["chill_injury"] is True
    assert data["degree_days"] == pytest.approx(54.0)


def test_cli_history_damage_is_quiet_for_fridge_safe_fruit(capsys):
    assert main(["strawberry", "--temps", "4,4,4,20"]) == 0
    assert "chilled" not in capsys.readouterr().out


def test_cli_history_damage_softens_once_it_ripened(capsys):
    # cold while firm, but it got there in the end: texture, not tragedy
    assert main(["banana", "--temps", "22,4,4,24,24,24"]) == 0
    out = capsys.readouterr().out
    assert "muted flavour" in out
    assert "may never ripen properly" not in out


def test_cli_history_damage_survives_an_unknown_fruit(capsys):
    assert main(["moon rock", "--temps", "4,4"]) == 2
    assert "unknown fruit" in capsys.readouterr().err


# --- "it's been in the fridge for three days" ---------------------------


def test_cli_counts_a_steady_cold_stint_as_damage(capsys):
    assert main(["banana", "--days", "3", "--temp", "4", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["chilled_days"] == pytest.approx(3.0)
    assert data["chill_injury"] is True


def test_cli_steady_cold_stint_says_it_once(capsys):
    assert main(["banana", "--days", "3", "--temp", "4"]) == 0
    out = capsys.readouterr().out
    assert "3 days of its history" in out
    assert "may never ripen properly" in out
    # the forward-looking version of the same sentence is suppressed
    assert "stop ripening for good" not in out


def test_cli_steady_stint_uses_the_pre_fridge_temperature(capsys):
    # --fridge is the forecast, not the history: two warm days did no damage
    assert main(["banana", "--days", "2", "--temp", "21", "--fridge",
                 "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["chilled_days"] == 0.0
    assert data["chill_injury"] is False


def test_cli_no_history_means_no_damage_note(capsys):
    assert main(["banana", "--days", "3", "--temp", "24", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["chilled_days"] == 0.0
    assert data["chill_injury"] is False


def test_cli_steady_cold_stint_is_quiet_for_fridge_safe_fruit(capsys):
    assert main(["apple", "--days", "5", "--temp", "2"]) == 0
    assert "chilled" not in capsys.readouterr().out


def test_cli_ready_in_plans_a_temperature(capsys):
    assert main(["banana", "--ready-in", "5", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert data["temp_c"] == pytest.approx(15.0)
    assert data["counter_c"] == pytest.approx(model.ROOM_C)
    assert data["fridge_days"] > 0


def test_cli_ready_in_warns_about_a_chilly_hold(capsys):
    assert main(["banana", "--ready-in", "8"]) == 0
    out = capsys.readouterr().out
    assert "13°C chill line" in out
    assert "two-step" in out
    assert "in the fridge" in out


def test_cli_ready_in_stays_quiet_for_a_cold_hold_of_ripe_fruit(capsys):
    assert main(["banana", "--days", "4", "--temp", "21",
                 "--ready-in", "6", "--stage", "fly-feast", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["current_stage"] == "ripe"
    assert data["temp_c"] < data["chill_safe_c"]
    assert data["chill_risk"] is False

    assert main(["banana", "--days", "4", "--temp", "21",
                 "--ready-in", "6", "--stage", "fly-feast"]) == 0
    assert "chill line" not in capsys.readouterr().out


def test_cli_counter_flag_overrides_the_split_temperature(capsys):
    assert main(["banana", "--ready-in", "6", "--counter", "26", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["counter_c"] == pytest.approx(26.0)
    assert data["counter_days"] == pytest.approx(2.5, abs=0.05)


def test_cli_counter_defaults_to_temp(capsys):
    assert main(["banana", "--temp", "26", "--ready-in", "6", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["counter_c"] == pytest.approx(26.0)


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
    assert "in the fridge" in out


def test_cli_ready_in_rejects_zero_days(capsys):
    assert main(["banana", "--ready-in", "0"]) == 2
    assert "positive" in capsys.readouterr().err


def test_cli_list_and_errors(capsys):
    assert main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "banana" in out
    assert "keep above 13°C until ripe" in out
    assert "fridge-safe any time" in out
    assert main(["moon rock"]) == 2
    assert "unknown fruit" in capsys.readouterr().err
    assert main(["moon rock", "--ready-in", "3"]) == 2
    assert "unknown fruit" in capsys.readouterr().err
    assert main([]) == 2
