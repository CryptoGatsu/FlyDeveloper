import datetime as dt

import pytest

from ripeness import model as m
from ripeness.cli import main, parse_temps, report


def test_reference_rate_is_one():
    assert m.ripening_rate(20.0) == pytest.approx(1.0)


def test_rate_increases_with_heat():
    assert m.ripening_rate(10.0) < m.ripening_rate(20.0) < m.ripening_rate(30.0)


def test_rate_capped_above_heat_cap():
    assert m.ripening_rate(45.0) == pytest.approx(m.ripening_rate(m.HEAT_CAP_C))


def test_fridge_stops_ripening():
    banana = m.FRUITS["banana"]
    assert m.ripening_rate(4.0, banana.chill_floor) == 0.0
    assert m.accumulate(banana, [4.0] * 10) == 0.0


def test_accumulate_matches_days_at_reference():
    peach = m.FRUITS["peach"]
    assert m.accumulate(peach, [20.0] * 5) == pytest.approx(5.0)


def test_stage_boundaries():
    f = m.FRUITS["banana"]
    assert m.stage(f, 0.0) == "green"
    assert m.stage(f, f.to_ripe) == "ripe"
    assert m.stage(f, f.to_peak) == "peak"
    assert m.stage(f, f.to_overripe) == "overripe"
    assert m.stage(f, f.to_compost + 99) == "compost"


def test_next_stage_ends():
    assert m.next_stage("green") == "ripe"
    assert m.next_stage("compost") is None


def test_days_until_is_consistent():
    f = m.FRUITS["peach"]
    d = m.days_until(f, 0.0, "ripe", 20.0)
    assert d == pytest.approx(f.to_ripe)
    assert m.days_until(f, f.to_ripe, "ripe", 20.0) == 0.0


def test_days_until_never_in_the_cold():
    f = m.FRUITS["banana"]
    assert m.days_until(f, 0.0, "ripe", 2.0) is None


def test_warm_ripens_faster_than_cool():
    f = m.FRUITS["mango"]
    warm = m.days_until(f, 0.0, "peak", 28.0)
    cool = m.days_until(f, 0.0, "peak", 18.0)
    assert warm < cool


def test_progress_bar_shape():
    f = m.FRUITS["apple"]
    bar = m.progress_bar(f, 0.0)
    assert bar == "[" + "." * 20 + "]"
    assert m.progress_bar(f, 10 * f.to_compost) == "[" + "#" * 20 + "]"


def test_parse_temps_repeats_last():
    assert parse_temps("5,22", 4) == [5.0, 22.0, 22.0, 22.0]
    assert parse_temps("5,22,30", 2) == [5.0, 22.0]
    assert parse_temps("20", 0) == []


def test_parse_temps_rejects_empty():
    with pytest.raises(ValueError):
        parse_temps("  ", 3)


def test_report_mentions_stage_and_fly():
    f = m.FRUITS["banana"]
    bought = dt.date(2024, 6, 1)
    today = dt.date(2024, 6, 7)
    text = report(f, bought, today, [24.0] * 6)
    assert "banana" in text
    assert "stage:" in text
    assert "fly note:" in text


def test_report_flags_heat_damage():
    f = m.FRUITS["tomato"]
    text = report(f, dt.date(2024, 6, 1), dt.date(2024, 6, 3), [41.0, 41.0])
    assert "heat damage" in text


def test_cli_happy_path(capsys):
    code = main(["banana", "--bought", "2024-06-01", "--today", "2024-06-07", "--temp", "24"])
    out = capsys.readouterr().out
    assert code == 0
    assert "banana" in out
    assert "ripeness" in out


def test_cli_list(capsys):
    assert main(["--list"]) == 0
    assert "banana" in capsys.readouterr().out


def test_cli_unknown_fruit(capsys):
    assert main(["durian"]) == 2
    assert "unknown fruit" in capsys.readouterr().out


def test_cli_future_purchase(capsys):
    code = main(["pear", "--bought", "2024-06-10", "--today", "2024-06-01"])
    assert code == 2
    assert "not been bought" in capsys.readouterr().out


def test_cli_needs_a_fruit(capsys):
    assert main([]) == 2
    assert "give me a fruit" in capsys.readouterr().out
