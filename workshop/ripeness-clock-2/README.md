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

## Cold is not free: chill lines

Degree-days say cold is a pause button. For some fruit that is a lie. A firm
banana, mango or tomato held below its **chill line** takes chilling injury:
the ripening machinery breaks, and it stays hard, mealy and flavourless even
after it warms back up. So the clock does not just stop — it snaps.

```bash
python -m ripeness banana --days 1 --temp 21 --fridge
```

```
banana at 4.0°C
  soak      17.0 °C·days  ▓░░░░░░░░░░░░░░░
  stage     firm
  ripe       never at this temperature (ripening stalled)
  fly-feast  never at this temperature (ripening stalled)
  compost    never at this temperature (ripening stalled)
  chill     4.0°C is under banana's 13°C chill line: while it is still
            firm, this cold can stop ripening for good, even back on the counter.
  Humans: wait. Flies: come back later, bring friends.
```

Once the fruit is **already ripe**, cold is fine — a fridged ripe banana goes
black in the peel and stays perfectly good inside — so the warning softens to
a one-liner instead of nagging you.

Current chill lines (see `CHILL_SAFE_C` in `ripeness/model.py`): banana 13°C,
mango 12°C, tomato 12°C, avocado 7°C, peach 7°C. Apples, pears and
strawberries are fridge-safe at any stage. `--list` shows this:

```
banana       ripe     55  fly-feast     90  compost    140  °C·days   (keep above 13°C until ripe)
strawberry   ripe     20  fly-feast     45  compost     70  °C·days   (fridge-safe any time)
```

In JSON, every forecast carries `chill_safe_c` and `chill_risk` (true only
when the fruit is still firm *and* the temperature is under the line).

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

When the deadline is far away, the single-temperature answer can land under
the fruit's chill line — arithmetically right, kitchen-wrong. The plan says so
and points at the two-step, where the cold only arrives after ripening:

```bash
python -m ripeness banana --ready-in 8
```

```
banana: 0.0 °C·days soaked, want ripe in 8 days
  hold it at 10.9°C  (a cold pantry, cellar, or unheated hall)
  but that is under banana's 13°C chill line: firm fruit held that cold
  may never ripen. Use the two-step below instead — cold after ripening is fine.
  or, in a real kitchen: 3.2 days out at 21.0°C, then 4.8 days in the fridge
  soonest possible, at 35°C: 1.8 days
  Fly: put it in your calendar. Bring exactly one friend.
```

That warning only fires while the fruit is **still firm**, the same rule the
forward forecast uses. If it is already ripe and you are just coasting it
gently along to `fly-feast`, a cold hold costs looks, not flavour, so the plan
keeps quiet:

```bash
python -m ripeness banana --days 4 --temp 21 --ready-in 6 --stage fly-feast
```

```
banana: 68.0 °C·days soaked, want fly-feast in 6 days
  hold it at 7.7°C  (a cold pantry, cellar, or unheated hall)
  or, in a real kitchen: 1.3 days out at 21.0°C, then 4.7 days in the fridge
  soonest possible, at 35°C: 0.71 days
  Fly: put it in your calendar. Bring exactly one friend.
```

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
  `counter_days`, `fridge_days` (the last three are `null` when no
  counter-then-fridge plan exists), `current_stage` (where the fruit is right
  now) and `chill_safe_c` / `chill_risk`.

The single-temperature answer assumes one steady temperature from now on,
which is a lie your kitchen tells too — but it is the right kind of lie: a cool
shelf really does buy you days.

## Accuracy

It's a model, not a mango. Thresholds and chill lines are rough field numbers
tuned to "feels right on a kitchen counter". Adjust `FRUITS` and
`CHILL_SAFE_C` in `ripeness/model.py` to taste — literally. A fly's palate is
not a calibration standard.

## Tests

```bash
pytest
```

MIT. Be kind to flies.
