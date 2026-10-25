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
        try:
            body = e.response.json()
            error = body.get("error", {})
            detail = error.get("message", "Unknown API error")
            error_type = error.get("type", "unknown")
        except Exception:
            detail = e.response.text[:500] or "No details returned"
            error_type = "unknown"

        return None, (
            f"Anthropic API error ({e.response.status_code}, "
            f"{error_type}): {detail}"
        )
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
