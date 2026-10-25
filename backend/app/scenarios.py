"""
Predefined, reproducible debugging scenarios used by PatchPilot's demo mode.

Each scenario is fully self-contained: buggy code, the error a user would see,
a deterministic root-cause explanation, a deterministic verified fix, and a
small test suite used to prove (or disprove) a proposed patch.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCase:
    name: str
    args: list[Any]
    expected: Any


@dataclass
class Scenario:
    id: str
    title: str
    short_description: str
    function_name: str
    buggy_code: str
    fixed_code: str
    sample_error_message: str
    root_cause: str
    explanation: str
    code_location: str
    edge_cases: str
    diff_summary: str
    tests: list[TestCase] = field(default_factory=list)


SCENARIOS: dict[str, Scenario] = {
    "division_by_zero": Scenario(
        id="division_by_zero",
        title="Division by Zero in Average Calculation",
        short_description="calculate_average() crashes on an empty list.",
        function_name="calculate_average",
        buggy_code='''def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)
''',
        fixed_code='''def calculate_average(numbers):
    if not numbers:
        return 0.0
    total = sum(numbers)
    return total / len(numbers)
''',
        sample_error_message="ZeroDivisionError: division by zero",
        root_cause=(
            "calculate_average() divides the sum of the list by its length "
            "without first checking whether the list is empty. When "
            "numbers is [], len(numbers) is 0, so the division raises "
            "ZeroDivisionError."
        ),
        code_location="Line 3: return total / len(numbers)",
        explanation=(
            "Add a guard clause that returns a safe default (0.0) when the "
            "input list is empty, before the division ever runs. This "
            "avoids the crash while keeping normal-case behavior unchanged."
        ),
        edge_cases=(
            "Empty list (the reported bug), a single-element list, and "
            "lists containing negative numbers should all be checked."
        ),
        diff_summary=(
            "Inserted an early-return guard (`if not numbers: return 0.0`) "
            "before the division. No other logic changed."
        ),
        tests=[
            TestCase("empty list", [[]], 0.0),
            TestCase("single element", [[5]], 5.0),
            TestCase("positive numbers", [[2, 4, 6]], 4.0),
            TestCase("mixed sign numbers", [[-2, 2, 4]], 4 / 3),
        ],
    ),
    "off_by_one": Scenario(
        id="off_by_one",
        title="Off-by-One Error in Range Sum",
        short_description="sum_range() excludes the upper bound, under-counting by n.",
        function_name="sum_range",
        buggy_code='''def sum_range(n):
    total = 0
    for i in range(n):
        total += i
    return total
''',
        fixed_code='''def sum_range(n):
    total = 0
    for i in range(n + 1):
        total += i
    return total
''',
        sample_error_message=(
            "sum_range(5) returned 10, expected 15 "
            "(sum of integers from 0 to 5 inclusive)"
        ),
        root_cause=(
            "range(n) produces 0, 1, ..., n-1 — it stops one short of n. "
            "The function is intended to sum all integers from 0 up to and "
            "including n, so the loop silently drops the final term."
        ),
        code_location="Line 3: for i in range(n):",
        explanation=(
            "Change range(n) to range(n + 1) so the loop includes n itself. "
            "This is a classic off-by-one bug: the fix is a single-token "
            "change, but it changes the result for every input."
        ),
        edge_cases=(
            "n = 0 should return 0, and negative n should return 0 "
            "(range(n + 1) becomes empty when n is negative)."
        ),
        diff_summary="Changed `range(n)` to `range(n + 1)` on the loop line only.",
        tests=[
            TestCase("n = 5", [5], 15),
            TestCase("n = 0", [0], 0),
            TestCase("n = 1", [1], 1),
            TestCase("n = 10", [10], 55),
        ],
    ),
    "boundary_case": Scenario(
        id="boundary_case",
        title="Incorrect Result on All-Negative Input",
        short_description="find_max() returns 0 instead of the true maximum for all-negative lists.",
        function_name="find_max",
        buggy_code='''def find_max(numbers):
    max_val = 0
    for n in numbers:
        if n > max_val:
            max_val = n
    return max_val
''',
        fixed_code='''def find_max(numbers):
    if not numbers:
        raise ValueError("find_max() arg is an empty sequence")
    max_val = numbers[0]
    for n in numbers[1:]:
        if n > max_val:
            max_val = n
    return max_val
''',
        sample_error_message=(
            "find_max([-5, -2, -9]) returned 0, expected -2"
        ),
        root_cause=(
            "max_val is initialized to 0 instead of the first element of "
            "the list. When every number in the input is negative, none of "
            "them is ever greater than the initial 0, so the function "
            "incorrectly returns 0 — a value that was never in the input."
        ),
        code_location="Line 2: max_val = 0",
        explanation=(
            "Initialize max_val to numbers[0] instead of a hardcoded 0, and "
            "iterate over the remaining elements. An empty-list guard is "
            "also added since indexing numbers[0] would otherwise raise an "
            "IndexError."
        ),
        edge_cases=(
            "All-negative lists (the reported bug), an empty list, and a "
            "single-element list."
        ),
        diff_summary=(
            "Changed the initial value of max_val from 0 to numbers[0], "
            "iterate over numbers[1:], and added an empty-list guard that "
            "raises ValueError (matching Python's built-in max() behavior)."
        ),
        tests=[
            TestCase("all negative", [[-5, -2, -9]], -2),
            TestCase("mixed sign", [[-5, 3, -9]], 3),
            TestCase("single element", [[-7]], -7),
            TestCase("all positive", [[1, 2, 3]], 3),
        ],
    ),
}


def get_scenario(scenario_id: str) -> Scenario | None:
    return SCENARIOS.get(scenario_id)


def list_scenarios() -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.title,
            "short_description": s.short_description,
            "function_name": s.function_name,
            "buggy_code": s.buggy_code,
            "sample_error_message": s.sample_error_message,
        }
        for s in SCENARIOS.values()
    ]
