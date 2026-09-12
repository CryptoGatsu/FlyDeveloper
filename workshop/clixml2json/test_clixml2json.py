import base64
import json
from pathlib import Path

import clixml2json

HERE = Path(__file__).parent
SAMPLE = HERE / "sample.clixml"


def wrap(inner):
    return ('<Objs Version="1.1.0.1" '
            'xmlns="http://schemas.microsoft.com/powershell/2004/04">'
            + inner + "</Objs>")


def test_scalars():
    xml = wrap('<S>hi</S><I32>42</I32><B>true</B><B>False</B>'
               '<Db>1.25</Db><Nil/><C>65</C><U64>18446744073709551615</U64>')
    assert clixml2json.loads(xml) == [
        "hi", 42, True, False, 1.25, None, "A", 18446744073709551615]


def test_string_escapes():
    xml = wrap("<S>line1_x000A_line2_x0009_tab</S>")
    assert clixml2json.loads(xml) == ["line1\nline2\ttab"]


def test_list_and_hashtable():
    xml = wrap('<Obj RefId="0"><LST><S>a</S><S>b</S></LST></Obj>'
               '<Obj RefId="1"><DCT><En><S N="Key">k</S>'
               '<I32 N="Value">7</I32></En></DCT></Obj>')
    assert clixml2json.loads(xml) == [["a", "b"], {"k": 7}]


def test_tostring_only_object():
    xml = wrap('<Obj RefId="0"><TN RefId="0"><T>SomeEnum</T></TN>'
               "<ToString>Running</ToString></Obj>")
    assert clixml2json.loads(xml) == ["Running"]


def test_properties_plus_items_go_to_dollar_items():
    xml = wrap('<Obj RefId="0"><MS><S N="Name">x</S></MS>'
               "<LST><I32>1</I32></LST></Obj>")
    assert clixml2json.loads(xml) == [{"Name": "x", "$items": [1]}]


def test_ref_resolution_and_unknown_ref():
    xml = wrap('<Obj RefId="5"><MS><S N="Name">first</S></MS></Obj>'
               '<Ref RefId="5"/><Ref RefId="99"/>')
    a, b, c = clixml2json.loads(xml)
    assert b == a == {"Name": "first"}
    assert c == {"$ref": "99"}


def test_remoting_header_is_stripped():
    xml = "#< CLIXML\n" + wrap("<S>ok</S>")
    assert clixml2json.loads(xml) == ["ok"]


def test_sample_file_round_trip():
    apps = clixml2json.load(SAMPLE)
    assert [a["Name"] for a in apps] == ["Banana Browser", "Grape Grabber"]
    first = apps[0]
    assert first["Enabled"] is True
    assert first["Description"] is None
    assert first["Priority"] == 3
    assert first["CommandLine"] == "ripe.exe --sniff"
    assert first["Tags"] == ["fruit", "kitchen"]
    assert first["Limits"] == {"MaxUsers": 50}
    assert base64.b64decode(first["IconData"]) == b"\xde\xad\xbe\xef"
    # TNRef + Ref: second app points at the first app's tag list
    assert apps[1]["SharesTagsWith"] == ["fruit", "kitchen"]


def test_types_flag_adds_metadata():
    apps = clixml2json.load(SAMPLE, types=True)
    assert apps[0]["$type"] == "Example.Broker.Application"
    assert apps[0]["$tostring"] == "Banana Browser"
    assert apps[1]["$type"] == "Example.Broker.Application"  # via TNRef


def test_cli_prints_json(capsys):
    rc = clixml2json.main([str(SAMPLE), "--compact"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2 and data[0]["Priority"] == 3


def test_cli_unwrap_and_bad_input(tmp_path, capsys):
    one = tmp_path / "one.clixml"
    one.write_text(wrap('<Obj RefId="0"><MS><S N="N">solo</S></MS></Obj>'),
                   encoding="utf-8")
    assert clixml2json.main([str(one), "--unwrap"]) == 0
    assert json.loads(capsys.readouterr().out) == {"N": "solo"}

    bad = tmp_path / "bad.clixml"
    bad.write_text("not xml at all", encoding="utf-8")
    assert clixml2json.main([str(bad)]) == 2


def test_cli_output_file(tmp_path):
    out = tmp_path / "apps.json"
    assert clixml2json.main([str(SAMPLE), "-o", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))[1]["Enabled"] is False
