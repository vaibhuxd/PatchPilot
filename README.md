# PatchPilot

**From Error to Verified Fix.**

PatchPilot is an AI-assisted debugging workspace. It takes a Python bug, explains
the root cause, proposes a fix, and then actually *runs tests* against that fix
so you can see whether it's verified — not just suggested.

Built for Syntax Error 2026 (IIT Roorkee).

---

## Product overview

The core idea: **AI proposes the fix. Tests provide evidence.**

A lot of AI coding assistants stop at "here's a fix, looks right." PatchPilot
draws a hard line between a *proposed* patch and a *verified* one, and never
blurs the two:

- `Proposed` — a fix has been generated.
- `Untested` — the fix hasn't been run yet.
- `Passed` — the fix was actually executed against the test suite and every
  test passed.
- `Failed` — it was executed and at least one test failed.

Generating a patch never bumps its status to Passed on its own — only a real
test run does that.

## Features actually implemented

**Primary workflow — your own code:**
- Paste any Python source and an error message / traceback (or a plain
  description of the wrong behavior) and click **Analyze code**. No preset
  selection required.
- If `ANTHROPIC_API_KEY` is configured on the backend, Claude diagnoses the
  bug and returns root cause, code location, explanation, edge cases, a
  proposed fix, a diff summary, and 1–4 suggested test cases — as strict
  JSON that the backend validates before ever showing it (parses as valid
  Python, the claimed function actually exists in the proposed code, test
  args/expected values are JSON-safe primitives). If validation fails, or
  the API call fails, PatchPilot says so plainly instead of fabricating a
  result (`app/analysis.py::analyze_arbitrary`, unit-tested in
  `tests/test_general_analysis.py` without needing network access).
- Those AI-suggested tests then run for real, in the same sandboxed
  subprocess used for the preset scenarios — you can test the code you
  pasted and the proposed fix independently, and see genuine pass/fail
  results either way.
- If Claude can't confidently identify a fixable function, it says so
  honestly (`root_cause` explains why) rather than inventing a patch — no
  fix or test buttons are shown in that case.

**Sample scenarios (optional, always available, zero config):**
- Three reproducible, hand-crafted Python bug scenarios whose buggy code
  genuinely fails its tests and whose fix genuinely passes them (see
  `backend/tests/test_sandbox.py`): division-by-zero in an average
  function, an off-by-one range-sum bug, and a find-max boundary bug on
  all-negative input. These work identically with or without an API key —
  the fix and tests are deterministic; an API key, if present, only
  upgrades the natural-language *explanation* text.

**Shared:**
- Root-cause analysis panel: cause, code location, explanation, edge cases.
- Side-by-side diff view of original vs. proposed code.
- Status badges (`Proposed` / `Untested` / `Passed` / `Failed`) that only
  change on an actual test run — never on generation alone.
- Honest failure modes throughout: no API key configured → clearly labeled
  Demo Mode message (sample scenarios still fully work); AI call fails or
  returns something that doesn't validate → explicit error, not a guess;
  dangerous code (banned imports/calls) is rejected by a static check
  before anything ever executes.
- Centered, responsive workspace (desktop/tablet/mobile) using the full
  viewport width instead of hugging the left edge.

## What is *not* implemented (be honest about this in a demo)

- A production-grade sandbox (gVisor/Firecracker/Docker) — see **Security
  considerations**.
- Multi-file or multi-language input — Python, single-function fixes only.
- User accounts or persistence — state lives in the browser tab only.
- Full syntax highlighting in the code editor (line numbers + monospace
  only).

## Technology stack actually used

**Frontend:** React 18, TypeScript, Vite 5, plain CSS (no component library).

**Backend:** Python 3.12, FastAPI, Uvicorn, httpx (for the optional Anthropic
API call).

**Testing:** pytest, run against `backend/app/sandbox.py` and the scenario
data to prove the buggy code fails and the fixed code passes.

**AI integration:** a thin server-side adapter (`backend/app/analysis.py`)
that calls the Anthropic Messages API only when `ANTHROPIC_API_KEY` is
configured; otherwise it returns the deterministic demo-mode explanation.
No API key is ever sent to or stored in the frontend.

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm

## Installation

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

## Environment variable configuration

Copy `backend/.env.example` to `backend/.env` and fill in real values if you
want live AI analysis:

```
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6   # optional, this is the default
```

If `ANTHROPIC_API_KEY` is left unset, PatchPilot runs entirely in demo mode —
no network calls to any AI provider are made, and the UI labels every
analysis as "Demo mode" accordingly.

**Never commit a real `.env` file or paste a real key into the README,
frontend code, or git history.**

## Startup commands

Run both processes in separate terminals:

```bash
# Terminal 1 — backend (serves the API on :8000)
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (serves the UI on :5173, proxies /api to :8000)
cd frontend
npm run dev
```

Open `http://localhost:5173`.

For a production-style build of the frontend: `npm run build` in `frontend/`,
then serve `frontend/dist/` with any static file server (configure it to
proxy `/api` to the backend, or set `VITE_API_BASE` and rebuild if you adapt
`src/api.ts` for a different deployment target).

## Running your own code

1. Paste Python source into **Python source code**.
2. Paste the error/traceback (or describe the wrong behavior) into **Error
   message or traceback**.
3. Click **Analyze code**.
   - With `ANTHROPIC_API_KEY` configured: you get a real diagnosis and,
     when Claude can confidently identify one, a proposed fix with suggested
     tests.
   - Without a key: you'll get an honest Demo Mode message instead of a
     fabricated analysis — use a sample scenario instead, or configure a key.
4. If a fix was proposed, click **Generate proposed fix** to see the diff,
   then **Run verification tests (proposed fix)** for real pass/fail
   results. You can also run the same suggested tests against your
   original, unmodified code via **Run verification tests (current code)**.

## Running the sample scenarios

1. Open the app and pick one of the three cards under **Try an example**.
2. The buggy code and a sample error message load into the workspace
   (both are editable — editing either switches you back to custom-code
   mode on the next Analyze).
3. Click **Analyze code** to see the root-cause panel.
4. Click **Generate proposed fix** to see the diff and the proposed code.
5. Click **Run verification tests (current code)** and/or **Run
   verification tests (proposed fix)** to see real pass/fail results and
   the resulting status badge.

## Testing instructions

Backend unit tests (prove the scenarios are real, the sandbox behaves, and
the AI-response validation logic rejects bad output without needing
network access):

```bash
cd backend
pytest tests/ -v
```

This includes tests that:
- each scenario's buggy code actually fails at least one test,
- each scenario's fixed code actually passes all tests,
- dangerous imports (`os`, `subprocess`, `socket`, `eval`, ...) are rejected
  before execution,
- an infinite loop is killed by the timeout,
- a missing function and a syntax error both report cleanly instead of
  crashing the server,
- general-mode AI responses are rejected when they're missing fields,
  contain unparseable code, claim a function that isn't actually defined,
  or include malformed test cases — and that a well-formed "I can't
  confidently fix this" response is accepted rather than treated as an
  error.

Frontend build/type-check:

```bash
cd frontend
npm run build
```

## Security considerations

PatchPilot never executes submitted code inside the FastAPI server process.
Code runs in a separate OS subprocess (`backend/app/sandbox.py`) with:

- A static AST check that rejects dangerous imports and calls (`os`, `sys`,
  `subprocess`, `socket`, `shutil`, `eval`, `exec`, `open`, `__import__`,
  ...) before anything executes.
- A hard wall-clock timeout (5s).
- POSIX resource limits on CPU time, memory, and output size where the
  `resource` module is available (Linux).
- `python -I -S` (isolated mode, no site packages) for the subprocess.

**Known limitation:** this is defense-in-depth, not a true security
boundary — there is no container/VM-level isolation (no Docker/gVisor/
Firecracker in this build). It is adequate for a hackathon demo, but it is
**not** sufficient for running fully arbitrary, adversarial code from
untrusted users in production. A real deployment should add a proper
sandboxing layer (gVisor, Firecracker, or a managed code-execution API)
before accepting arbitrary code from the public internet. This applies to
both the sample scenarios and general-mode custom code — the same sandbox
runs both.

This also means: general mode always runs the code *you* currently have in
the editor (or the AI's proposed fix) against tests, never arbitrary code
the model might have hallucinated outside what you can see — the proposed
code is always shown to you before it's ever executed, and the same static
import/call checks apply to it as to anything else that reaches the sandbox.

API keys are read from server-side environment variables only
(`backend/.env`, not committed) and are never embedded in or served to the
frontend. The Anthropic API is called only from the backend.

## Known limitations

- General-mode analysis (your own code) requires `ANTHROPIC_API_KEY` to be
  configured; without it, only the three sample scenarios are available —
  Demo Mode says so plainly rather than faking an analysis.
- The sandbox is subprocess + AST-allowlist + resource limits, not full
  container isolation (see Security above) — applies to all code, preset
  or custom.
- AI-suggested tests (general mode) are generated and validated, but not
  human-authored the way the three sample scenarios' tests are — the UI
  labels this distinction explicitly.
- No persistence — state lives in the browser tab only; refreshing resets
  the workspace.
- The "diff" view is a simple line-based LCS diff, not a full token-level
  diff.
- Single-function fixes only; multi-function or multi-file bugs aren't
  supported.

## Demo walkthrough (~2 minutes)

**If you have an API key configured:**
1. Open PatchPilot — point out the tagline and the centered workspace.
2. Paste a small buggy function (e.g. a function that indexes off-by-one)
   and a short error description directly into the editor — no preset
   needed.
3. Click **Analyze code** — walk through the AI-generated root cause,
   location, explanation, and edge cases.
4. Click **Generate proposed fix** — show the diff and the status badge at
   **Untested**.
5. Click **Run verification tests (proposed fix)** — show the real
   pass/fail results and the badge flipping to **Passed**, and point out
   the note that these tests were AI-suggested, not hand-authored.
6. Optionally click **Run verification tests (current code)** to show the
   *original* buggy version actually failing those same tests.

**Either way (works with zero configuration):**
1. Scroll to **Try an example** and pick **Division by Zero in Average
   Calculation**. Buggy code and the sample error auto-load.
2. Click **Analyze code** — walk through the root-cause panel. Point out
   the "Demo mode" / "AI-generated" label — it's never hidden.
3. Click **Generate proposed fix** — show the diff and the status badge
   sitting at **Untested**.
4. Click **Run verification tests (proposed fix)** — show the real
   pass/fail results, and the badge flipping to **Passed**.
5. Optionally: go back, click **Run verification tests (current code)** (the original
   buggy version) to show it actually fails the empty-list test — proving
   the bug is real, not just asserted.
7. Close by stating the core principle out loud: AI proposes, tests verify —
   and show the backend pytest run (`pytest tests/ -v`, all green) as
   independent proof the scenario data itself isn't fabricated.
