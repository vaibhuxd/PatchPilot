"""
Analysis provider adapter.

Two modes, always honestly labeled to the caller:

1. Scenario mode (the 3 built-in sample bugs): the fix and tests are always
   the deterministic, pre-verified data in scenarios.py. If an API key is
   configured, Claude is asked only to restate/augment the *explanation* in
   natural language — it never gets to change what fix is applied or what
   is tested.

2. General mode (arbitrary user-submitted code): only available when
   ANTHROPIC_API_KEY is configured. Claude is asked to diagnose the bug AND
   propose a fix AND propose test cases, returned as strict JSON. The
   response is validated (parses as JSON, has the required fields, the
   proposed code is syntactically valid Python, the named function actually
   exists in it, suggested tests are well-formed) before PatchPilot will
   show it or let it be executed. If validation fails, or no key is
   configured, PatchPilot says so plainly instead of fabricating a result.

The API key lives only in server-side environment variables and is never
sent to, or embedded in, the frontend.
"""

from __future__ import annotations

import ast
import json
import os
import re

import httpx

from .scenarios import Scenario

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

MAX_SUGGESTED_TESTS = 6


def ai_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)


async def generate_explanation(scenario: Scenario, user_error_message: str) -> tuple[str, str]:
    """Returns (explanation_text, mode) where mode is 'llm' or 'demo'."""
    if not ai_enabled():
        return _demo_explanation(scenario), "demo"

    prompt = (
        "You are PatchPilot, an AI debugging assistant. A user ran into this "
        f"bug:\n\nBuggy code:\n```python\n{scenario.buggy_code}\n```\n\n"
        f"Error / symptom reported by the user: {user_error_message or scenario.sample_error_message}\n\n"
        f"Known root cause: {scenario.root_cause}\n"
        f"Known fix location: {scenario.code_location}\n\n"
        "In 3-5 concise sentences, explain the root cause and why the fix "
        "below resolves it, for a developer audience. Do not suggest a "
        "different fix than the one shown.\n\n"
        f"Fix:\n```python\n{scenario.fixed_code}\n```"
    )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 400,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
            text = "\n".join(text_parts).strip()
            if text:
                return text, "llm"
            return _demo_explanation(scenario), "demo"
    except Exception:
        # Fail honestly to demo mode rather than fabricating a response.
        return _demo_explanation(scenario), "demo"


def _demo_explanation(scenario: Scenario) -> str:
    return (
        f"{scenario.root_cause} {scenario.explanation} "
        f"Edge cases to watch for: {scenario.edge_cases}"
    )


_GENERAL_SYSTEM_PROMPT = """You are PatchPilot, an AI debugging assistant embedded in a developer tool.
A user has pasted Python source code and an error message or description of unexpected behavior.

Respond with ONLY a single JSON object — no markdown code fences, no prose before or after it.
The JSON object must have exactly these keys:

{
  "root_cause": "1-3 sentences on why the bug happens",
  "code_location": "short description of the relevant line(s), e.g. 'Line 4: the division'",
  "explanation": "2-4 sentences explaining the fix and why it resolves the issue",
  "edge_cases": "1-2 sentences on edge cases worth checking",
  "function_name": "the name of the single top-level function being fixed, exactly as it appears in the code",
  "proposed_code": "the FULL corrected source, as a single string with real newline characters, preserving everything that wasn't buggy",
  "diff_summary": "1-2 sentences summarizing what changed, in plain language",
  "suggested_tests": [
    {"name": "short label", "args": [<positional args to pass to the function>], "expected": <expected return value>}
  ]
}

Rules:
- "suggested_tests" must contain between 1 and 4 test cases, each calling function_name with JSON-serializable
  arguments (numbers, strings, booleans, null, lists, objects) and an expected JSON-serializable return value.
  Only propose tests for pure functions with no I/O, randomness, network, or file access.
- If you cannot confidently identify a single fixable function, or the input isn't really a Python bug
  (e.g. it's not code, or the issue requires external context you don't have), set "root_cause" to a short
  honest explanation of why, set "function_name" and "proposed_code" to null, and set "suggested_tests" to [].
- Never invent facts about the user's environment, libraries, or data you cannot see.
- proposed_code must be syntactically valid, runnable Python 3, and must not import os, sys, subprocess,
  socket, shutil, or any networking/filesystem module, and must not call eval, exec, open, or __import__.
"""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    return match.group(1).strip() if match else text


def _validate_general_payload(payload: dict) -> tuple[dict | None, str | None]:
    """Returns (validated_payload, None) on success, or (None, reason) on failure."""
    required_keys = {
        "root_cause",
        "code_location",
        "explanation",
        "edge_cases",
        "function_name",
        "proposed_code",
        "diff_summary",
        "suggested_tests",
    }
    if not isinstance(payload, dict) or not required_keys.issubset(payload.keys()):
        return None, "The model response was missing required fields."

    for key in ("root_cause", "explanation"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            return None, f"The model response had an empty or invalid '{key}'."

    function_name = payload.get("function_name")
    proposed_code = payload.get("proposed_code")
    suggested_tests_raw = payload.get("suggested_tests")

    if function_name is None or proposed_code is None:
        # Model honestly declined to propose a fix — still a valid, usable response.
        return {
            "root_cause": payload["root_cause"],
            "code_location": str(payload.get("code_location") or "")[:500],
            "explanation": payload["explanation"],
            "edge_cases": str(payload.get("edge_cases") or "")[:500],
            "function_name": None,
            "proposed_code": None,
            "diff_summary": None,
            "suggested_tests": [],
        }, None

    if not isinstance(function_name, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", function_name):
        return None, "The model proposed an invalid function name."

    if not isinstance(proposed_code, str) or not proposed_code.strip():
        return None, "The model's proposed code was empty."

    try:
        tree = ast.parse(proposed_code)
    except SyntaxError as e:
        return None, f"The model's proposed code does not parse as valid Python: {e}"

    defined_names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if function_name not in defined_names:
        return None, "The model's proposed code does not define the function it claims to fix."

    if not isinstance(suggested_tests_raw, list):
        return None, "The model's suggested tests were malformed."

    tests: list[dict] = []
    for item in suggested_tests_raw[:MAX_SUGGESTED_TESTS]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        args = item.get("args")
        if not isinstance(name, str) or not name.strip() or not isinstance(args, list):
            continue
        if "expected" not in item:
            continue
        try:
            json.dumps(item["expected"])
            json.dumps(args)
        except (TypeError, ValueError):
            continue
        tests.append({"name": name[:120], "args": args[:8], "expected": item["expected"]})

    return {
        "root_cause": payload["root_cause"],
        "code_location": str(payload.get("code_location") or "")[:500],
        "explanation": payload["explanation"],
        "edge_cases": str(payload.get("edge_cases") or "")[:500],
        "function_name": function_name,
        "proposed_code": proposed_code,
        "diff_summary": str(payload.get("diff_summary") or "")[:500],
        "suggested_tests": tests,
    }, None


async def analyze_arbitrary(code: str, error_message: str) -> tuple[dict | None, str | None]:
    """Analyze arbitrary user-submitted code with Claude.

    Returns (validated_payload, None) on success, or (None, human_readable_reason)
    if AI is disabled, the request failed, or the response didn't validate.
    Never fabricates a result on failure.
    """
    if not ai_enabled():
        return None, (
            "Full AI analysis of custom code requires configuring an Anthropic "
            "API key on the server (see README). In demo mode, try one of the "
            "sample scenarios below instead."
        )

    user_content = (
        f"Source code:\n```python\n{code}\n```\n\n"
        f"Error message / traceback / unexpected behavior reported by the user:\n{error_message or '(none provided)'}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 1400,
                    "system": _GENERAL_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_content}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return None, f"The AI provider returned an error ({e.response.status_code})."
    except Exception:
        return None, "Could not reach the AI provider. Check server connectivity and the API key."

    text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    raw_text = "\n".join(text_parts).strip()
    if not raw_text:
        return None, "The AI provider returned an empty response."

    cleaned = _strip_code_fences(raw_text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, "The AI provider's response was not valid JSON and could not be used."

    validated, reason = _validate_general_payload(payload)
    if validated is None:
        return None, reason or "The AI response failed validation."
    return validated, None
