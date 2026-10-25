import { useEffect, useState } from "react";
import "./App.css";
import { analyzeCode, fetchHealth, fetchScenarios, proposeFix, testCustom, testScenario, type AnalyzeResponse, type ScenarioSummary, type SuggestedTest, type TestResponse } from "./api";
import ScenarioPicker from "./components/ScenarioPicker";
import CodeEditor from "./components/CodeEditor";
import DiffView from "./components/DiffView";
import TestResults from "./components/TestResults";
import StatusBadge from "./components/StatusBadge";

type PatchStatus = "proposed" | "untested" | "passed" | "failed";
interface Proposal { scenario_id: string | null; original_code: string; proposed_code: string; diff_summary: string; }

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
    fetchScenarios().then(setScenarios).catch(() => setScenariosError("Could not reach the PatchPilot backend. Is it running?"));
    fetchHealth().then((health) => setAiMode(health.ai_mode)).catch(() => setAiMode(null));
  }, []);

  function resetDownstream() { setAnalysis(null); setAnalysisError(null); setProposal(null); setProposalFunctionName(null); setProposalTests(null); setOriginalTestReport(null); setProposedTestReport(null); }
  function selectScenario(scenario: ScenarioSummary) { setSelectedScenarioId(scenario.id); setCode(scenario.buggy_code); setErrorMessage(scenario.sample_error_message); resetDownstream(); }
  function handleCodeChange(value: string) { setCode(value); if (selectedScenarioId !== null) { setSelectedScenarioId(null); resetDownstream(); } }
  function handleErrorChange(value: string) { setErrorMessage(value); if (selectedScenarioId !== null) { setSelectedScenarioId(null); resetDownstream(); } }

  async function handleAnalyze() {
    if (!code.trim()) return;
    setAnalyzing(true); setAnalysisError(null); setAnalysis(null); setProposal(null); setProposalFunctionName(null); setProposalTests(null); setOriginalTestReport(null); setProposedTestReport(null);
    try { setAnalysis(await analyzeCode(selectedScenarioId, code, errorMessage)); }
    catch (error) { setAnalysisError(error instanceof Error ? error.message : "Analysis request failed."); }
    finally { setAnalyzing(false); }
  }
  async function handleGenerateFix() {
    if (!analysis || !analysis.supported) return;
    if (analysis.mode === "scenario" && analysis.scenario_id) {
      setGeneratingFix(true);
      try { const result = await proposeFix(analysis.scenario_id); setProposal(result); setProposalFunctionName(analysis.function_name ?? null); setProposalTests(null); setProposedTestReport(null); }
      finally { setGeneratingFix(false); }
      return;
    }
    if (analysis.mode === "general" && analysis.fix_available && analysis.proposed_code) {
      setProposal({ scenario_id: null, original_code: analysis.original_code ?? code, proposed_code: analysis.proposed_code, diff_summary: analysis.diff_summary ?? "" });
      setProposalFunctionName(analysis.function_name ?? null); setProposalTests(analysis.suggested_tests ?? []); setProposedTestReport(null);
    }
  }
  async function handleTest(target: "original" | "proposed") {
    const codeToRun = target === "original" ? code : proposal?.proposed_code;
    if (!codeToRun) return;
    setTesting(target);
    try {
      let report: TestResponse;
      if (target === "original") {
        if (analysis?.mode === "scenario" && analysis.scenario_id) report = await testScenario(analysis.scenario_id, codeToRun);
        else if (analysis?.mode === "general" && analysis.function_name && analysis.suggested_tests?.length) report = await testCustom(codeToRun, analysis.function_name, analysis.suggested_tests);
        else return;
        setOriginalTestReport(report);
      } else {
        if (proposal?.scenario_id) report = await testScenario(proposal.scenario_id, codeToRun);
        else if (proposalFunctionName && proposalTests?.length) report = await testCustom(codeToRun, proposalFunctionName, proposalTests);
        else return;
        setProposedTestReport(report);
      }
    } finally { setTesting(null); }
  }

  const proposedStatus: PatchStatus = !proposal ? "proposed" : !proposedTestReport ? "untested" : proposedTestReport.status === "passed" ? "passed" : "failed";
  const canTestOriginal = (analysis?.mode === "scenario" && !!analysis.scenario_id) || (analysis?.mode === "general" && !!analysis.function_name && (analysis.suggested_tests?.length ?? 0) > 0);
  const canGenerateFix = analysis?.supported && ((analysis.mode === "scenario" && !!analysis.scenario_id) || (analysis.mode === "general" && !!analysis.fix_available));
  const phase = proposedTestReport?.status === "passed" ? "verified" : proposal ? "patch ready" : analysis ? "cause mapped" : "awaiting input";

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#mission" aria-label="PatchPilot home"><span className="brand__glyph"><i /><i /><i /></span><span className="brand__wordmark">PATCH<span>PILOT</span></span></a>
      <div className="topbar__center"><span className="signal-dot" /> REPOSITORY REPAIR CONSOLE <span className="topbar__slash">//</span> PYTHON</div>
      <div className="topbar__right"><span className={`system-state ${aiMode === "llm" ? "system-state--live" : ""}`}><i /> {aiMode === "llm" ? "AI LINKED" : aiMode === "demo" ? "DEMO CORE" : "CONNECTING"}</span><span className="topbar__unit">UNIT 01</span></div>
    </header>
    <main id="mission" className="mission">
      <section className="hero">
        <div className="hero__copy"><div className="eyebrow"><span>01</span> ERROR IN. EVIDENCE OUT.</div><h1>Make every<br /><em>patch</em> earn its green.</h1><p>PatchPilot traces a Python failure, stages a repair, and runs the proof. No hand-wavy “looks fixed” verdicts.</p></div>
        <div className="hero__radar" aria-label="Patch verification signal"><div className="radar-core"><span>PATCH<br />PILOT</span></div><i className="radar-line" /><b className="radar-ping radar-ping--one" /><b className="radar-ping radar-ping--two" /><b className="radar-ping radar-ping--three" /><div className="radar-label radar-label--top">ANALYZE</div><div className="radar-label radar-label--right">PATCH</div><div className="radar-label radar-label--bottom">VERIFY</div></div>
        <div className="hero__stats"><div><span>RUN STATE</span><strong>{phase}</strong></div><div><span>EXECUTION</span><strong>isolated</strong></div><div><span>TRUST RULE</span><strong>tests decide</strong></div></div>
      </section>
      <section className="flight-strip" aria-label="Repair workflow">
        <div className={!analysis ? "flight-step flight-step--active" : "flight-step flight-step--done"}><b>01</b><span>INTAKE</span><i /></div>
        <div className={analysis && !proposal ? "flight-step flight-step--active" : proposal ? "flight-step flight-step--done" : "flight-step"}><b>02</b><span>DIAGNOSE</span><i /></div>
        <div className={proposal && !proposedTestReport ? "flight-step flight-step--active" : proposedTestReport ? "flight-step flight-step--done" : "flight-step"}><b>03</b><span>PATCH</span><i /></div>
        <div className={proposedTestReport ? "flight-step flight-step--active" : "flight-step"}><b>04</b><span>VERIFY</span><i /></div>
      </section>
      {scenariosError && <div className="alert alert--error"><b>BACKEND OFFLINE</b><span>{scenariosError}</span></div>}
      {aiMode === "demo" && <div className="alert"><b>DEMO CORE ACTIVE</b><span>Custom AI analysis is off. The three diagnostic drills below still run end-to-end with real tests.</span></div>}
      <section className="console-panel intake-panel"><div className="panel-kicker"><span>01 / INTAKE</span><span>PASTE A FAILURE OR LOAD A DRILL</span></div><div className="intake-grid">
        <div className="source-bay"><div className="bay-label"><span>PYTHON SOURCE</span><small>your_code.py</small></div><CodeEditor value={code} onChange={handleCodeChange} label="workspace / source.py" /></div>
        <div className="incident-bay"><div className="bay-label"><span>INCIDENT REPORT</span><small>optional, but useful</small></div><textarea className="error-input" rows={6} value={errorMessage} onChange={(event) => handleErrorChange(event.target.value)} placeholder="Paste the traceback, test failure, or describe the behavior that broke." /><div className="incident-bay__footer"><span>{code.trim() ? `${code.split("\n").length} lines armed` : "no source loaded"}</span><button className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing || !code.trim()}>{analyzing ? <><span className="spinner" />TRACING FAILURE</> : <>TRACE FAILURE <span>→</span></>}</button></div></div>
      </div>{!code.trim() && <p className="inline-note">No source loaded. Drop in a function, or arm one of the pre-built failures below.</p>}</section>
      <section className="drills"><div className="section-heading"><div><span className="section-index">DRILL DECK</span><h2>Known failures. Real outcomes.</h2></div><p>Each sample has a deliberately broken implementation and a pre-verified repair path.</p></div><ScenarioPicker scenarios={scenarios} selectedId={selectedScenarioId} onSelect={selectScenario} /></section>
      {analysisError && <div className="alert alert--error"><b>TRACE ABORTED</b><span>{analysisError}</span></div>}
      {analysis && !analysis.supported && <section className="console-panel unavailable-panel"><div className="panel-kicker"><span>02 / DIAGNOSE</span><span>NO VERDICT AVAILABLE</span></div><h2>{analysis.analysis_mode === "demo" ? "This needs the live analysis core." : "No confident diagnosis."}</h2><p>{analysis.message}</p></section>}
      {analysis && analysis.supported && <section className="console-panel diagnosis-panel"><div className="panel-kicker"><span>02 / DIAGNOSE</span><span className="tag">{analysis.analysis_mode === "llm" ? "AI SIGNAL" : "DETERMINISTIC DRILL"}</span></div><div className="diagnosis-layout"><div className="diagnosis-title"><span>ROOT CAUSE</span><h2>{analysis.root_cause}</h2>{analysis.code_location && <code>{analysis.code_location}</code>}</div><div className="diagnosis-detail"><div><span>READOUT</span><p>{analysis.explanation}</p></div><div><span>WATCH FOR</span><p>{analysis.edge_cases}</p></div></div></div>{analysis.mode === "general" && !analysis.fix_available && <p className="inline-note">The analysis stopped short of making a patch. That’s intentional: PatchPilot will not invent a repair it cannot support.</p>}<div className="action-row">{canGenerateFix && <button className="btn btn-primary" onClick={handleGenerateFix} disabled={generatingFix}>{generatingFix ? <><span className="spinner" />STAGING PATCH</> : <>STAGE REPAIR <span>→</span></>}</button>}{canTestOriginal && <button className="btn btn-ghost" onClick={() => handleTest("original")} disabled={testing !== null}>{testing === "original" ? <><span className="spinner" />RUNNING BASELINE</> : "RUN BASELINE TESTS"}</button>}</div>{analysis.mode === "general" && analysis.fix_available && <p className="inline-note">The custom tests were suggested by AI and will be executed for real; the drill tests are human-authored and deterministic.</p>}</section>}
      {originalTestReport && <section className="console-panel result-panel"><div className="panel-kicker"><span>BASELINE / CURRENT CODE</span><span>REAL EXECUTION</span></div><TestResults report={originalTestReport} codeLabel="current code" /></section>}
      {proposal && <section className="console-panel patch-panel"><div className="panel-kicker"><span>03 / PATCH</span><StatusBadge status={proposedStatus} /></div><div className="patch-head"><div><h2>Repair staged.</h2><p>{proposal.diff_summary || "A candidate repair has been prepared for verification."}</p></div><div className="patch-rule"><span>STATUS IS NOT A PROMISE</span><b>{proposedTestReport ? "TEST RUN RECORDED" : "TEST RUN REQUIRED"}</b></div></div><div className="analysis-grid"><div><div className="field-label">CHANGESET / ORIGINAL → PATCH</div><DiffView original={proposal.original_code} proposed={proposal.proposed_code} /></div><div><div className="field-label">STAGED SOURCE / READ ONLY</div><CodeEditor value={proposal.proposed_code} readOnly minLines={6} /></div></div><div className="action-row"><button className="btn btn-primary" onClick={() => handleTest("proposed")} disabled={testing !== null}>{testing === "proposed" ? <><span className="spinner" />EXECUTING TESTS</> : <>VERIFY THIS PATCH <span>→</span></>}</button></div><p className="inline-note">A patch turns green only after its test suite completes successfully. Generating it changes nothing.</p></section>}
      {proposedTestReport && <section className={`console-panel result-panel ${proposedTestReport.status === "passed" ? "result-panel--passed" : "result-panel--failed"}`}><div className="panel-kicker"><span>04 / VERIFICATION RECORD</span><StatusBadge status={proposedStatus} /></div><TestResults report={proposedTestReport} codeLabel="proposed fix" /></section>}
    </main>
    <footer className="footer"><span>PATCHPILOT / FROM ISSUE TO VERIFIED PATCH</span><span>AI PROPOSES <i /> TESTS VERIFY</span></footer>
  </div>;
}

