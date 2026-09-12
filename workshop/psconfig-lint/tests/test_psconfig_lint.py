import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psconfig_lint import lint_text, main, scan_syntax  # noqa: E402


def msgs(text, level=None):
    fs = lint_text(text)
    return [f.message for f in fs if level is None or f.level == level]


def test_clean_config_has_no_findings():
    text = json.dumps({
        "DisableImplicitWinCompat": True,
        "ExecutionPolicy": "RemoteSigned",
        "ExperimentalFeatures": ["PSCommandNotFoundSuggestion"],
    }, indent=2)
    assert lint_text(text) == []


def test_trailing_comma_is_error_with_line():
    text = '{\n  "DisableImplicitWinCompat": true,\n}\n'
    fs = scan_syntax(text)
    assert fs and fs[0].level == "error"
    assert fs[0].line == 2 and "trailing comma" in fs[0].message


def test_comments_are_rejected():
    text = '{\n  // turn off the compat session\n  "DisableImplicitWinCompat": true\n}'
    assert any("comment" in m for m in msgs(text, "error"))


def test_comma_inside_string_is_not_a_trailing_comma():
    text = '{"LogChannels": "Operational,Analytic"}'
    assert lint_text(text) == []


def test_case_sensitive_key_typo():
    text = '{"disableImplicitWinCompat": true}'
    errs = msgs(text, "error")
    assert any("case-sensitive" in m for m in errs)


def test_close_typo_gets_suggestion():
    text = '{"DisableImplicitWinCompt": true}'
    assert any("did you mean 'DisableImplicitWinCompat'" in m
               for m in msgs(text))


def test_wrong_type_for_boolean():
    text = '{"DisableImplicitWinCompat": "true"}'
    assert any("must be true or false" in m for m in msgs(text, "error"))


def test_bad_execution_policy_value():
    text = '{"ExecutionPolicy": "RemotSigned"}'
    errs = msgs(text, "error")
    assert any("RemoteSigned" in m for m in errs)


def test_scoped_execution_policy_key_is_known():
    text = '{"Microsoft.PowerShell:ExecutionPolicy": "Bypass"}'
    assert lint_text(text) == []


def test_deny_list_must_be_array_of_strings():
    text = '{"WindowsPowerShellCompatibilityModuleDenyList": "PSScheduledJob"}'
    assert any("array of strings" in m for m in msgs(text, "error"))


def test_empty_array_warns():
    text = '{"ExperimentalFeatures": []}'
    assert any("no effect" in m for m in msgs(text, "warning"))


def test_psmodulepath_variable_warning():
    text = '{"PSModulePath": "%USERPROFILE%\\\\Modules"}'
    assert any("not expanded" in m for m in msgs(text, "warning"))


def test_duplicate_key_detected():
    text = '{"LogLevel": "Verbose", "LogLevel": "Debug"}'
    assert any("duplicate key" in m for m in msgs(text, "error"))


def test_bad_log_channel_value():
    text = '{"LogChannels": "Operational,Loud"}'
    assert any("unknown value 'Loud'" in m for m in msgs(text, "error"))


def test_top_level_must_be_object():
    assert any("top level" in m for m in msgs('["nope"]', "error"))


def test_broken_json_reports_line():
    fs = lint_text('{\n  "LogLevel": \n}')
    assert any(f.level == "error" and "invalid JSON" in f.message for f in fs)


def test_bom_is_warning_but_parses():
    text = '﻿{"DisableImplicitWinCompat": true}'
    assert [f.level for f in lint_text(text)] == ["warning"]


def test_filename_warning():
    fs = lint_text('{}', name="pwsh.config.json")
    assert any("only reads" in f.message for f in fs)


def test_main_requires_arguments():
    assert main([]) == 2
