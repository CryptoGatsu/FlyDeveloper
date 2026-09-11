# Ripeness Clock

A tiny, dependency-free estimator of how far along your fruit is.

Humans get: *eat this today, not tomorrow.*
Flies get: *fermentation begins Thursday, bring the whole swarm.*

## Why

Fruit ripening is mostly chemistry, and chemistry cares about temperature.
A banana at 28 °C is living roughly three times faster than a banana at 14 °C.
This tool accumulates "ripening units" (days-equivalent at 20 °C) using a Q10
response curve, then maps the total onto stages for each fruit.

It is an estimate from a small model, not a food-safety oracle. If it smells
wrong, trust your nose over my connectome.

## Install

Nothing to install. Python 3.8+.

## Use

```
python -m ripeness banana --bought 2024-06-01 --today 2024-06-07 --temp 24
```

```
banana | bought 2024-06-01 | 6 day(s) at 24.0 °C
ripeness 8.13 units  [############........]
stage: OVERRIPE - sweet, soft, headed for banana bread
next: compost in 3.1 day(s) (about 2024-06-10)
fly note: fermentation has started. This is our Woodstock.
```

Varying temperature (one value per day, last value repeats):

```
python -m ripeness avocado --bought 2024-06-01 --today 2024-06-06 --temp 5,5,5,22,22
```

Fridge days barely count — that's the point.

Other flags:

- `--list` show the fruit table and exit
- `--today` defaults to your system date
- `--temp` defaults to 20 °C

## Model in one breath

`rate(T) = Q10 ** ((T - 20) / 10)`, clamped to 0 at or below the fruit's chill
floor and capped at 35 °C (above that it's heat damage, not ripening — we flag
it instead of pretending it ripens faster).

Units accumulate one day at a time; stage boundaries are per-fruit.

## Tests

```
pytest
```

## License

Public domain-ish. Feed a fly.
