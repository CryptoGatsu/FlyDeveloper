# Ripeness Clock

Fruit does not ripen by calendar days. It ripens by **heat soaked up**.

This is a ~200 line, dependency-free CLI that models ripening as accumulated
**degree-days**: every day, a fruit banks `temperature - 4°C` of ripening
(capped at 35°C, above which things stop being food and start being science).
Each fruit has thresholds for `ripe`, `fly-feast` and `compost`.

## Why

- **Humans:** "bought it Tuesday" tells you nothing. 3 days at 28°C is roughly
  a week at 15°C. Stop binning good avocados.
- **Flies:** we live ~50 days. Showing up three days early to a banana is 6% of
  a whole life spent hovering over a green thing. An ETA is a kindness.

## Run it

```bash
python -m ripeness banana --days 3 --temp 24
```

```
banana at 24.0°C
  soak      60.0 °C·days  ▓▓▓▓▓▓░░░░░░░░░░
  stage     ripe
  ripe       already there
  fly-feast  in 1.5 days
  compost    in 4.0 days
  Eat it now, human. Fly: hover politely, wait your turn.
```

More:

```bash
python -m ripeness --list                      # known fruits
python -m ripeness tomato --temps 26,26,19,8   # a real temperature history
python -m ripeness avocado --days 5 --fridge   # what if I chill it from now on
python -m ripeness mango --days 2 --temp 30 --json
```

- `--days D --temp T` : it has sat D days at a steady T°C.
- `--temps a,b,c`     : one measured temperature per past day (more honest).
- `--temp`            : also the temperature used for the forecast ahead.
- `--fridge`          : forecast at 4°C, where ripening effectively stalls.

## Accuracy

It's a model, not a mango. Thresholds are rough field numbers tuned to "feels
right on a kitchen counter". Adjust `FRUITS` in `ripeness/model.py` to taste —
literally. A fly's palate is not a calibration standard.

## Tests

```bash
pytest
```

MIT. Be kind to flies.
