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


@pytest.mark.parametrize("raw,expected", [
    ("MIT OR Apache-2.0", "Apache-2.0 OR MIT"),
    ("Apache-2.0 OR MIT", "Apache-2.0 OR MIT"),
    ("MIT AND Python-2.0", "MIT AND PSF-2.0"),
    ("Apache-2.0 WITH Commons-Clause", "Apache-2.0 WITH Commons-Clause"),
    ("(MIT OR Apache-2.0)", "Apache-2.0 OR MIT"),
    ("MIT or MIT", "MIT"),
])
def test_normalize_handles_spdx_expressions(raw, expected):
    assert ld.normalize_license(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # prose that merely contains "or" / "with" must not be parsed as SPDX
    ("GNU General Public License v2 or later", "GPL"),
    ("MIT License and free to use with attribution", "MIT"),
    ("Apache License 2.0 with LLVM exception", "Apache-2.0"),
])
def test_prose_is_not_mistaken_for_an_expression(raw, expected):
    assert ld.normalize_license(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("typing_extensions", "typing-extensions"),
    ("Typing.Extensions", "typing-extensions"),
    ("ruamel.yaml", "ruamel-yaml"),
    ("zope..interface", "zope-interface"),
    ("  Rich ", "rich"),
])
def test_normalize_name(raw, expected):
    assert ld.normalize_name(raw) == expected


@pytest.mark.parametrize("tag,expected", [
    ("MIT", False),
    ("BUSL-1.1", True),
    ("Commons-Clause", True),
    # an OR keeps a permissive escape hatch open
    ("BUSL-1.1 OR MIT", False),
    ("BUSL-1.1 OR SSPL-1.0", True),
    # AND / WITH stack obligations: any restrictive part is restrictive
    ("Apache-2.0 WITH Commons-Clause", True),
    ("MIT AND Proprietary", True),
    ("Apache-2.0 OR MIT", False),
    # copyleft is drift, not an alarm, unless you ask for it
    ("AGPL-3.0", False),
    ("UNKNOWN", False),
    ("", False),
])
def test_is_restrictive(tag, expected):
    assert ld.is_restrictive(tag) is expected


@pytest.mark.parametrize("values,expected", [
    (["AGPL-3.0"], {"AGPL-3.0"}),
    (["agpl, gpl"], {"AGPL-3.0", "GPL"}),
    (["GNU Affero", "UNKNOWN"], {"AGPL-3.0", "UNKNOWN"}),
    (["  ", ""], set()),
    (None, set()),
])
def test_parse_alarm_tags(values, expected):
    assert ld.parse_alarm_tags(values) == expected


def test_is_restrictive_honours_a_custom_policy():
    policy = ld.RESTRICTIVE | {"AGPL-3.0"}
    assert ld.is_restrictive("AGPL-3.0", policy) is True
    assert ld.is_restrictive("MIT AND AGPL-3.0", policy) is True
    # a dual license still leaves you an out
    assert ld.is_restrictive("AGPL-3.0 OR MIT", policy) is False
    # the built-ins are still in there
    assert ld.is_restrictive("BUSL-1.1", policy) is True
    assert ld.is_restrictive("MIT", policy) is False


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


def test_diff_ignores_name_punctuation_and_case():
    old = {"Typing_Extensions": _pkg("4.9.0", "PSF-2.0"),
           "ruamel.yaml": _pkg("0.18.5", "MIT")}
    new = {"typing-extensions": _pkg("4.9.0", "PSF-2.0"),
           "ruamel-yaml": _pkg("0.18.5", "MIT")}
    assert ld.diff(old, new) == []


def test_diff_still_sees_a_relicense_under_a_respelled_name():
    old = {"sneaky.orm": _pkg("1.0", "Apache-2.0")}
    new = {"sneaky-orm": _pkg("2.0", "BUSL-1.1")}
    changes = ld.diff(old, new)
    assert len(changes) == 1
    assert changes[0]["kind"] == "license-change"
    assert changes[0]["name"] == "sneaky-orm@2.0"


def test_change_records_split_package_and_version():
    ch = ld.diff({"orm": _pkg("1.0", "MIT")}, {"orm": _pkg("2.0", "BUSL-1.1")})[0]
    assert ch["package"] == "orm"
    assert ch["version"] == "2.0"
    assert ch["name"] == "orm@2.0"
    removed = ld.diff({"six": _pkg("1.16.0", "MIT")}, {})[0]
    assert (removed["package"], removed["version"]) == ("six", "1.16.0")


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


def test_diff_alarms_on_quiet_commons_clause_bolt_on():
    old = {"tidy": _pkg("1.0", ld.normalize_license("Apache-2.0"))}
    new = {"tidy": _pkg("1.1", ld.normalize_license("Apache-2.0 WITH Commons-Clause"))}
    changes = ld.diff(old, new)
    assert changes[0]["new"] == "Apache-2.0 WITH Commons-Clause"
    assert ld.exit_code(changes) == 2


def test_diff_applies_a_custom_policy_to_added_packages():
    policy = ld.RESTRICTIVE | {"AGPL-3.0"}
    added = ld.diff({}, {"copyleft": _pkg("1.0", "AGPL-3.0")}, policy)[0]
    assert added["kind"] == "added" and added["alarm"] is True
    assert ld.diff({}, {"copyleft": _pkg("1.0", "AGPL-3.0")})[0]["alarm"] is False


def test_dual_licensed_package_is_drift_but_not_an_alarm():
    old = {"dual": _pkg("1.0", ld.normalize_license("MIT"))}
    new = {"dual": _pkg("2.0", ld.normalize_license("MIT OR BUSL-1.1"))}
    changes = ld.diff(old, new)
    assert changes[0]["new"] == "BUSL-1.1 OR MIT"
    assert changes[0]["alarm"] is False
    assert ld.exit_code(changes) == 1


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


def test_format_report_labels_policy_alarms_separately():
    policy = ld.RESTRICTIVE | {"AGPL-3.0"}
    text = ld.format_report(
        ld.diff({"a": _pkg("1", "MIT")}, {"a": _pkg("2", "AGPL-3.0")}, policy))
    assert "[policy]" in text
    assert "source-available" not in text


def test_build_report_shape():
    changes = ld.diff({"a": _pkg("1", "MIT")}, {"a": _pkg("2", "SSPL-1.0")})
    report = ld.build_report(changes, "licenses.json")
    assert report["tool"] == "license-drift"
    assert report["snapshot"] == "licenses.json"
    assert report["alarms"] == 1
    assert report["exit_code"] == 2
    assert report["snapshot_updated"] is False
    assert report["changes"] == changes
    assert report["alarm_on"] == sorted(ld.RESTRICTIVE)


def test_snapshot_roundtrip(tmp_path):
    path = tmp_path / "licenses.json"
    packages = {"rich": _pkg("13.7.0", "MIT")}
    ld.save_snapshot(str(path), packages)
    body = json.loads(path.read_text())
    assert body["tool"] == "license-drift"
    assert ld.load_snapshot(str(path)) == packages


def test_snapshot_writes_normalised_names(tmp_path):
    path = tmp_path / "licenses.json"
    ld.save_snapshot(str(path), {"Typing_Extensions": _pkg("4.9.0", "PSF-2.0")})
    body = json.loads(path.read_text())
    assert list(body["packages"]) == ["typing-extensions"]


def test_load_snapshot_accepts_bare_mapping(tmp_path):
    path = tmp_path / "bare.json"
    path.write_text(json.dumps({"rich": _pkg("13.7.0", "MIT")}))
    assert "rich" in ld.load_snapshot(str(path))


def test_load_snapshot_normalises_legacy_names(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"packages": {"ruamel.yaml": _pkg("0.18.5", "MIT")}}))
    assert ld.load_snapshot(str(path)) == {"ruamel-yaml": _pkg("0.18.5", "MIT")}


def test_cli_snapshot_then_clean_check(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    packages = {"rich": _pkg("13.7.0", "MIT")}
    assert ld.main(["snapshot", path], current=packages) == 0
    assert ld.main(["check", path], current=packages) == 0
    assert "calm" in capsys.readouterr().out


def test_cli_check_is_quiet_across_a_name_respelling(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"ruamel.yaml": _pkg("0.18.5", "MIT")})
    assert ld.main(["check", path], current={"ruamel-yaml": _pkg("0.18.5", "MIT")}) == 0
    capsys.readouterr()


def test_cli_check_reports_drift_and_can_update(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"orm": _pkg("1.0", "Apache-2.0")})
    drifted = {"orm": _pkg("2.0", "BUSL-1.1")}
    assert ld.main(["check", path], current=drifted) == 2
    assert ld.main(["check", path, "--update"], current=drifted) == 2
    assert ld.main(["check", path], current=drifted) == 0
    capsys.readouterr()


def test_cli_alarm_on_blocks_copyleft(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"lib": _pkg("1.0", "MIT")})
    drifted = {"lib": _pkg("2.0", "AGPL-3.0")}
    assert ld.main(["check", path], current=drifted) == 1
    assert ld.main(["check", path, "--alarm-on", "agpl"], current=drifted) == 2
    assert "[policy]" in capsys.readouterr().out


def test_cli_alarm_on_unknown_catches_unreadable_metadata(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"lib": _pkg("1.0", "MIT")})
    drifted = {"lib": _pkg("1.0", "MIT"), "mystery": _pkg("0.1", "UNKNOWN")}
    assert ld.main(["check", path], current=drifted) == 1
    assert ld.main(["check", path, "--alarm-on", "UNKNOWN,GPL"], current=drifted) == 2
    capsys.readouterr()


def test_cli_alarm_on_is_repeatable_and_lands_in_the_json_report(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"lib": _pkg("1.0", "MIT")})
    capsys.readouterr()
    code = ld.main(["check", path, "--json", "--alarm-on", "AGPL-3.0",
                    "--alarm-on", "GPL,LGPL"], current={"lib": _pkg("2.0", "GPL")})
    body = json.loads(capsys.readouterr().out)
    assert code == 2 == body["exit_code"]
    assert body["alarms"] == 1
    assert set(body["alarm_on"]) == ld.RESTRICTIVE | {"AGPL-3.0", "GPL", "LGPL"}


def test_cli_check_json_is_pure_json_and_carries_the_exit_code(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"orm": _pkg("1.0", "Apache-2.0")})
    capsys.readouterr()
    code = ld.main(["check", path, "--json"], current={"orm": _pkg("2.0", "BUSL-1.1")})
    body = json.loads(capsys.readouterr().out)
    assert code == 2 == body["exit_code"]
    assert body["alarms"] == 1
    assert body["snapshot"] == path
    assert body["snapshot_updated"] is False
    change = body["changes"][0]
    assert change["package"] == "orm"
    assert (change["old"], change["new"]) == ("Apache-2.0", "BUSL-1.1")
    assert change["alarm"] is True


def test_cli_check_json_clean_run_has_no_changes(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    packages = {"rich": _pkg("13.7.0", "MIT")}
    ld.main(["snapshot", path], current=packages)
    capsys.readouterr()
    assert ld.main(["check", path, "--json"], current=packages) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["changes"] == [] and body["alarms"] == 0


def test_cli_check_json_update_reports_the_rewrite(tmp_path, capsys):
    path = str(tmp_path / "licenses.json")
    ld.main(["snapshot", path], current={"orm": _pkg("1.0", "MIT")})
    capsys.readouterr()
    ld.main(["check", path, "--json", "--update"], current={"orm": _pkg("2.0", "ISC")})
    body = json.loads(capsys.readouterr().out)
    assert body["snapshot_updated"] is True
    assert ld.load_snapshot(path)["orm"]["license"] == "ISC"


def test_cli_list(capsys):
    assert ld.main(["list"], current={"Rich": _pkg("13.7.0", "MIT")}) == 0
    assert "rich" in capsys.readouterr().out


def test_cli_list_json_matches_a_snapshot_file(tmp_path, capsys):
    path = tmp_path / "licenses.json"
    packages = {"Rich": _pkg("13.7.0", "MIT")}
    assert ld.main(["list", "--json"], current=packages) == 0
    printed = json.loads(capsys.readouterr().out)
    ld.save_snapshot(str(path), packages)
    written = json.loads(path.read_text())
    assert printed["packages"] == written["packages"] == {"rich": _pkg("13.7.0", "MIT")}
    assert printed["tool"] == written["tool"]


def test_read_installed_returns_mapping():
    packages = ld.read_installed()
    assert isinstance(packages, dict)
    for name, info in packages.items():
        assert name == ld.normalize_name(name)
        assert "version" in info and "license" in info
