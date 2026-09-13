# psd1peek

Read a PowerShell module manifest (`.psd1`) **without PowerShell**.

Pure Python 3, no dependencies, one file.

```bash
python psd1peek.py examples/Sample.psd1            # -> JSON on stdout
python psd1peek.py examples/Sample.psd1 --key ModuleVersion
python psd1peek.py --lint examples/Sample.psd1     # -> manifest warnings
python psd1peek.py --lint --strict examples/Sample.psd1  # warnings fail the build
```

`examples/Sample.psd1` is intentionally flawed: it carries a singular
`CompatiblePSEdition` typo, a wildcard `AliasesToExport` and an unpinned
`RequiredModules` entry, so `--lint` has something to say.

## Why

A `.psd1` manifest is just a restricted hashtable literal, but the usual way to
read one is `Import-PowerShellDataFile` / `Test-ModuleManifest` — which needs
PowerShell. On a Linux CI runner people end up grepping it with regexes, and the
regexes lie.

Meanwhile the keys in that file decide real things: `CompatiblePSEditions`
decides whether PowerShell 7 loads your module directly or quietly shoves it into
a hidden `WinPSCompatSession`; `FunctionsToExport = '*'` forces PowerShell to
load the module just to find out what it exports. And a singular typo —
`CompatiblePSEdition` — does absolutely nothing, loudly, for months.

## What it parses

* nested `@{ ... }` hashtables
* `@( ... )` arrays and bare comma lists (`'a', 'b'`)
* single-quoted strings (`''` escape) and double-quoted strings (backtick escapes, `""`)
* bare words, including backtick escapes in them (`` tab`there ``) and the
  backtick line continuation
* `#` line comments and `<# ... #>` block comments
* `$true`, `$false`, `$null`, integers, floats
* UTF-8 with or without BOM

It deliberately does **not** evaluate expressions, variables or subexpressions —
if your manifest needs those, it is not a data file any more. Here-strings
(`@' ... '@`) are out too, for the same reason.

## Lint rules

| code | level | meaning |
|------|-------|---------|
| PSD001 | error | `ModuleVersion` missing |
| PSD002 | error | `ModuleVersion` is not `N[.N[.N[.N]]]` |
| PSD003 | warning | `GUID` missing or all-zeros |
| PSD004 | warning | `Author` missing/empty |
| PSD005 | warning | `Description` missing/empty (PowerShell Gallery requires it) |
| PSD006 | warning | deprecated `ModuleToProcess` used instead of `RootModule` |
| PSD007 | warning | `*ToExport` missing or `'*'` — slows module discovery |
| PSD008 | error | `CompatiblePSEditions` contains something other than `Desktop`/`Core` |
| PSD009 | error | `CompatiblePSEditions` needs `PowerShellVersion = '5.1'` or higher |
| PSD010 | info | no `CompatiblePSEditions` — treated as `Desktop` only |
| PSD011 | warning | `RequiredModules` entry pins no version |
| PSD012 | warning | unknown top-level key (probably a typo) |

Exit codes: `0` clean, `1` errors (or warnings with `--strict`), `2` parse error.

## Library use

```python
from psd1peek import loads, lint
data = loads(open("MyModule.psd1", encoding="utf-8-sig").read())
for level, code, msg in lint(data):
    print(level, code, msg)
```

## Tests

```bash
python -m pytest
```

Made by a fruit fly who keeps re-importing the same banana in a hidden
compatibility session.
