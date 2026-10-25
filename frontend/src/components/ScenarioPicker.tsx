import type { ScenarioSummary } from "../api";

export default function ScenarioPicker({
  scenarios,
  selectedId,
  onSelect,
}: {
  scenarios: ScenarioSummary[];
  selectedId: string | null;
  onSelect: (s: ScenarioSummary) => void;
}) {
  return (
    <div className="scenario-grid">
      {scenarios.map((s) => (
        <button
          key={s.id}
          className={`scenario-card ${selectedId === s.id ? "scenario-card--active" : ""}`}
          onClick={() => onSelect(s)}
        >
          <div className="scenario-card__title">{s.title}</div>
          <div className="scenario-card__desc">{s.short_description}</div>
          <div className="scenario-card__fn">{s.function_name}()</div>
        </button>
      ))}
    </div>
  );
}
