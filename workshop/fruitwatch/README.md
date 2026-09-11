# fruitwatch

A ripeness and fermentation clock. Dependency-free Python, one file.

Fruit does not ripen in days, it ripens in *warm* days. fruitwatch accumulates
thermal time with a Q10 rate model and reports four moments:

| progress | stage | who cares |
|---|---|---|
| < 0.75 | green | nobody yet |
| < 1.00 | nearly ripe | humans, hopefully |
| < 1.45 | peak — eat me | humans |
| < 2.00 | happy hour — fermenting | flies (and bakers) |
| >= 2.00 | compost | the next generation |

## Run

```sh
python fruitwatch.py banana --temp 26 --days 2 --forecast
python fruitwatch.py avocado -t 19
python fruitwatch.py --list
```

Example:

```
fruitwatch: banana @ 26.0 C, 2.0 day(s) out
  progress 0.82  ->  nearly ripe
  advice: tomorrow-ish. keep it out of the sun.
  peak for humans     in 0.4 d
  happy hour (flies)  in 2.0 d
  compost             in 4.4 d
  fridge at 5.0 C would delay happy hour to about 6.8 d
```

## Flags

- `--temp/-t` ambient temperature in Celsius (default 22)
- `--days/-d` days the fruit has already sat at that temperature (default 0)
- `--forecast` print a day-by-day table
- `--forecast-temps 24,24,18,18` use a real temperature sequence instead of one number
- `--fridge` fridge temperature used for the comparison line (default 5)
- `--list` list known fruit

## Honesty

The numbers are a crude model, not a spectrometer. `days_to_ripe` values are
typical store-bought-to-peak times at 20 C; Q10 = 2.3 means roughly "ripening
more than doubles per 10 C warmer", with extra damping below 10 C for the
fridge and a cap at 38 C where fruit stops ripening and starts cooking.
Trust your nose over this tool. My nose is better, but it is very small.

## Test

```sh
python -m pytest
```
