import { useRef } from "react";

interface Props {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  minLines?: number;
  label?: string;
}

export default function CodeEditor({ value, onChange, readOnly, minLines = 8, label }: Props) {
  const gutterRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const lineCount = Math.max(value.split("\n").length, minLines);
  const lines = Array.from({ length: lineCount }, (_, i) => i + 1);

  const syncScroll = () => {
    if (gutterRef.current && taRef.current) {
      gutterRef.current.scrollTop = taRef.current.scrollTop;
    }
  };

  return (
    <div className="code-editor">
      {label && <div className="code-editor__label">{label}</div>}
      <div className="code-editor__body">
        <div className="code-editor__gutter" ref={gutterRef}>
          {lines.map((n) => (
            <div key={n}>{n}</div>
          ))}
        </div>
        <textarea
          ref={taRef}
          className="code-editor__textarea"
          value={value}
          onChange={(e) => onChange?.(e.target.value)}
          onScroll={syncScroll}
          readOnly={readOnly}
          spellCheck={false}
          rows={lineCount}
          placeholder={
            'def get_discounted_price(price, discount_percent):\n' +
            '    discount = price * discount_percent / 100\n' +
            '    return price - discount\n\n' +
            '# Paste your own buggy function above, or load a sample below.'
          }
        />
      </div>
    </div>
  );
}
