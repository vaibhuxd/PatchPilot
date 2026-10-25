export interface ScenarioSummary {
  id: string;
  title: string;
  short_description: string;
  function_name: string;
  buggy_code: string;
  sample_error_message: string;
}

export interface SuggestedTest {
  name: string;
  args: unknown[];
  expected: unknown;
}

export interface AnalyzeResponse {
  supported: boolean;
  mode: "scenario" | "general";
  message?: string;
  scenario_id?: string | null;
  title?: string;
  root_cause?: string;
  code_location?: string;
  explanation?: string;
  edge_cases?: string;
  function_name?: string | null;
  proposed_code?: string | null;
  diff_summary?: string | null;
  suggested_tests?: SuggestedTest[] | null;
  analysis_mode?: "llm" | "demo";
  fix_available?: boolean;
  original_code?: string;
}

export interface ProposeResponse {
  scenario_id: string;
  original_code: string;
  proposed_code: string;
  diff_summary: string;
  status: "proposed";
}

export interface TestResultItem {
  name: string;
  passed: boolean;
  expected: string;
  actual: string;
  error: string | null;
}

export interface TestResponse {
  status: "passed" | "failed" | "error";
  ran: boolean;
  sandbox_error: string | null;
  stderr: string;
  total: number;
  passed_count: number;
  failed_count: number;
  results: TestResultItem[];
}

const BASE = "/api";

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Request failed (${res.status}): ${text}`);
  }
  return res.json();
}

export async function fetchScenarios(): Promise<ScenarioSummary[]> {
  const res = await fetch(`${BASE}/scenarios`);
  if (!res.ok) throw new Error("Could not load scenarios");
  const data = await res.json();
  return data.scenarios;
}

export function analyzeCode(
  scenario_id: string | null,
  code: string,
  error_message: string
): Promise<AnalyzeResponse> {
  return postJSON<AnalyzeResponse>("/analyze", { scenario_id, code, error_message });
}

export function proposeFix(scenario_id: string): Promise<ProposeResponse> {
  return postJSON<ProposeResponse>("/propose", { scenario_id });
}

/** Preset scenario test run. */
export function testScenario(scenario_id: string, code: string): Promise<TestResponse> {
  return postJSON<TestResponse>("/test", { scenario_id, code });
}

/** General-mode test run against an AI-identified function and suggested tests. */
export function testCustom(
  code: string,
  function_name: string,
  tests: SuggestedTest[]
): Promise<TestResponse> {
  return postJSON<TestResponse>("/test", { code, function_name, tests });
}

export async function fetchHealth(): Promise<{ status: string; ai_mode: "llm" | "demo" }> {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error("backend unreachable");
  return res.json();
}
