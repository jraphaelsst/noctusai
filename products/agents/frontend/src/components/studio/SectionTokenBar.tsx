/**
 * Stacked horizontal bar: one segment per manifest section, width ∝ its
 * `tokens`. Product-local (driven by the Agent Studio manifest shape).
 * Colour is decorative only — every segment carries a title + aria label and
 * the legend repeats the numbers as text.
 */
import type { ManifestSection } from "@/api/studio/types";
import { sectionColor } from "./compiledSegments";

export function SectionTokenBar({
  manifest,
  onSelect,
}: {
  manifest: ManifestSection[];
  onSelect?: (indice: number) => void;
}) {
  const total = manifest.reduce((acc, s) => acc + s.tokens, 0);
  if (total <= 0) return null;
  return (
    <div className="space-y-2" data-testid="section-token-bar">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
        {manifest.map((s, i) => (
          <button
            key={`${s.chave}-${i}`}
            type="button"
            className={`${sectionColor(i)} h-full min-w-[2px] opacity-80 hover:opacity-100`}
            style={{ width: `${(s.tokens / total) * 100}%` }}
            title={`${s.titulo}: ~${s.tokens} tokens`}
            aria-label={`${s.titulo}: ${s.tokens} tokens`}
            onClick={() => onSelect?.(i)}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {manifest.map((s, i) => (
          <li key={`${s.chave}-${i}`} className="flex items-center gap-1.5">
            <span className={`inline-block h-2 w-2 rounded-sm ${sectionColor(i)}`} aria-hidden />
            {s.titulo} · {s.tokens.toLocaleString("pt-BR")} ({Math.round((s.tokens / total) * 100)}%)
          </li>
        ))}
      </ul>
    </div>
  );
}
