import { diffLines } from "../diff";

export default function DiffView({ original, proposed }: { original: string; proposed: string }) {
  const lines = diffLines(original, proposed);

  return (
    <div className="diff-view scroll-x">
      <pre className="diff-view__code">
        {lines.map((line, idx) => (
          <div key={idx} className={`diff-line diff-line--${line.type}`}>
            <span className="diff-line__marker">
              {line.type === "add" ? "+" : line.type === "remove" ? "−" : " "}
            </span>
            <span>{line.text || " "}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}
