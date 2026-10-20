/**
 * Structured editor for a JSON value (rule trees, point tables, axis config). Valid JSON flows to
 * `onChange(value, null)`; invalid JSON reports `onChange(undefined, message)` and the parent must
 * block its save — the raw text is never sent.
 */
import { useEffect, useRef, useState } from "react";
import { Textarea } from "@noctusai/lib/design-system";

export function JsonField({
  id,
  label,
  value,
  onChange,
  disabled,
  rows = 6,
}: {
  id: string;
  label: string;
  value: unknown;
  onChange: (value: unknown, error: string | null) => void;
  disabled?: boolean;
  rows?: number;
}) {
  const serialized = JSON.stringify(value ?? null, null, 2);
  const [text, setText] = useState(serialized);
  const [erro, setErro] = useState<string | null>(null);
  const last = useRef(serialized);

  // A new server/parent value replaces the text; a value the user typed (already valid) does not.
  useEffect(() => {
    if (serialized !== last.current) {
      last.current = serialized;
      setText(serialized);
      setErro(null);
    }
  }, [serialized]);

  function handle(next: string) {
    setText(next);
    try {
      const parsed = JSON.parse(next);
      setErro(null);
      last.current = JSON.stringify(parsed ?? null, null, 2);
      onChange(parsed, null);
    } catch {
      setErro("JSON inválido");
      onChange(undefined, "JSON inválido");
    }
  }

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium">{label}</label>
      <Textarea id={id} monospace rows={rows} disabled={disabled} value={text} onChange={(e) => handle(e.target.value)} aria-invalid={!!erro} />
      {erro && <p className="mt-1 text-xs text-destructive" role="alert">{erro}</p>}
    </div>
  );
}
