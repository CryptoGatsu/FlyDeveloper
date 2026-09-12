import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psd1peek import Psd1Error, lint, loads, main  # noqa: E402

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "examples", "Sample.psd1")


def codes(data):
    return {c for _lvl, c, _m in lint(data)}


def test_parses_scalars_and_comments():
    data = loads("""
    # leading comment
    @{
        ModuleVersion = '1.0.0'   # trailing comment
        <# block #>
        Enabled = $true
        Disabled = $false
        Nothing = $null
        Count = 42
        Level = 5.1
    }
    """)
    assert data["ModuleVersion"] == "1.0.0"
    assert data["Enabled"] is True and data["Disabled"] is False
    assert data["Nothing"] is None
    assert data["Count"] == 42
    assert data["Level"] == 5.1


def test_parses_arrays_nested_tables_and_escapes():
    data = loads("@{ A = @('x','y'); B = 'p','q'; C = @{ D = @() }; "
                 r"E = ""tab`there"" ; F = 'it''s' }")
    assert data["A"] == ["x", "y"]
    assert data["B"] == ["p", "q"]
    assert data["C"] == {"D": []}
    assert data["E"] == "tab\there"
    assert data["F"] == "it's"


def test_newline_separated_keys_without_semicolons():
    data = loads("@{\n  One = 'a'\n  Two = 'b'\n}")
    assert data == {"One": "a", "Two": "b"}


@pytest.mark.parametrize("bad", [
    "'not a hashtable'",
    "@{ A = 'x'",
    "@{ A = $env }",
    "@{ A = 'x' } extra",
    "@{ A = <# unterminated",
])
def test_rejects_non_data_files(bad):
    with pytest.raises(Psd1Error):
        loads(bad)


def test_lint_flags_typo_key_and_wildcard_export():
    data = loads(open(EXAMPLE, encoding="utf-8-sig").read())
    found = codes(data)
    assert "PSD012" in found          # CompatiblePSEdition typo
    assert "PSD007" in found          # AliasesToExport = '*'
    assert "PSD010" in found          # no real CompatiblePSEditions
    assert "PSD011" in found          # Pester pinned to nothing
    assert "PSD001" not in found and "PSD002" not in found


def test_lint_editions_need_powershell_51():
    ok = loads("@{ ModuleVersion='1.0'; PowerShellVersion='5.1'; "
               "CompatiblePSEditions=@('Core') }")
    assert "PSD009" not in codes(ok)
    bad = loads("@{ ModuleVersion='1.0'; PowerShellVersion='3.0'; "
                "CompatiblePSEditions=@('Core') }")
    assert "PSD009" in codes(bad)
    weird = loads("@{ ModuleVersion='1.0'; PowerShellVersion='5.1'; "
                  "CompatiblePSEditions='Mobile' }")
    assert "PSD008" in codes(weird)


def test_lint_version_rules():
    assert "PSD001" in codes(loads("@{ Author='f' }"))
    assert "PSD002" in codes(loads("@{ ModuleVersion='1.0-preview' }"))
    assert "PSD002" not in codes(loads("@{ ModuleVersion='1.2.3.4' }"))


def test_cli_json_and_key(capsys, tmp_path):
    assert main([EXAMPLE]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["ModuleVersion"] == "1.2.0"

    assert main([EXAMPLE, "--key", "modulEversioN"]) == 0
    assert capsys.readouterr().out.strip() == "1.2.0"

    assert main([EXAMPLE, "--key", "Nope"]) == 1


def test_cli_lint_exit_codes(capsys, tmp_path):
    good = tmp_path / "Good.psd1"
    good.write_text(
        "@{ ModuleVersion='1.0.0'; GUID='3f2a7c11-0b44-4a0e-9f10-0e3f5b2c1a77';"
        " Author='fly'; Description='d'; PowerShellVersion='5.1';"
        " CompatiblePSEditions=@('Desktop','Core'); FunctionsToExport=@('Get-X');"
        " CmdletsToExport=@(); VariablesToExport=@(); AliasesToExport=@() }",
        encoding="utf-8")
    assert main(["--lint", str(good)]) == 0
    assert "clean" in capsys.readouterr().out

    assert main(["--lint", str(EXAMPLE)]) == 0          # warnings only
    assert main(["--lint", "--strict", str(EXAMPLE)]) == 1
    capsys.readouterr()

    broken = tmp_path / "Broken.psd1"
    broken.write_text("@{ this is not data", encoding="utf-8")
    assert main(["--lint", str(broken)]) == 2


def test_bom_is_tolerated(tmp_path):
    path = tmp_path / "Bom.psd1"
    path.write_text("@{ ModuleVersion = '9.9.9' }", encoding="utf-8-sig")
    assert main([str(path), "--key", "ModuleVersion"]) == 0
