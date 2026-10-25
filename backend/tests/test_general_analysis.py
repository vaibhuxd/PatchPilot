import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis import _strip_code_fences, _validate_general_payload


def _valid_payload(**overrides):
    base = {
        "root_cause": "The loop uses range(n) which excludes n.",
        "code_location": "Line 3",
        "explanation": "Use range(n + 1) instead.",
        "edge_cases": "n = 0 and negative n.",
        "function_name": "sum_range",
        "proposed_code": "def sum_range(n):\n    total = 0\n    for i in range(n + 1):\n        total += i\n    return total\n",
        "diff_summary": "Changed range(n) to range(n + 1).",
        "suggested_tests": [{"name": "n=5", "args": [5], "expected": 15}],
    }
    base.update(overrides)
    return base


def test_strip_code_fences_removes_markdown():
    assert _strip_code_fences("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    assert _strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_valid_payload_passes():
    validated, reason = _validate_general_payload(_valid_payload())
    assert reason is None
    assert validated is not None
    assert validated["function_name"] == "sum_range"
    assert len(validated["suggested_tests"]) == 1


def test_missing_required_key_rejected():
    payload = _valid_payload()
    del payload["root_cause"]
    validated, reason = _validate_general_payload(payload)
    assert validated is None
    assert reason is not None


def test_proposed_code_must_parse():
    validated, reason = _validate_general_payload(_valid_payload(proposed_code="def broken(:\n  pass"))
    assert validated is None
    assert "parse" in (reason or "").lower()


def test_function_name_must_exist_in_proposed_code():
    validated, reason = _validate_general_payload(
        _valid_payload(function_name="not_defined_anywhere")
    )
    assert validated is None
    assert "define" in (reason or "").lower()


def test_function_name_must_be_identifier():
    validated, reason = _validate_general_payload(_valid_payload(function_name="not a name!"))
    assert validated is None


def test_honest_decline_when_no_fix_identified():
    payload = _valid_payload(function_name=None, proposed_code=None, suggested_tests=[])
    validated, reason = _validate_general_payload(payload)
    assert reason is None
    assert validated is not None
    assert validated["function_name"] is None
    assert validated["proposed_code"] is None


def test_malformed_test_cases_are_dropped_not_fatal():
    payload = _valid_payload(
        suggested_tests=[
            {"name": "ok", "args": [1], "expected": 1},
            {"name": "bad, missing args"},
            "not even a dict",
        ]
    )
    validated, reason = _validate_general_payload(payload)
    assert reason is None
    assert len(validated["suggested_tests"]) == 1


def test_too_many_tests_are_truncated():
    payload = _valid_payload(
        suggested_tests=[{"name": f"t{i}", "args": [i], "expected": i} for i in range(20)]
    )
    validated, reason = _validate_general_payload(payload)
    assert reason is None
    assert len(validated["suggested_tests"]) <= 6
