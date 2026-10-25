from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import sandbox
from .analysis import ai_enabled, analyze_arbitrary, generate_explanation
from .scenarios import get_scenario, list_scenarios

app = FastAPI(title="PatchPilot API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo deployment; restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_CODE_CHARS = 20_000
MAX_CUSTOM_TESTS = 6


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_mode": "llm" if ai_enabled() else "demo"}


@app.get("/api/scenarios")
def get_scenarios():
    return {"scenarios": list_scenarios()}


class AnalyzeRequest(BaseModel):
    scenario_id: str | None = None
    code: str = ""
    error_message: str = ""


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    scenario = get_scenario(req.scenario_id) if req.scenario_id else None

    # --- Scenario mode: fix & tests are always the pre-verified scenario
    # data. An AI key, if configured, only augments the explanation text.
    if scenario is not None:
        explanation, mode = await generate_explanation(scenario, req.error_message)
        return {
            "supported": True,
            "mode": "scenario",
            "scenario_id": scenario.id,
            "title": scenario.title,
            "root_cause": scenario.root_cause,
            "code_location": scenario.code_location,
            "explanation": explanation,
            "edge_cases": scenario.edge_cases,
            "function_name": scenario.function_name,
            "proposed_code": None,  # fetched via /api/propose for this mode
            "diff_summary": None,
            "suggested_tests": None,
            "analysis_mode": mode,  # "llm" or "demo"
        }

    # --- General mode: arbitrary pasted code, no preset selected.
    code = (req.code or "").strip()
    if not code:
        return {
            "supported": False,
            "mode": "general",
            "message": "Paste some Python code (and, if you have one, an error message) before analyzing.",
        }
    if len(code) > MAX_CODE_CHARS:
        return {
            "supported": False,
            "mode": "general",
            "message": f"That's more code than this build can analyze at once ({MAX_CODE_CHARS:,} character limit).",
        }

    if not ai_enabled():
        return {
            "supported": False,
            "mode": "general",
            "analysis_mode": "demo",
            "message": (
                "This build is running in Demo Mode (no Anthropic API key configured on "
                "the server), so free-form analysis of your own code isn't available. "
                "Demo Mode fully supports the three sample scenarios below — try one of "
                "those, or configure ANTHROPIC_API_KEY on the backend for real analysis "
                "of your own code (see README)."
            ),
        }

    result, failure_reason = await analyze_arbitrary(code, req.error_message)
    if result is None:
        return {
            "supported": False,
            "mode": "general",
            "analysis_mode": "llm",
            "message": failure_reason or "AI analysis failed for an unknown reason.",
        }

    has_fix = result["function_name"] is not None and result["proposed_code"] is not None
    return {
        "supported": True,
        "mode": "general",
        "scenario_id": None,
        "title": "Custom code analysis",
        "root_cause": result["root_cause"],
        "code_location": result["code_location"],
        "explanation": result["explanation"],
        "edge_cases": result["edge_cases"],
        "function_name": result["function_name"],
        "proposed_code": result["proposed_code"],
        "diff_summary": result["diff_summary"],
        "suggested_tests": result["suggested_tests"],
        "analysis_mode": "llm",
        "fix_available": has_fix,
        "original_code": code,
    }


class ProposeRequest(BaseModel):
    scenario_id: str


@app.post("/api/propose")
def propose(req: ProposeRequest):
    """Fetch the deterministic proposed fix for a built-in scenario.

    General-mode (arbitrary code) fixes are returned directly by
    /api/analyze and don't need a second round trip here.
    """
    scenario = get_scenario(req.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Unknown scenario_id")

    return {
        "scenario_id": scenario.id,
        "original_code": scenario.buggy_code,
        "proposed_code": scenario.fixed_code,
        "diff_summary": scenario.diff_summary,
        "status": "proposed",  # proposed | untested | passed | failed
    }


class CustomTest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    args: list[Any] = Field(default_factory=list, max_length=8)
    expected: Any = None


class TestRequest(BaseModel):
    scenario_id: str | None = None
    code: str  # the code the user wants to test (original or proposed)
    function_name: str | None = None
    tests: list[CustomTest] | None = None


def _blocked_response(message: str, total: int = 0) -> dict:
    return {
        "status": "error",
        "ran": False,
        "sandbox_error": message,
        "stderr": "",
        "results": [],
        "total": total,
        "passed_count": 0,
        "failed_count": 0,
    }


@app.post("/api/test")
def run_tests(req: TestRequest):
    # --- Preset scenario path: known function + known, pre-verified tests.
    if req.scenario_id:
        scenario = get_scenario(req.scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="Unknown scenario_id")
        function_name = scenario.function_name
        tests_payload = [{"name": t.name, "args": t.args, "expected": t.expected} for t in scenario.tests]

    # --- General path: caller supplies the function name + AI-suggested
    # tests that /api/analyze already validated. We re-validate here too,
    # since this endpoint is a separate trust boundary.
    else:
        if not req.function_name or not req.tests:
            return _blocked_response(
                "No verification tests are available for this code. PatchPilot can only "
                "run tests it (or the configured AI) generated for a specific function — "
                "select a sample scenario, or analyze your code first so a function name "
                "and test cases can be identified."
            )
        if len(req.tests) > MAX_CUSTOM_TESTS:
            return _blocked_response(f"Too many test cases (max {MAX_CUSTOM_TESTS}).")
        if len(req.code) > MAX_CODE_CHARS:
            return _blocked_response("Code is too large to test in this build.")

        function_name = req.function_name
        tests_payload = [{"name": t.name, "args": t.args, "expected": t.expected} for t in req.tests]

    report = sandbox.run_tests(req.code, function_name, tests_payload)

    if not report.ran:
        return {
            "status": "error",
            "ran": False,
            "sandbox_error": report.sandbox_error,
            "stderr": report.stderr,
            "results": [],
            "total": len(tests_payload),
            "passed_count": 0,
            "failed_count": 0,
        }

    passed_count = sum(1 for r in report.results if r.passed)
    failed_count = len(report.results) - passed_count
    overall_status = "passed" if failed_count == 0 and passed_count > 0 else "failed"

    return {
        "status": overall_status,  # passed | failed
        "ran": True,
        "sandbox_error": None,
        "stderr": report.stderr,
        "total": len(report.results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "expected": r.expected,
                "actual": r.actual,
                "error": r.error,
            }
            for r in report.results
        ],
    }
