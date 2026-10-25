
"""
Analysis provider adapter.

Two modes, always honestly labeled to the caller:

1. Scenario mode: fixes and tests come from pre-verified scenarios.
   Claude may augment the explanation but cannot change the fix.

2. General mode: Claude analyzes arbitrary Python code and proposes
   a fix and tests. Responses are validated before being returned.
"""

from __future__ import annotations

import ast
import json
import os
import re

import httpx

from .scenarios import Scenario

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get(
    "ANTHROPIC_MODEL", "claude-sonnet-4-6"
)
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

MAX_SUGGESTED_TESTS = 6


def ai_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)


async def generate_explanation(
    scenario: Scenario, user_error_message: str
) -> tuple[str, str]:
    """Returns (explanation_text, mode)."""
    if not ai_enabled():
        return _demo_explanation(scenario), "demo"

    prompt = (
        "You are PatchPilot, an AI debugging assistant. A user ran into "
        f"this bug:\n\nBuggy code:\n```python\n{scenario.buggy_code}\n```\n\n"
        f"Error / symptom: {user_error_message or scenario.sample_error_message}\n\n"
        f"Known root cause: {scenario.root_cause}\n"
        f"Known fix location: {scenario.code_location}\n\n"
        "In 3-5 concise sentences, explain the root cause and why the "
        "fix below resolves it. Do not suggest a different fix.\n\n"
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
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        text_parts = [
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        text = "\n".join(text_parts).strip()

        if text:
            return text, "llm"

        return _demo_explanation(scenario), "demo"

    except Exception:
        return _demo_explanation(scenario), "demo"


def _demo_explanation(scenario: Scenario) -> str:
    return (
        f"{scenario.root_cause} {scenario.explanation} "
        f"Edge cases to watch for: {scenario.edge_cases}"
    )


_GENERAL_SYSTEM_PROMPT = """You are PatchPilot, an AI debugging assistant.

The user provides Python source code and an error or unexpected behavior.

Respond with ONLY one JSON object with exactly these keys:
{
  "root_cause": "1-3 sentences explaining the bug",
  "code_location": "location of the bug",
  "explanation": "2-4 sentences explaining the fix",
  "edge_cases": "edge cases worth checking",
  "function_name": "name of the function being fixed",
  "proposed_code": "full corrected Python source code",
  "diff_summary": "brief summary of changes",
  "suggested_tests": [
    {"name": "test name", "args": [], "expected": null}
  ]
}

Rules:
- Provide 1-4 tests for pure functions without I/O.
- Test arguments and expected results must be JSON serializable.
- If no safe, confident fix can be proposed, set function_name and
  proposed_code to null and suggested_tests to [].
- Do not invent environmental facts.
- Code must be valid Python 3.
- Do not import os, sys, subprocess, socket, shutil, or networking/
  filesystem modules in proposed code.
- Do not call eval, exec, open, or __import__.
"""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    match = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$",
        text,
        flags=re.DOTALL,
    )
    return match.group(1).strip() if match else text


def _validate_general_payload(
    payload: dict,
) -> tuple[dict | None, str | None]:
    """Return validated payload or a readable validation error."""
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

    if not isinstance(payload, dict) or not required_keys.issubset(payload):
        return None, "The model response was missing required fields."

    for key in ("root_cause", "explanation"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            return None, f"The model response had an invalid '{key}'."

    function_name = payload.get("function_name")
    proposed_code = payload.get("proposed_code")
    raw_tests = payload.get("suggested_tests")

    if function_name is None or proposed_code is None:
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

    if not isinstance(function_name, str) or not re.match(
        r"^[A-Za-z_][A-Za-z0-9_]*$", function_name
    ):
        return None, "The model proposed an invalid function name."

    if not isinstance(proposed_code, str) or not proposed_code.strip():
        return None, "The model's proposed code was empty."

    try:
        tree = ast.parse(proposed_code)
    except SyntaxError as exc:
        return None, f"Proposed code is invalid Python: {exc}"

    defined_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    if function_name not in defined_names:
        return None, "Proposed code does not define the named function."

    if not isinstance(raw_tests, list):
        return None, "The model's suggested tests were malformed."

    tests = []
    for item in raw_tests[:MAX_SUGGESTED_TESTS]:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        args = item.get("args")

        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(args, list) or "expected" not in item:
            continue

        try:
            json.dumps(args)
            json.dumps(item["expected"])
        except (TypeError, ValueError):
            continue

        tests.append({
            "name": name[:120],
            "args": args[:8],
            "expected": item["expected"],
        })

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


async def analyze_arbitrary(
    code: str, error_message: str
) -> tuple[dict | None, str | None]:
    """Analyze user-submitted code using Anthropic."""
    if not ai_enabled():
        return None, (
            "Full AI analysis requires an Anthropic API key on the server."
        )

    user_content = (
        f"Source code:\n```python\n{code}\n```\n\n"
        "Error / traceback / unexpected behavior:\n"
        f"{error_message or '(none provided)'}"
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
                    "messages": [
                        {"role": "user", "content": user_content}
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()

    except httpx.HTTPStatusError as exc:
        try:
            body = exc.response.json()
            error = body.get("error", {})
            detail = error.get("message", "Unknown API error")
            error_type = error.get("type", "unknown")
        except Exception:
            detail = exc.response.text[:500] or "No details returned"
            error_type = "unknown"

        return None, (
            f"Anthropic API error ({exc.response.status_code}, "
            f"{error_type}): {detail}"
        )

    except Exception:
        return None, (
            "Could not reach the AI provider. "
            "Check server connectivity and configuration."
        )

    text_parts = [
        block["text"]
        for block in data.get("content", [])
        if block.get("type") == "text"
    ]
    raw_text = "\n".join(text_parts).strip()

    if not raw_text:
        return None, "The AI provider returned an empty response."

    cleaned = _strip_code_fences(raw_text)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, (
            "The AI provider's response was not valid JSON."
        )

    validated, reason = _validate_general_payload(payload)

    if validated is None:
        return None, reason or "The AI response failed validation."

    return validated, None
