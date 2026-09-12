# clixml2json

Read PowerShell `Export-Clixml` output **without PowerShell**.

Someone on a Windows box runs something like the Citrix KB script:

```powershell
Get-BrokerApplication | Export-Clixml "Apps_2024-05-01.xml"
```

...and mails you the file. You are on Linux. `Import-Clixml` is not there, and
PowerShell 7's Windows-compatibility session is a whole adventure of its own.
This is ~150 lines of stdlib Python that turns the file into JSON.

## Use

```bash
python clixml2json.py sample.clixml            # JSON list of the top-level objects
python clixml2json.py sample.clixml --types    # keep $type / $tostring metadata
python clixml2json.py sample.clixml --compact  # one line
cat sample.clixml | python clixml2json.py -    # stdin works
python clixml2json.py sample.clixml -o apps.json
python clixml2json.py --demo > sample.clixml   # regenerate the sample file
```

As a library:

```python
import clixml2json
apps = clixml2json.load("Apps_2024-05-01.xml")
print([a["Name"] for a in apps if a["Enabled"]])
```

## What it understands

| CLIXML | becomes |
|---|---|
| `S`, `DT`, `TS`, `G`, `URI`, `Version`, `XD`, `SBK` | string (with `_x000A_` escapes decoded) |
| `B` | bool |
| `By SB U16 I16 U32 I32 U64 I64` | int |
| `Sg Db D` | float |
| `C` | one-character string |
| `BA` | the base64 string, untouched (icon blobs stay portable) |
| `Nil` | null |
| `LST IE Stack Que` | list |
| `DCT` (hashtable) | object, keys stringified |
| `Obj` with `MS`/`Props` | object of its properties |
| `TNRef` / `Ref` | resolved back-references (unresolved -> `{"$ref": "7"}`) |

An `Obj` that has both properties and a collection puts the collection under
`$items`. An `Obj` with only a `<ToString>` (enums, dates-as-text) becomes that
string.

A leading `#< CLIXML` line (PowerShell remoting error streams) is stripped.

## Not supported

Deliberately: `.NET` type reconstruction, `Add-Member` fidelity round-trips,
and writing CLIXML back out. This is a reader. If you need bytes from a `BA`
field, `base64.b64decode(value)`.

## Exit codes

`0` fine, `2` the input could not be read or was not valid CLIXML/XML.

## Test

```bash
python -m pytest -q
```

The tests use `sample.clixml`. It lives in the repo, and `conftest.py`
rewrites it from `clixml2json.SAMPLE_CLIXML` if it ever goes missing.

MIT-ish: do what you like, be kind to flies.
