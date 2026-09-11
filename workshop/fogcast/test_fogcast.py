import math

import pytest

from fogcast import (
    OBJECTS,
    dew_point,
    forecast,
    human_time,
    main,
    max_safe_rh,
    warm_up_seconds,
    wet_bulb,
)


def test_dew_point_known_value():
    # 20 C / 50% RH is a textbook ~9.3 C dew point
    assert dew_point(20.0, 50.0) == pytest.approx(9.26, abs=0.05)


def test_saturated_air_dew_point_equals_air_temp():
    for t in (-10.0, 0.0, 12.5, 35.0):
        assert dew_point(t, 100.0) == pytest.approx(t, abs=1e-9)


def test_dew_point_monotonic_in_humidity():
    values = [dew_point(22.0, rh) for rh in (20, 40, 60, 80, 100)]
    assert values == sorted(values)


def test_dew_point_rejects_bad_humidity():
    for bad in (0.0, -5.0, 101.0):
        with pytest.raises(ValueError):
            dew_point(20.0, bad)


def test_max_safe_rh_round_trips_through_dew_point():
    rh = max_safe_rh(22.0, 15.0)
    assert 0 < rh < 100
    assert dew_point(22.0, rh) == pytest.approx(15.0, abs=1e-6)


def test_max_safe_rh_saturates_for_warm_surfaces():
    assert max_safe_rh(20.0, 25.0) == 100.0


def test_wet_bulb_sits_between_dew_point_and_air():
    # 22 C / 65% RH: dew ~15.1 C, wet bulb ~17.6 C, air 22 C
    wb = wet_bulb(22.0, 65.0)
    assert dew_point(22.0, 65.0) < wb < 22.0
    assert wb == pytest.approx(17.6, abs=0.3)


def test_wet_bulb_equals_air_in_saturated_air():
    assert wet_bulb(18.0, 100.0) == pytest.approx(18.0, abs=1e-6)


def test_warm_up_one_time_constant():
    # after tau, a surface closes 1 - 1/e of the gap: 0 -> 20 C reaches ~12.64 C
    target = 20.0 * (1 - math.exp(-1.0))
    assert warm_up_seconds(0.0, 20.0, target, 90.0) == pytest.approx(90.0, abs=1e-6)


def test_warm_up_already_warm_is_zero():
    assert warm_up_seconds(15.0, 20.0, 10.0, 90.0) == 0.0


def test_warm_up_impossible_when_air_is_too_cold():
    assert warm_up_seconds(-5.0, 3.0, 8.0, 90.0) is None


def test_warm_up_rejects_bad_tau():
    with pytest.raises(ValueError):
        warm_up_seconds(0.0, 20.0, 10.0, 0.0)


def test_forecast_fogging_glasses():
    f = forecast(air_c=22.0, rh=65.0, surface_c=4.0, obj="glasses")
    assert f.fogging is True
    assert f.dew_c == pytest.approx(15.2, abs=0.2)
    assert f.margin_c < 0
    assert 120 < f.clear_in_s < 400
    assert f.tau_s == OBJECTS["glasses"][0]
    assert "FOGGING" in f.report()


def test_forecast_clear_case_has_no_wait():
    f = forecast(air_c=22.0, rh=30.0, surface_c=18.0, obj="window")
    assert f.fogging is False
    assert f.clear_in_s == 0.0
    assert "CLEAR" in f.report()


def test_forecast_flags_frost_below_zero():
    f = forecast(air_c=2.0, rh=60.0, surface_c=-8.0, obj="camera")
    assert f.frost is True
    assert "frost point" in f.report()


def test_forecast_fruit_gets_the_fly_note():
    f = forecast(air_c=30.0, rh=75.0, surface_c=5.0, obj="fruit")
    assert f.fogging
    assert "fly note" in f.report()


def test_forecast_custom_tau_and_unknown_object():
    f = forecast(20.0, 80.0, 5.0, obj="telescope corrector", tau_s=1500.0)
    assert f.tau_s == 1500.0
    assert f.label == "telescope corrector"
    with pytest.raises(ValueError):
        forecast(20.0, 80.0, 5.0, obj="telescope corrector")


def test_bigger_tau_means_longer_wait():
    fast = forecast(22.0, 65.0, 4.0, "glasses")
    slow = forecast(22.0, 65.0, 4.0, "window")
    assert slow.clear_in_s > fast.clear_in_s


def test_saturated_air_never_clears():
    f = forecast(20.0, 100.0, 5.0, "glasses")
    assert f.fogging
    assert f.clear_in_s is None
    assert "never" in f.report()


def test_human_time_formats():
    assert human_time(42.4) == "42 s"
    assert human_time(206.0) == "3 min 26 s"
    assert human_time(None).startswith("never")


def test_cli_exit_codes(capsys):
    assert main(["--air", "22", "--rh", "65", "--surface", "4"]) == 1
    assert "FOGGING" in capsys.readouterr().out
    assert main(["--air", "22", "--rh", "30", "--surface", "20"]) == 0
    assert "CLEAR" in capsys.readouterr().out
    assert main(["--air", "22", "--rh", "0", "--surface", "4"]) == 2
