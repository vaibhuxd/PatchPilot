import { useEffect, useState } from "react";
import "./App.css";
import {
  analyzeCode,
  fetchHealth,
  fetchScenarios,
  proposeFix,
  testCustom,
  testScenario,
  type AnalyzeResponse,
  type ScenarioSummary,
  type SuggestedTest,
  type TestResponse,
} from "./api";
import ScenarioPicker from "./components/ScenarioPicker";
import CodeEditor from "./components/CodeEditor";
import DiffView from "./components/DiffView";
import TestResults from "./components/TestResults";
import StatusBadge from "./components/StatusBadge";

type PatchStatus = "proposed" | "untested" | "passed" | "failed";

interface Proposal {
  scenario_id: string | null; // non-null => preset scenario fix; null => general/AI-generated fix
  original_code: string;
  proposed_code: string;
  diff_summary: string;
}

export default function App() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [scenariosError, setScenariosError] = useState<string | null>(null);
  const [aiMode, setAiMode] = useState<"llm" | "demo" | null>(null);

  const [code, setCode] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);

  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const [generatingFix, setGeneratingFix] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [proposalFunctionName, setProposalFunctionName] = useState<string | null>(null);
  const [proposalTests, setProposalTests] = useState<SuggestedTest[] | null>(null);

  const [testing, setTesting] = useState<"original" | "proposed" | null>(null);
  const [originalTestReport, setOriginalTestReport] = useState<TestResponse | null>(null);
  const [proposedTestReport, setProposedTestReport] = useState<TestResponse | null>(null);

  useEffect(() => {
    fetchScenarios()
      .then(setScenarios)
      .catch(() => setScenariosError("Could not reach the PatchPilot backend. Is it running?"));
    fetchHealth()
      .then((h) => setAiMode(h.ai_mode))
      .catch(() => setAiMode(null));
  }, []);

  function resetDownstream() {
    setAnalysis(null);
    setAnalysisError(null);
    setProposal(null);
    setProposalFunctionName(null);
    setProposalTests(null);
    setOriginalTestReport(null);
    setProposedTestReport(null);
  }

  function selectScenario(s: ScenarioSummary) {
    setSelectedScenarioId(s.id);
    setCode(s.buggy_code);
    setErrorMessage(s.sample_error_message);
    resetDownstream();
  }

  function handleCodeChange(v: string) {
    setCode(v);
    if (selectedScenarioId !== null) {
      // Editing the code means this is no longer the untouched sample —
      // treat it as custom input from here on so Analyze reflects what's
      // actually in the box, not the preset's canned data.
      setSelectedScenarioId(null);
      resetDownstream();
    }
  }

  function handleErrorChange(v: string) {
    setErrorMessage(v);
    if (selectedScenarioId !== null) {
      setSelectedScenarioId(null);
      resetDownstream();
    }
  }

  async function handleAnalyze() {
    if (!code.trim()) return;
    setAnalyzing(true);
    setAnalysisError(null);
    setAnalysis(null);
    setProposal(null);
    setProposalFunctionName(null);
    setProposalTests(null);
    setOriginalTestReport(null);
    setProposedTestReport(null);
    try {
      const result = await analyzeCode(selectedScenarioId, code, errorMessage);
      setAnalysis(result);
    } catch (e) {
      setAnalysisError(e instanceof Error ? e.message : "Analysis request failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleGenerateFix() {
    if (!analysis || !analysis.supported) return;

    if (analysis.mode === "scenario" && analysis.scenario_id) {
      setGeneratingFix(true);
      try {
        const result = await proposeFix(analysis.scenario_id);
        setProposal({
          scenario_id: result.scenario_id,
          original_code: result.original_code,
          proposed_code: result.proposed_code,
          diff_summary: result.diff_summary,
        });
        setProposalFunctionName(analysis.function_name ?? null);
        setProposalTests(null); // preset tests come via scenario_id, not an explicit list
        setProposedTestReport(null);
      } finally {
        setGeneratingFix(false);
      }
      return;
    }

    // General mode: the fix was already generated alongside the analysis —
    // no second AI call needed, just reveal it.
    if (analysis.mode === "general" && analysis.fix_available && analysis.proposed_code) {
      setProposal({
        scenario_id: null,
        original_code: analysis.original_code ?? code,
        proposed_code: analysis.proposed_code,
        diff_summary: analysis.diff_summary ?? "",
      });
      setProposalFunctionName(analysis.function_name ?? null);
      setProposalTests(analysis.suggested_tests ?? []);
      setProposedTestReport(null);
    }
  }

  async function handleTest(target: "original" | "proposed") {
    const codeToRun = target === "original" ? code : proposal?.proposed_code;
    if (!codeToRun) return;

    setTesting(target);
    try {
      let report: TestResponse;

      if (target === "original") {
        if (analysis?.mode === "scenario" && analysis.scenario_id) {
          report = await testScenario(analysis.scenario_id, codeToRun);
        } else if (analysis?.mode === "general" && analysis.function_name && analysis.suggested_tests?.length) {
          report = await testCustom(codeToRun, analysis.function_name, analysis.suggested_tests);
        } else {
          return;
        }
        setOriginalTestReport(report);
      } else {
        if (proposal?.scenario_id) {
          report = await testScenario(proposal.scenario_id, codeToRun);
        } else if (proposalFunctionName && proposalTests?.length) {
          report = await testCustom(codeToRun, proposalFunctionName, proposalTests);
        } else {
          return;
        }
        setProposedTestReport(report);
      }
    } finally {
      setTesting(null);
    }
  }

  let proposedStatus: PatchStatus = "proposed";
  if (proposal) {
    if (!proposedTestReport) proposedStatus = "untested";
    else if (proposedTestReport.status === "passed") proposedStatus = "passed";
    else proposedStatus = "failed";
  }

  const canTestOriginal =
    (analysis?.mode === "scenario" && !!analysis.scenario_id) ||
    (analysis?.mode === "general" && !!analysis.function_name && (analysis.suggested_tests?.length ?? 0) > 0);

  const canGenerateFix =
    analysis?.supported &&
    ((analysis.mode === "scenario" && !!analysis.scenario_id) ||
      (analysis.mode === "general" && !!analysis.fix_available));

  return (
    <div className="shell">
      <aside className="sidebar">
        <div>
          <div className="brand">
            <svg className="brand__mark" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
              <rect width="64" height="64" rx="14" fill="#0a0e1a" />
              <path d="M20 44 L32 16 L44 44 L32 36 Z" fill="#4f8cff" />
              <circle cx="32" cy="22" r="3" fill="#35d4e0" />
            </svg>
            <div>
              <div className="brand__name">PatchPilot</div>
            </div>
          </div>
          <div className="brand__tagline">From Error to Verified Fix</div>
        </div>

        <nav className="sidebar__nav">
          <div className="nav-item nav-item--active">Debug workspace</div>
        </nav>

        <div className="sidebar__footer">
          {aiMode && (
            <span className="mode-pill">
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: aiMode === "llm" ? "var(--status-passed)" : "var(--status-untested)",
                }}
              />
              {aiMode === "llm" ? "Live AI analysis" : "Demo Mode (no API key)"}
            </span>
          )}
          <p className="sidebar__note">
            Executes code in an isolated subprocess with a timeout, import
            allow-listing, and resource limits — not a full container
            sandbox.
          </p>
        </div>
      </aside>

      <main className="main">
        <div className="page-head">
          <h1>Debug workspace</h1>
          <p>
            Paste your own Python code and error message, or load a sample
            scenario below. PatchPilot explains the likely cause, proposes a
            fix, and lets you run real tests to confirm it.
          </p>
        </div>

        {scenariosError && (
          <div className="panel panel--error">
            <div className="panel__title">Backend unreachable</div>
            <p className="muted">{scenariosError}</p>
          </div>
        )}

        {aiMode === "demo" && (
          <div className="panel panel--notice">
            <div className="panel__title">Demo Mode</div>
            <p className="muted" style={{ fontSize: 13 }}>
              No Anthropic API key is configured on the backend, so free-form
              analysis of your own code isn't available right now. The three
              sample scenarios below are fully supported — buggy code, root
              cause, fix, and real tests, end to end. Set{" "}
              <code>ANTHROPIC_API_KEY</code> on the backend to analyze your
              own code (see README).
            </p>
          </div>
        )}

        <section className="panel">
          <div className="panel__title">1. Python source code &amp; error</div>
          <div style={{ marginTop: 14, marginBottom: 16 }}>
            <span className="field-label">Python source code</span>
            <CodeEditor value={code} onChange={handleCodeChange} label="your_code.py" />
          </div>
          <div>
            <span className="field-label">Error message or traceback</span>
            <textarea
              className="error-input"
              rows={2}
              value={errorMessage}
              onChange={(e) => handleErrorChange(e.target.value)}
              placeholder="Paste the error message / traceback, or describe the incorrect behavior"
            />
          </div>
          <div className="btn-row">
            <button className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing || !code.trim()}>
              {analyzing ? (
                <>
                  <span className="spinner" />
                  Analyzing…
                </>
              ) : (
                "Analyze code"
              )}
            </button>
          </div>
          {!code.trim() && <p className="inline-note">Paste code above, or load an example below.</p>}
        </section>

        <section className="panel">
          <div className="panel__title">Try an example</div>
          <p className="muted" style={{ marginBottom: 14, fontSize: 13 }}>
            Optional — these three bugs always get a verified, deterministic
            fix and a real test run, with or without an API key configured.
          </p>
          <ScenarioPicker scenarios={scenarios} selectedId={selectedScenarioId} onSelect={selectScenario} />
        </section>

        {analysisError && (
          <section className="panel panel--error">
            <div className="panel__title">Analysis request failed</div>
            <p className="muted">{analysisError}</p>
          </section>
        )}

        {analysis && !analysis.supported && (
          <section className="panel panel--notice">
            <div className="panel__title">
              {analysis.analysis_mode === "demo" ? "Demo Mode — custom analysis unavailable" : "Not analyzed"}
            </div>
            <p className="muted">{analysis.message}</p>
          </section>
        )}

        {analysis && analysis.supported && (
          <section className="panel">
            <div className="panel__row">
              <div className="panel__title">2. Root-cause analysis</div>
              <span className="mode-pill">{analysis.analysis_mode === "llm" ? "AI-generated" : "Demo mode"}</span>
            </div>
            <div className="analysis-field">
              <div className="analysis-field__label">Root cause</div>
              <div className="analysis-field__value">{analysis.root_cause}</div>
            </div>
            {analysis.code_location && (
              <div className="analysis-field">
                <div className="analysis-field__label">Location</div>
                <div className="analysis-field__value">
                  <code>{analysis.code_location}</code>
                </div>
              </div>
            )}
            <div className="analysis-field">
              <div className="analysis-field__label">Explanation</div>
              <div className="analysis-field__value">{analysis.explanation}</div>
            </div>
            {analysis.edge_cases && (
              <div className="analysis-field">
                <div className="analysis-field__label">Edge cases to verify</div>
                <div className="analysis-field__value">{analysis.edge_cases}</div>
              </div>
            )}

            {analysis.mode === "general" && !analysis.fix_available && (
              <p className="inline-note">
                The AI didn't propose a corrected version of this code — see
                the root cause above for why. No fix or tests are available
                for this input.
              </p>
            )}

            <div className="btn-row">
              {canGenerateFix && (
                <button className="btn btn-primary" onClick={handleGenerateFix} disabled={generatingFix}>
                  {generatingFix ? (
                    <>
                      <span className="spinner" />
                      Generating fix…
                    </>
                  ) : (
                    "Generate proposed fix"
                  )}
                </button>
              )}
              {canTestOriginal && (
                <button
                  className="btn btn-secondary"
                  onClick={() => handleTest("original")}
                  disabled={testing !== null}
                >
                  {testing === "original" ? (
                    <>
                      <span className="spinner" />
                      Running…
                    </>
                  ) : (
                    "Run verification tests (current code)"
                  )}
                </button>
              )}
            </div>
            {analysis.mode === "general" && analysis.fix_available && (
              <p className="inline-note">
                Suggested tests were generated by the AI alongside the fix —
                running them is real execution, but, unlike the sample
                scenarios, they weren't authored or verified by a human.
              </p>
            )}
          </section>
        )}

        {originalTestReport && (
          <section className="panel">
            <div className="panel__title">Test results — current code</div>
            <TestResults report={originalTestReport} codeLabel="current code" />
          </section>
        )}

        {proposal && (
          <section className="panel">
            <div className="panel__row">
              <div className="panel__title">3. Proposed fix</div>
              <StatusBadge status={proposedStatus} />
            </div>
            {proposal.diff_summary && (
              <p className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
                {proposal.diff_summary}
              </p>
            )}
            <div className="analysis-grid">
              <div>
                <div className="field-label">Diff (original → proposed)</div>
                <DiffView original={proposal.original_code} proposed={proposal.proposed_code} />
              </div>
              <div>
                <div className="field-label">Proposed code</div>
                <CodeEditor value={proposal.proposed_code} readOnly minLines={6} />
              </div>
            </div>

            <div className="btn-row">
              <button className="btn btn-primary" onClick={() => handleTest("proposed")} disabled={testing !== null}>
                {testing === "proposed" ? (
                  <>
                    <span className="spinner" />
                    Running tests…
                  </>
                ) : (
                  "Run verification tests (proposed fix)"
                )}
              </button>
            </div>
            <p className="inline-note">
              A fix is only marked <strong>Passed</strong> once its tests
              actually run and succeed — generating a patch alone never
              changes its status.
            </p>
          </section>
        )}

        {proposedTestReport && (
          <section className="panel">
            <div className="panel__row">
              <div className="panel__title">4. Test results — proposed fix</div>
              <StatusBadge status={proposedStatus} />
            </div>
            <TestResults report={proposedTestReport} codeLabel="proposed fix" />
          </section>
        )}
      </main>
    </div>
  );
}
