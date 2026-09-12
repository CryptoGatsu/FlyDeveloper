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
| 2 | a package now carries an alarming license |
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

## Your own policy: `--alarm-on`

Out of the box only source-available licenses exit `2`. Plenty of teams have a
different line in the sand — no AGPL in a hosted service, no unreadable license
metadata at all. Name the extra tags and they join the alarm set:

```sh
python licensedrift.py check licenses.json --alarm-on AGPL-3.0,GPL
python licensedrift.py check licenses.json --alarm-on agpl --alarm-on UNKNOWN
```

* Comma-separated, repeatable, and each value is normalised by the same rules as
  package metadata — `agpl`, `AGPL-3.0` and `GNU Affero` all mean `AGPL-3.0`.
* Tags are distinct: `GPL`, `LGPL` and `AGPL-3.0` are three separate things, so
  list the ones you mean.
* `--alarm-on UNKNOWN` turns "we could not read this package's license" into a
  build failure, which is a good habit once your snapshot is clean.
* Compound licenses follow the same operator rules as below, so
  `AGPL-3.0 OR MIT` still does not alarm under an AGPL policy: you may pick MIT.
* The built-in source-available set is always included; `--alarm-on` only adds.

Policy hits are labelled `[policy]` instead of `[source-available]`, so a reader
can tell "the upstream rug-pulled" from "this is our own house rule":

```
license drift: 1 change(s)
  ! chatty-lib@3.0.0        MIT -> AGPL-3.0  [policy]
```

## Machine-readable output

For bots, PR annotations and anything that would otherwise grep the text report:

```sh
python licensedrift.py check licenses.json --json
```

```json
{
  "alarms": 1,
  "alarm_on": ["BUSL-1.1", "Commons-Clause", "Elastic-2.0", "FSL-1.1", "Proprietary", "SSPL-1.0"],
  "changes": [
    {
      "alarm": true,
      "kind": "license-change",
      "name": "sneaky-orm@2.0.0",
      "new": "BUSL-1.1",
      "old": "Apache-2.0",
      "package": "sneaky-orm",
      "version": "2.0.0"
    }
  ],
  "exit_code": 2,
  "generated": "2024-05-01T09:14:02Z",
  "snapshot": "licenses.json",
  "snapshot_updated": false,
  "tool": "license-drift"
}
```

`kind` is one of `added`, `removed`, `license-change`. `old` and `new` are the
normalised license tags (`null` where they do not apply). `alarm` is the
block-the-merge flag. `alarm_on` is the effective alarm set for this run —
built-ins plus anything you passed to `--alarm-on` — so a log tells you which
policy produced the verdict. The exit code is still the exit code; it is
repeated in the document so a job that pipes stdout into another tool does not
lose it.

With `--json`, stdout is *only* JSON: the "snapshot updated." line becomes the
`snapshot_updated` field. Errors still go to stderr with exit `3`.

`list --json` prints exactly what a snapshot file contains, so
`python licensedrift.py list --json > licenses.json` is the same thing as
`python licensedrift.py snapshot licenses.json`.

## What counts as "source-available"

`BUSL-1.1`, `SSPL-1.0`, `Elastic-2.0`, `FSL-1.1`, `Commons-Clause`, `Proprietary`.

Compound licenses are judged by their operator:

* `A OR B` — you get to choose, so it only alarms when **every** option is
  restrictive. `BUSL-1.1 OR MIT` is still drift (exit 1), not an alarm.
* `A AND B`, `A WITH B` — obligations stack, so **any** restrictive part alarms.
  This is how `Apache-2.0 WITH Commons-Clause` gets caught.

These are not a legal opinion, they are a reason to go read the LICENSE file.

## Package names

Names are compared after PEP 503 normalisation: lower-cased, with any run of
`-`, `_` or `.` collapsed to a single `-`. So `Typing_Extensions`,
`typing.extensions` and `typing-extensions` are one package, and a project that
re-spells its own `Name:` field between releases does not show up as one
dependency vanishing and another appearing. Old snapshots are normalised when
they are read, so nothing needs regenerating.

If the same distribution has two `.dist-info` directories (a virtualenv
shadowing a system install), the first one on `sys.path` wins — the same copy
Python would actually import.

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
later becomes something else — and can be made a hard failure with
`--alarm-on UNKNOWN`.

## Tests

```sh
pytest
```

---

Made by a fruit fly. Fruit rots quietly too; at least this one beeps.
