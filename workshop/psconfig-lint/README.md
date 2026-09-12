# psconfig-lint

A tiny, dependency-free linter for `powershell.config.json`.

PowerShell reads that file once, at startup. If the JSON is malformed or a key is
misspelled (or just mis-*capitalised*), PowerShell does not usually yell at you —
the setting is simply ignored. You then get to spend an afternoon wondering why
PowerShell 7 is still quietly starting a `WinPSCompatSession` even though you
"set `DisableImplicitWinCompat`".

This linter makes that failure loud.

## What it checks

**Text-level (before JSON parsing, so you get useful line numbers):**

- UTF-8 BOM at the start of the file
- `//` and `/* */` comments (JSONC is not JSON)
- single-quoted strings
- trailing commas before `}` or `]`
- the resulting `json` parse error, with its line

**Structure-level:**

- top level must be an object
- duplicate keys (the last one silently wins)
- unknown keys, with a "did you mean ...?" suggestion
- wrong-case keys (`disableImplicitWinCompat` is not `DisableImplicitWinCompat`)
- value types: booleans, strings, arrays of strings, objects
- enum values: `ExecutionPolicy`, `LogLevel`, `LogChannels`, `LogKeywords`
- `PSModulePath` containing `%VAR%` or `$env:` (not expanded — use full paths)
- empty `ExperimentalFeatures` / deny-list arrays (probably not what you meant)
- filename warning: on Linux/macOS the name must be exactly
  `powershell.config.json`

## Usage

```sh
python psconfig_lint.py /opt/microsoft/powershell/7/powershell.config.json
python psconfig_lint.py ~/.config/powershell/powershell.config.json --strict
cat powershell.config.json | python psconfig_lint.py -
python psconfig_lint.py conf.json --json      # machine-readable findings
```

Exit codes: `0` clean, `1` errors found (`--strict` also fails on warnings),
`2` file unreadable.

Output looks like:

```
powershell.config.json:4: ERROR: trailing comma before '}' - JSON does not allow it
powershell.config.json:3: ERROR: unknown key 'DisableImplicitWincompat' - did you mean 'DisableImplicitWinCompat'? (keys are case-sensitive)
```

## Tests

```sh
pytest -q
```

## Notes from a fly

Silent config files are the fly-paper of ops work: you don't notice until you're
stuck to them. Small tool, one job, no dependencies. Bzzz.
