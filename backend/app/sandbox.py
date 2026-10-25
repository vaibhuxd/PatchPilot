"""
Best-effort isolated execution for running PatchPilot's test suites against
user-submitted code.

HONEST LIMITATION: this process does not have access to a container runtime
(e.g. Docker/gVisor) in the hackathon deployment environment. What is
implemented here is defense-in-depth, not a true security boundary:

  1. A static AST check that rejects dangerous imports and calls
     (os, sys, subprocess, socket, shutil, open, eval, exec, __import__, ...)
     before anything is ever executed.
  2. Execution in a separate OS process (subprocess), never inside the
     FastAPI server process.
  3. A hard wall-clock timeout.
  4. POSIX resource limits on CPU time, memory, and output size (Linux only;
     skipped gracefully on platforms without the `resource` module).
  5. No network access is granted beyond what the host process already has
     restricted (the harness itself opens no sockets).

For a production deployment handling fully arbitrary, adversarial code, this
should be replaced with a real sandboxing layer (gVisor, Firecracker, a
locked-down container, or a managed code-execution API). This limitation is
called out in the README and in the UI.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_SECONDS = 5
MAX_OUTPUT_BYTES = 64_000

FORBIDDEN_NAMES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "importlib",
    "ctypes",
    "multiprocessing",
    "threading",
    "requests",
    "urllib",
    "http",
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "exit",
    "quit",
}


class UnsafeCodeError(Exception):
    pass


def static_safety_check(code: str) -> None:
    """Reject obviously dangerous code before it is ever executed."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise UnsafeCodeError(f"Code does not parse: {e}") from e

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            else:
                if node.module:
                    names = [node.module.split(".")[0]]
            for n in names:
                if n in FORBIDDEN_NAMES:
                    raise UnsafeCodeError(f"Import of '{n}' is not allowed in the sandbox.")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise UnsafeCodeError(f"Use of '{node.id}' is not allowed in the sandbox.")
        if isinstance(node, ast.Attribute) and node.attr in {"system", "popen", "remove", "rmdir", "unlink"}:
            raise UnsafeCodeError(f"Use of '.{node.attr}(...)' is not allowed in the sandbox.")


def _resource_preexec():
    try:
        import resource

        cpu_seconds = TIMEOUT_SECONDS + 1
        mem_bytes = 256 * 1024 * 1024  # 256 MB
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
        resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
    except Exception:
        # Not available on this platform (e.g. non-POSIX) — timeout + AST
        # checks still apply.
        pass


@dataclass
class TestResult:
    name: str
    passed: bool
    expected: str
    actual: str
    error: str | None = None


@dataclass
class ExecutionReport:
    ran: bool
    results: list[TestResult]
    stderr: str = ""
    sandbox_error: str | None = None


_RUNNER_TEMPLATE = '''
import json
import sys

{user_code}

_tests = {tests_json}
_function_name = {function_name!r}
_results = []

_fn = globals().get(_function_name)
if _fn is None:
    print(json.dumps({{"__harness_error__": f"Function '{{_function_name}}' was not defined."}}))
    sys.exit(0)

for _t in _tests:
    _name = _t["name"]
    _args = _t["args"]
    _expected = _t["expected"]
    try:
        _actual = _fn(*_args)
        _passed = _actual == _expected
        _results.append({{
            "name": _name,
            "passed": _passed,
            "expected": repr(_expected),
            "actual": repr(_actual),
            "error": None,
        }})
    except Exception as e:
        _results.append({{
            "name": _name,
            "passed": False,
            "expected": repr(_expected),
            "actual": "",
            "error": f"{{type(e).__name__}}: {{e}}",
        }})

print(json.dumps({{"results": _results}}))
'''


def run_tests(code: str, function_name: str, tests: list[dict]) -> ExecutionReport:
    """Run `tests` against `function_name` defined in `code`, isolated in a
    subprocess with a timeout and resource limits."""
    try:
        static_safety_check(code)
    except UnsafeCodeError as e:
        return ExecutionReport(ran=False, results=[], sandbox_error=str(e))

    runner_source = _RUNNER_TEMPLATE.format(
        user_code=textwrap.indent(code, ""),
        tests_json=json.dumps(tests),
        function_name=function_name,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "harness.py"
        script_path.write_text(runner_source)

        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", str(script_path)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
                preexec_fn=_resource_preexec if sys.platform != "win32" else None,
            )
        except subprocess.TimeoutExpired:
            return ExecutionReport(
                ran=False,
                results=[],
                sandbox_error=f"Execution exceeded the {TIMEOUT_SECONDS}s timeout and was terminated.",
            )

        stdout = proc.stdout[-MAX_OUTPUT_BYTES:]
        stderr = proc.stderr[-MAX_OUTPUT_BYTES:]

        if proc.returncode != 0 and not stdout.strip():
            return ExecutionReport(
                ran=False,
                results=[],
                stderr=stderr,
                sandbox_error="The submitted code failed to run (see stderr).",
            )

        try:
            payload = json.loads(stdout.strip().splitlines()[-1])
        except Exception:
            return ExecutionReport(
                ran=False,
                results=[],
                stderr=stderr,
                sandbox_error="Could not parse test harness output.",
            )

        if "__harness_error__" in payload:
            return ExecutionReport(ran=False, results=[], sandbox_error=payload["__harness_error__"])

        results = [
            TestResult(
                name=r["name"],
                passed=r["passed"],
                expected=r["expected"],
                actual=r["actual"],
                error=r.get("error"),
            )
            for r in payload["results"]
        ]
        return ExecutionReport(ran=True, results=results, stderr=stderr)
