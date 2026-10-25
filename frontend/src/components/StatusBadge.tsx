type Status = "proposed" | "untested" | "passed" | "failed";

const LABELS: Record<Status, string> = {
  proposed: "Proposed",
  untested: "Untested",
  passed: "Passed",
  failed: "Failed",
};

const COLORS: Record<Status, string> = {
  proposed: "var(--status-proposed)",
  untested: "var(--status-untested)",
  passed: "var(--status-passed)",
  failed: "var(--status-failed)",
};

export default function StatusBadge({ status }: { status: Status }) {
  const color = COLORS[status];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px",
        borderRadius: 999,
        fontSize: 12.5,
        fontFamily: "var(--font-mono)",
        color,
        background: `${color}1a`,
        border: `1px solid ${color}40`,
        lineHeight: 1.6,
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: color }} />
      {LABELS[status]}
    </span>
  );
}
