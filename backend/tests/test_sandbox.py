import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import sandbox
from app.scenarios import SCENARIOS


def test_buggy_code_fails_for_each_scenario():
    """Each scenario's buggy_code must fail at least one test (proves the
    'bug' is real and reproducible, not just asserted in prose)."""
    for scenario in SCENARIOS.values():
        tests = [{"name": t.name, "args": t.args, "expected": t.expected} for t in scenario.tests]
        report = sandbox.run_tests(scenario.buggy_code, scenario.function_name, tests)
        assert report.ran, f"{scenario.id}: buggy code should at least run, got {report.sandbox_error}"
        failed = [r for r in report.results if not r.passed]
        assert failed, f"{scenario.id}: expected the buggy code to fail at least one test"


def test_fixed_code_passes_every_scenario():
    """Each scenario's fixed_code must pass all of its own tests."""
    for scenario in SCENARIOS.values():
        tests = [{"name": t.name, "args": t.args, "expected": t.expected} for t in scenario.tests]
        report = sandbox.run_tests(scenario.fixed_code, scenario.function_name, tests)
        assert report.ran, f"{scenario.id}: fixed code failed to run: {report.sandbox_error}"
        failed = [r for r in report.results if not r.passed]
        assert not failed, f"{scenario.id}: fixed code failed tests: {failed}"


def test_static_safety_check_blocks_dangerous_imports():
    for bad in ["import os", "import subprocess", "from socket import socket", "eval('1')"]:
        try:
            sandbox.static_safety_check(bad)
            assert False, f"expected UnsafeCodeError for: {bad}"
        except sandbox.UnsafeCodeError:
            pass


def test_timeout_is_enforced():
    scenario = SCENARIOS["division_by_zero"]
    infinite_loop_code = "def calculate_average(numbers):\n    while True:\n        pass\n"
    tests = [{"name": "x", "args": [[1, 2]], "expected": 1.5}]
    report = sandbox.run_tests(infinite_loop_code, scenario.function_name, tests)
    assert not report.ran
    assert "timeout" in (report.sandbox_error or "").lower()


def test_missing_function_reports_cleanly():
    scenario = SCENARIOS["off_by_one"]
    tests = [{"name": "t", "args": [5], "expected": 15}]
    report = sandbox.run_tests("def not_the_right_name():\n    return 1\n", scenario.function_name, tests)
    assert not report.ran
    assert "was not defined" in (report.sandbox_error or "")


def test_syntax_error_reports_cleanly():
    scenario = SCENARIOS["off_by_one"]
    tests = [{"name": "t", "args": [5], "expected": 15}]
    report = sandbox.run_tests("def sum_range(n:\n    pass", scenario.function_name, tests)
    assert not report.ran
    assert report.sandbox_error is not None
