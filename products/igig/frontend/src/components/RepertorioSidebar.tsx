/**
 * RepertorioSidebar — Módulo 2's required automation.
 *
 * The spec: "sempre que um designer ou copywriter abrir uma tarefa vinculada a
 * um cliente específico, o sistema deve exibir um card lateral persistente com
 * a paleta de cores HEX, tom de voz e pilares editoriais ativos."
 *
 * So this is ambient chrome on a work screen, and that shapes every decision
 * here:
 *   - it NEVER blocks — no error banner, no modal. A client with no brand yet
 *     shows a quiet prompt, not a failure.
 *   - HEX codes are copyable, because the whole point is a designer using them
 *     without leaving the task.
 *   - termos proibidos are rendered as a warning, since getting those wrong is
 *     the expensive mistake this card exists to prevent.
 */
import { useState } from "react";
import { Badge } from "@noctusai/lib/design-system";
import { Ban, Check, Copy, Palette } from "lucide-react";

import { useRepertorio } from "@/hooks/useMarca";

function Swatch({ nome, hex }: { nome: string; hex: string }) {
  const [copiado, setCopiado] = useState(false);

  function copiar() {
    // Clipboard can be denied (insecure context / permissions). The hex is on
    // screen regardless, so a refusal degrades to reading it — never to a
    // broken-looking button that claims success.
    void navigator.clipboard
      ?.writeText(hex)
      .then(() => {
        setCopiado(true);
        window.setTimeout(() => setCopiado(false), 1200);
      })
      .catch(() => undefined);
  }

  return (
    <button
      type="button"
      onClick={copiar}
      title={`Copiar ${hex}`}
      aria-label={`Copiar ${nome} ${hex}`}
      className="flex w-full items-center gap-2 rounded px-1 py-1 text-left hover:bg-muted"
    >
      <span
        className="h-5 w-5 shrink-0 rounded border border-border"
        style={{ backgroundColor: hex }}
      />
      <span className="min-w-0 flex-1 truncate text-xs text-foreground">{nome}</span>
      <code className="text-[11px] text-muted-foreground">{hex}</code>
      {copiado ? (
        <Check className="h-3 w-3 text-foreground" />
      ) : (
        <Copy className="h-3 w-3 text-muted-foreground" />
      )}
    </button>
  );
}

export function RepertorioSidebar({ clienteId }: { clienteId: string | undefined }) {
  const { repertorio, loading } = useRepertorio(clienteId);

  if (!clienteId) return null;

  return (
    <aside
      aria-label="Repertório da marca"
      className="w-64 shrink-0 space-y-4 rounded-lg border border-border bg-card p-4"
    >
      <header className="flex items-center gap-2">
        <Palette className="h-4 w-4 text-muted-foreground" />
        <h2 className="truncate text-sm font-semibold text-foreground">
          {repertorio?.marca_nome || repertorio?.cliente_nome || "Repertório"}
        </h2>
      </header>

      {loading ? (
        <p className="text-xs text-muted-foreground">Carregando repertório…</p>
      ) : !repertorio ? (
        /* Never an error state — the sidebar must not shout over someone's work. */
        <p className="text-xs text-muted-foreground">Repertório indisponível.</p>
      ) : (
        <>
          {repertorio.logo_url && (
            <img
              src={repertorio.logo_url}
              alt={`Logo ${repertorio.marca_nome ?? ""}`}
              className="max-h-16 w-full object-contain"
            />
          )}

          {repertorio.paleta.length > 0 && (
            <section>
              <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Paleta
              </h3>
              <div className="space-y-0.5">
                {repertorio.paleta.map((cor) => (
                  <Swatch key={`${cor.nome}-${cor.hex}`} nome={cor.nome} hex={cor.hex} />
                ))}
              </div>
            </section>
          )}

          {repertorio.tom_de_voz && (
            <section>
              <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Tom de voz
                {repertorio.nivel_formalidade && (
                  <Badge variant="muted" className="ml-2">
                    {repertorio.nivel_formalidade}
                  </Badge>
                )}
              </h3>
              <p className="whitespace-pre-wrap text-xs text-foreground">
                {repertorio.tom_de_voz}
              </p>
            </section>
          )}

          {repertorio.termos_proibidos && (
            <section>
              <h3 className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-destructive">
                <Ban className="h-3 w-3" />
                Termos proibidos
              </h3>
              <p className="whitespace-pre-wrap text-xs text-destructive">
                {repertorio.termos_proibidos}
              </p>
            </section>
          )}

          {repertorio.linhas_editoriais.length > 0 && (
            <section>
              <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Linhas editoriais
              </h3>
              <ul className="flex flex-wrap gap-1">
                {repertorio.linhas_editoriais.map((linha) => (
                  <li key={linha.nome}>
                    <Badge variant="outline">{linha.nome}</Badge>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {!repertorio.marca_nome && (
            <p className="text-xs text-muted-foreground">
              Este cliente ainda não tem marca cadastrada.
            </p>
          )}
        </>
      )}
    </aside>
  );
}

export default RepertorioSidebar;
