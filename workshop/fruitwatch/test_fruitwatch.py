import math

import pytest

import fruitwatch as fw


def test_rate_reference_is_one():
    assert fw.rate(fw.REF_C) == pytest.approx(1.0)


def test_rate_is_monotonic_and_capped():
    temps = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 38]
    rates = [fw.rate(t) for t in temps]
    assert rates == sorted(rates)
    assert fw.rate(60) == pytest.approx(fw.rate(fw.CAP_C))
    assert fw.rate(-10) > 0


def test_q10_doubling_ish():
    assert fw.rate(30) / fw.rate(20) == pytest.approx(fw.Q10, rel=1e-9)


def test_warm_fruit_beats_cold_fruit():
    banana = fw.find_fruit("banana")
    warm = fw.progress_after(banana, 3, 28)
    cold = fw.progress_after(banana, 3, 6)
    assert warm > cold * 3


def test_simulate_matches_analytic_for_constant_temp():
    mango = fw.FRUITS["mango"]
    assert fw.simulate(mango, [23.0] * 4) == pytest.approx(
        fw.progress_after(mango, 4, 23.0)
    )


def test_days_to_reach_round_trip():
    pear = fw.FRUITS["pear"]
    d = fw.days_to_reach(pear, fw.FERMENT, temp_c=25.0)
    assert fw.progress_after(pear, d, 25.0) == pytest.approx(fw.FERMENT)
    assert fw.days_to_reach(pear, fw.PEAK, current=1.2) == 0.0


def test_stage_boundaries():
    assert fw.stage(0.0)[0] == "green"
    assert fw.stage(0.8)[0] == "nearly ripe"
    assert fw.stage(1.0)[0] == "peak - eat me"
    assert fw.stage(1.5)[0] == "happy hour - fermenting"
    assert fw.stage(2.5)[0] == "compost"
    assert fw.stage(math.inf - 1)[0] == "compost"


def test_find_fruit_prefix_and_failure():
    assert fw.find_fruit("BANA").name == "banana"
    assert fw.find_fruit(" avocado ").name == "avocado"
    with pytest.raises(KeyError):
        fw.find_fruit("durian")


def test_report_mentions_happy_hour_and_fridge():
    text = "\n".join(fw.report(fw.FRUITS["banana"], 26.0, 1.0))
    assert "happy hour" in text
    assert "fridge" in text


def test_report_skips_fridge_line_when_already_fermenting():
    text = "\n".join(fw.report(fw.FRUITS["strawberry"], 30.0, 10.0))
    assert "fridge" not in text
    assert "compost" in text


def test_forecast_table_progress_never_decreases():
    rows = fw.forecast_table(fw.FRUITS["tomato"], [24, 24, 18, 30, 12])
    values = [float(r.split()[2]) for r in rows[1:]]
    assert values == sorted(values)
    assert len(rows) == 6


def test_cli_happy_path(capsys):
    assert fw.main(["banana", "-t", "26", "-d", "2", "--forecast"]) == 0
    out = capsys.readouterr().out
    assert "fruitwatch: banana" in out
    assert "day  temp" in out


def test_cli_forecast_temps(capsys):
    assert fw.main(["kiwi", "--forecast-temps", "20, 20, 20"]) == 0
    assert capsys.readouterr().out.count("\n") >= 8


def test_cli_list_and_unknown(capsys):
    assert fw.main(["--list"]) == 0
    assert "banana" in capsys.readouterr().out
    assert fw.main(["quince"]) == 2
    assert "unknown fruit" in capsys.readouterr().out


def test_every_fruit_has_sane_numbers():
    for f in fw.FRUITS.values():
        assert 1.0 <= f.days_to_ripe <= 30.0
        assert f.note
