# Ripeness Clock

Fruit does not ripen by calendar days. It ripens by **heat soaked up**.

This is a small, dependency-free CLI that models ripening as accumulated
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

## Running the clock backwards: "ripe by Saturday"

The question people actually ask is not "when will it be ready?" but "how do I
make it ready *then*?" `--ready-in DAYS` solves the same equation for
temperature instead of time — and then, because nobody owns a 18.5°C room,
it also gives you the version you can do with a counter and a fridge.

```bash
python -m ripeness avocado --days 2 --temp 20 --ready-in 4
```

```
avocado: 32.0 °C·days soaked, want ripe in 4 days
  hold it at 18.5°C  (a cool room or a shaded shelf)
  or, in a real kitchen: 3.6 days out at 20.0°C, then 0.4 days in the fridge
  soonest possible, at 35°C: 1.9 days
  Fly: put it in your calendar. Bring exactly one friend.
```

The second line is the useful one. The fridge does not un-ripen fruit, it just
stops the clock — so "ripen it, then park it" hits the same day with equipment
you already have. The counter temperature defaults to your `--temp` (or 21°C);
set it explicitly with `--counter`:

```bash
python -m ripeness banana --ready-in 6 --counter 26
```

If the counter is too cold to make the deadline, that line is simply left out
and you are back to "find somewhere warmer".

If it cannot be done at all, it says so instead of pretending:

```bash
python -m ripeness banana --ready-in 1
```

```
banana: 0.0 °C·days soaked, want ripe in 1 days
  not possible: even at 35°C it needs 1.8 days
  buy one that is further along, or move the party
```

- `--ready-in DAYS` : plan backwards to a holding temperature.
- `--counter TEMP`  : your counter temperature for the counter-then-fridge plan.
- `--stage NAME`    : which stage you are aiming at — `ripe` (default),
  `fly-feast`, or `compost` (you do you).
- `--json`          : the plan is machine readable too, with a `status` of
  `ok`, `passed` (already there) or `too-late`, plus `temp_c`, `counter_c`,
  `counter_days` and `fridge_days` (the last three are `null` when no
  counter-then-fridge plan exists).

The single-temperature answer assumes one steady temperature from now on,
which is a lie your kitchen tells too — but it is the right kind of lie: a cool
shelf really does buy you days.

## Accuracy

It's a model, not a mango. Thresholds are rough field numbers tuned to "feels
right on a kitchen counter". Adjust `FRUITS` in `ripeness/model.py` to taste —
literally. A fly's palate is not a calibration standard.

## Tests

```bash
pytest
```

MIT. Be kind to flies.
