/**
 * Renders a §D1 `VersionDiff`: section / skill states, changed settings, and
 * the side-by-side compiled text. Shared by the Versões tab (diff picker) and
 * the inspector's "Comparar com publicada".
 */
import { Badge } from "@noctusai/lib/design-system";
import type { DiffState, VersionDiff } from "@/api/studio/types";
import { CompiledTextDiff } from "./CompiledTextDiff";
import { shortHash } from "./compiledSegments";

const STATE_LABEL: Record<DiffState, string> = {
  igual: "igual",
  alterada: "alterada",
  nova: "nova",
  removida: "removida",
};

function StateBadge({ estado }: { estado: DiffState }) {
  const variant = estado === "igual" ? "muted" : estado === "removida" ? "destructive" : estado === "nova" ? "default" : "outline";
  return <Badge variant={variant}>{STATE_LABEL[estado]}</Badge>;
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function VersionDiffSummary({ diff, rotuloA, rotuloB }: { diff: VersionDiff; rotuloA: string; rotuloB: string }) {
  const changedSecoes = diff.secoes.filter((s) => s.estado !== "igual");
  const changedSkills = diff.skills.filter((s) => s.estado !== "igual");
  const mesmoHash = diff.a.hash === diff.b.hash;
  return (
    <div className="space-y-4" data-testid="version-diff">
      <p className="text-xs text-muted-foreground">
        <span className="font-mono">{shortHash(diff.a.hash)}</span> → <span className="font-mono">{shortHash(diff.b.hash)}</span>
        {mesmoHash && " · prompts idênticos"}
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        <div>
          <h4 className="mb-1 text-xs font-semibold">Seções ({changedSecoes.length} alteradas)</h4>
          <ul className="space-y-1 text-xs">
            {diff.secoes.map((s) => (
              <li key={s.chave} className="flex items-center gap-2">
                <span className="font-mono">{s.chave}</span>
                <StateBadge estado={s.estado} />
              </li>
            ))}
            {diff.secoes.length === 0 && <li className="text-muted-foreground">Nenhuma.</li>}
          </ul>
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold">Skills ({changedSkills.length} alteradas)</h4>
          <ul className="space-y-1 text-xs">
            {diff.skills.map((s) => (
              <li key={s.nome} className="flex items-center gap-2">
                <span className="font-mono">{s.nome}</span>
                <StateBadge estado={s.estado} />
              </li>
            ))}
            {diff.skills.length === 0 && <li className="text-muted-foreground">Nenhuma.</li>}
          </ul>
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold">Configurações</h4>
          {diff.configuracoes.length === 0 ? (
            <p className="text-xs text-muted-foreground">Sem diferenças.</p>
          ) : (
            <ul className="space-y-1 text-xs">
              {diff.configuracoes.map((c) => (
                <li key={c.campo}>
                  <span className="font-mono">{c.campo}</span>: {fmt(c.a)} → {fmt(c.b)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {!mesmoHash && <CompiledTextDiff textoA={diff.texto_a} textoB={diff.texto_b} rotuloA={rotuloA} rotuloB={rotuloB} />}
    </div>
  );
}
