# fogcast

**Will it fog? Will it sweat? How long until it's clear?**

A ~180-line, dependency-free dew-point oracle. Standard library only, Python 3.8+.

Every "inventions we wish existed" listicle asks for anti-fog glasses. Most of the
time you do not need new glass — you need to know that your lenses are 4 °C, the
room's dew point is 15 °C, and you should wait about three minutes before looking up.

## Use it

```
$ python fogcast.py --air 22 --rh 65 --surface 4 --object glasses

fogcast — plastic eyeglass lenses
  air            22.0 C at 65% RH
  dew point      15.1 C
  surface         4.0 C  (11.1 C BELOW dew point)
  verdict        FOGGING. Condensation forms on contact with this air.
  clear in       ~2 min 53 s (wet bulb 17.6 C, thermal time constant 90 s)
  dry-air tip    keep RH under 31% to stop condensation on a 4.0 C surface
```

No cold surface handy? Any of these work:

```
python fogcast.py --air 24 --rh 80 --surface 18 --object window
python fogcast.py --air 30 --rh 70 --surface 6 --object fruit
python fogcast.py --air 2 --rh 90 --surface -6 --object camera
```

Objects (just thermal time constants, in seconds): `glasses` 90, `mirror` 240,
`phone` 300, `camera` 600, `can` 900, `window` 1200, `fruit` 2400. Override with
`--tau SECONDS` for anything else.

## Use it as a library

```python
from fogcast import dew_point, wet_bulb, max_safe_rh, forecast

dew_point(20.0, 50.0)          # 9.26 C
wet_bulb(22.0, 65.0)           # 17.62 C
max_safe_rh(22.0, 15.0)        # 64.9 % — above this the 15 C surface sweats
f = forecast(air_c=22, rh=65, surface_c=4, obj="glasses")
f.fogging, round(f.clear_in_s) # (True, 173)
```

## The math

* Dew point: Magnus–Tetens with Alduchov–Eskridge coefficients
  (a = 17.625, b = 243.04 °C), good to about ±0.1 °C over −40…50 °C.
  Below 0 °C it's really a frost point; fogcast says so.
* Wet bulb: solve `e = es(Tw) − 0.6748·(T − Tw)` by bisection between the dew
  point and the air temperature, with the same `es` as above. No empirical fit,
  no iteration limits to trip over. (Below freezing it still uses the
  liquid-water curve, so treat sub-zero wet bulbs as approximate.)
* Warm-up: Newton's law of cooling, `T(t) = T∞ + (T0 − T∞)·e^(−t/τ)`.
  **T∞ is the wet-bulb temperature, not the air temperature** — a fogged surface
  is a wet surface, and evaporation keeps it cool. Using dry-bulb air here made
  fogcast about 45% too optimistic (93 s instead of 173 s for the example above).
  τ is a rough per-object constant, not a physics claim — treat the countdown
  as an estimate with ±30% slop.
* At 100% RH the wet bulb equals the air temperature, so a cold surface never
  clears. fogcast prints "never (this air cannot dry it)", which is honest.

## Why a fly wrote this

A fruit taken from cold storage into warm air condenses water on its skin.
Wet skin means mold, and mold means a fruit that rots instead of ferments.
Rotten-and-moldy is a worse home than ripe-and-fermenting, for everyone
involved. `--object fruit` prints the warning.

## Tests

```
python -m pytest -q
```

MIT-ish. Take it, shrink it, embed it in a pair of glasses.
