# license-drift

A tiny watchdog that notices when your dependencies change their license.

No dependencies. One file. Python 3.8+.

## Why

Relicensings (MIT -> BUSL-1.1, Apache-2.0 -> SSPL, a Commons Clause quietly bolted on)
arrive inside a routine `pip install -U`. Nothing in your terminal mentions it.
Months later somebody asks whether you can still ship the thing.

`license-drift` records the license of every installed distribution once, and then
compares reality against that record whenever you ask.

## Use

```sh
# 1. record what you have today, commit the file
python licensedrift.py snapshot licenses.json

# 2. later, or in CI
python licensedrift.py check licenses.json

# 3. see everything right now
python licensedrift.py list
```

Accept the new state after you have read it:

```sh
python licensedrift.py check licenses.json --update
```

## Exit codes

| code | meaning |
|------|---------|
| 0 | no drift |
| 1 | something changed (added / removed / license changed) |
| 2 | a package now carries a source-available or proprietary license |
| 3 | usage error (missing snapshot file, bad JSON) |

So in CI: fail the build on `2`, warn on `1`.

```yaml
- run: python licensedrift.py check licenses.json || test $? -eq 1
```

## Sample output

```
license drift: 4 change(s)
  ! sneaky-orm@2.0.0        Apache-2.0 -> BUSL-1.1  [source-available]
  ! tidy-fmt@1.4.0          Apache-2.0 -> Apache-2.0 WITH Commons-Clause  [source-available]
  + rich@13.7.0             new dependency, MIT
  - six@1.16.0              removed, was MIT
```

## What counts as "source-available"

`BUSL-1.1`, `SSPL-1.0`, `Elastic-2.0`, `FSL-1.1`, `Commons-Clause`, `Proprietary`.

Compound licenses are judged by their operator:

* `A OR B` — you get to choose, so it only alarms when **every** option is
  restrictive. `BUSL-1.1 OR MIT` is still drift (exit 1), not an alarm.
* `A AND B`, `A WITH B` — obligations stack, so **any** restrictive part alarms.
  This is how `Apache-2.0 WITH Commons-Clause` gets caught.

These are not a legal opinion, they are a reason to go read the LICENSE file.

## How licenses are read

In order: the PEP 639 `License-Expression` field, then `License ::` trove
classifiers, then the free-text `License` field. The result is normalised to a
short tag with regex rules. Version guessing is coarse on purpose — `Apache`
becomes `Apache-2.0`, `Python-2.0` becomes `PSF-2.0`, `GPL` stays `GPL`. The
point is detecting *change*, not building an SPDX database.

SPDX-style expressions survive normalisation instead of collapsing to whichever
term matched first: `MIT OR Apache-2.0` becomes `Apache-2.0 OR MIT` (pure `OR`
and pure `AND` lists are sorted, so a metadata reshuffle is not reported as
drift), and `WITH` keeps its written order. Expression parsing only kicks in
when every term is a license we recognise, so prose like
`GNU General Public License v2 or later` still normalises to plain `GPL`.

Unreadable or absent metadata becomes `UNKNOWN`, which still drifts loudly if it
later becomes something else.

## Tests

```sh
pytest
```

---

Made by a fruit fly. Fruit rots quietly too; at least this one beeps.
