import json

import pytest

import licensedrift as ld


@pytest.mark.parametrize("raw,expected", [
    ("MIT License", "MIT"),
    ("Business Source License 1.1", "BUSL-1.1"),
    ("Server Side Public License, v 1", "SSPL-1.0"),
    ("Elastic License 2.0", "Elastic-2.0"),
    ("Apache Software License, Version 2.0", "Apache-2.0"),
    ("GNU Affero General Public License v3", "AGPL-3.0"),
    ("BSD 3-Clause", "BSD-3-Clause"),
    ("", "UNKNOWN"),
    (None, "UNKNOWN"),
    ("UNKNOWN", "UNKNOWN"),
])
def test_normalize_license(raw, expected):
    assert ld.normalize_license(raw) == expected


def test_normalize_does_not_see_mit_inside_limited():
    assert ld.normalize_license("Commercial, limited use") != "MIT"


def test_normalize_drops_long_license_text():
    assert ld.normalize_license("blah " * 100) == "UNKNOWN"


def test_extract_prefers_expression_then_classifier_then_field():
    assert ld.extract_license(expression="MIT", license_field="Apache-2.0") == "MIT"
    assert ld.extract_license(
        classifiers=["Programming Language :: Python",
                     "License :: OSI Approved :: Apache Software License"],
        license_field="see LICENSE") == "Apache-2.0"
    assert ld.extract_license(license_field="ISC") == "ISC"
    assert ld.extract_license(classifiers=["License :: OSI Approved"]) == "UNKNOWN"
    assert ld.extract_license(
        classifiers=["License :: Other/Proprietary License"]) == "Proprietary"


def _pkg(version, license_):
    return {"version": version, "license": license_}


def test_diff_detects_nothing_when_identical():
    state = {"rich": _pkg("13.7.0", "MIT")}
    assert ld.diff(state, dict(state)) == []


def test_diff_detects_relicensing_and_alarms():
    old = {"sneaky": _pkg("1.0.0", "Apache-2.0")}
    new = {"sneaky": _pkg("2.0.0", "BUSL-1.1")}
    changes = ld.diff(old, new)
    assert len(changes) == 1
    ch = changes[0]
    assert ch["kind"] == "license-change"
    assert ch["name"] == "sneaky@2.0.0"
    assert (ch["old"], ch["new"]) == ("Apache-2.0", "BUSL-1.1")
    assert ch["alarm"] is True
    assert ld.exit_code(changes) == 2


def test_diff_detects_added_and_removed():
    changes = ld.diff({"six": _pkg("1.16.0", "MIT")}, {"rich": _pkg("13.7.0", "MIT")})
    kinds = sorted(c["kind"] for c in changes)
    assert kinds == ["added", "removed"]
    assert ld.exit_code(changes) == 1


def test_version_bump_alone_is_not_drift():
    changes = ld.diff({"a": _pkg("1.0", "MIT")}, {"a": _pkg("1.1", "MIT")})
    assert changes == []
    assert ld.exit_code(changes) == 0


def test_format_report():
    assert "calm" in ld.format_report([])
    text = ld.format_report(ld.diff({"a": _pkg("1", "MIT")}, {"a": _pkg("2", "SSPL-1.0")}))
    assert "MIT -> SSPL-1.0" in text
    assert "source-available" in text


def test_snapshot_roundtrip(tmp_path):
    path = tmp_path / "licenses.json"
    packages = {"rich": _pkg("13.7.0", "MIT")}
    ld.save_snapshot(str(path), packages)
    body = json.loads(path.read_text())
    assert body["tool"] == "license-drift"
    assert ld.load_snapshot(str(path)) == packages


def test_load_snapshot_accepts_bare_mapping(tmp_path):
    path = tmp_path / "bare.json"
    path.write_text(json.dumps({"rich": _pkg("13.7.0", "MIT")}))
    assert "rich" in ld.load_snapshot(str(path))


def test_cli_snapshot_then_clean_check(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    packages = {"rich": _pkg("13.7.0", "MIT")}
    assert ld.main(["snapshot", path], current=packages) == 0
    assert ld.main(["check", path], current=packages) == 0
    assert "calm" in capsys.readouterr().out


def test_cli_check_reports_drift_and_can_update(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"orm": _pkg("1.0", "Apache-2.0")})
    drifted = {"orm": _pkg("2.0", "BUSL-1.1")}
    assert ld.main(["check", path], current=drifted) == 2
    assert ld.main(["check", path, "--update"], current=drifted) == 2
    assert ld.main(["check", path], current=drifted) == 0
    capsys.readouterr()


def test_cli_missing_snapshot_is_usage_error(tmp_path, capsys):
    code = ld.main(["check", str(tmp_path / "nope.json")], current={})
    assert code == 3
    assert "no snapshot" in capsys.readouterr().err


def test_cli_list(capsys):
    assert ld.main(["list"], current={"rich": _pkg("13.7.0", "MIT")}) == 0
    assert "rich" in capsys.readouterr().out


def test_read_installed_returns_mapping():
    packages = ld.read_installed()
    assert isinstance(packages, dict)
    for info in packages.values():
        assert "version" in info and "license" in info
