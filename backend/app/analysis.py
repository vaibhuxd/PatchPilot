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
