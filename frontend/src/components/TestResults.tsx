import type { TestResponse } from "../api";

export default function TestResults({ report, codeLabel }: { report: TestResponse; codeLabel: string }) {
  if (!report.ran) {
    return (
      <div className="panel panel--error">
        <div className="panel__title">Execution blocked</div>
        <p className="muted">
          The sandbox refused to run this code{codeLabel ? ` (${codeLabel})` : ""}.
        </p>
        <pre className="sandbox-error">{report.sandbox_error}</pre>
        {report.stderr && (
          <>
            <div className="panel__subtitle">stderr</div>
            <pre className="sandbox-error">{report.stderr}</pre>
          </>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="test-summary">
        <div>
          <span className="test-summary__count test-summary__count--pass">{report.passed_count}</span>
          <span className="muted"> / {report.total} passed</span>
        </div>
        {report.failed_count > 0 && (
          <div className="test-summary__count test-summary__count--fail">
            {report.failed_count} failed
          </div>
        )}
      </div>
      <div className="test-list">
        {report.results.map((r, idx) => (
          <div key={idx} className={`test-item ${r.passed ? "test-item--pass" : "test-item--fail"}`}>
            <div className="test-item__header">
              <span className="test-item__icon">{r.passed ? "✓" : "✗"}</span>
              <span className="test-item__name">{r.name}</span>
            </div>
            {!r.passed && (
              <div className="test-item__detail">
                {r.error ? (
                  <div>
                    <span className="muted">Raised: </span>
                    <code>{r.error}</code>
                  </div>
                ) : (
                  <div>
                    <span className="muted">Expected </span>
                    <code>{r.expected}</code>
                    <span className="muted"> — got </span>
                    <code>{r.actual}</code>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
