/**
 * The compiled master prompt, rendered block by block from the manifest
 * offsets (CONTRACT §C / §G "Prompt compilado"). Each block is labelled with
 * its source and — when `onOpenSource` is given — links back to the tab that
 * edits it. Used by the inspector tab AND `/studio/prompts/:hash`.
 */
import { forwardRef, useImperativeHandle, useMemo, useRef } from "react";
import { AlertTriangle, ExternalLink } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import type { ManifestSection } from "@/api/studio/types";
import { cn } from "@/lib/utils";
import { sectionColor, segmentCompiled, sourceTarget, type SourceTarget } from "./compiledSegments";

export interface CompiledPromptViewHandle {
  scrollToSection: (indice: number) => void;
}

export interface CompiledPromptViewProps {
  texto: string;
  manifest: ManifestSection[];
  clientId?: string | null;
  onOpenSource?: (target: SourceTarget) => void;
}

export const CompiledPromptView = forwardRef<CompiledPromptViewHandle, CompiledPromptViewProps>(
  function CompiledPromptView({ texto, manifest, clientId = null, onOpenSource }, ref) {
    const { segmentos, problemas } = useMemo(() => segmentCompiled(texto, manifest), [texto, manifest]);
    const blockRefs = useRef<Record<number, HTMLElement | null>>({});

    useImperativeHandle(ref, () => ({
      scrollToSection: (indice) => blockRefs.current[indice]?.scrollIntoView({ behavior: "smooth", block: "start" }),
    }));

    return (
      <div className="space-y-3" data-testid="compiled-prompt-view">
        {problemas.length > 0 && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700" role="alert">
            <p className="flex items-center gap-1 font-semibold">
              <AlertTriangle className="h-3.5 w-3.5" /> O manifesto não corresponde ao texto:
            </p>
            <ul className="ml-4 list-disc">
              {problemas.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        {segmentos.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="compiled-empty">
            O prompt compilado está vazio.
          </p>
        )}
        {segmentos.map((seg) => {
          if (seg.tipo === "orfao") {
            return (
              <section
                key={`orfao-${seg.inicio}`}
                className="rounded-lg border border-dashed border-amber-500/60"
                data-testid="compiled-orphan"
              >
                <header className="border-b border-border px-3 py-1.5 text-xs text-amber-700">
                  Texto sem seção no manifesto (caracteres {seg.inicio}–{seg.fim})
                </header>
                <pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs">{seg.texto}</pre>
              </section>
            );
          }
          const { secao, indice } = seg;
          const target = sourceTarget(secao, clientId);
          return (
            <section
              key={`${secao.chave}-${indice}`}
              ref={(el) => {
                blockRefs.current[indice] = el;
              }}
              className="scroll-mt-4 rounded-lg border border-border bg-card"
              data-testid="compiled-section"
              data-chave={secao.chave}
              data-inicio={secao.inicio}
              data-fim={secao.fim}
            >
              <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-1.5">
                <span className={cn("inline-block h-2.5 w-2.5 rounded-sm", sectionColor(indice))} aria-hidden />
                <span className="text-xs font-semibold text-foreground">{secao.titulo}</span>
                <Badge variant={secao.origem.tipo === "auto" ? "muted" : "outline"}>
                  {target?.rotulo ?? (secao.origem.tipo === "auto" ? "Automática" : "Seção do prompt")}
                </Badge>
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {secao.chars.toLocaleString("pt-BR")} caracteres · ~{secao.tokens.toLocaleString("pt-BR")} tokens
                </span>
                {target && onOpenSource && (
                  <button
                    type="button"
                    className="ml-auto inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                    onClick={() => onOpenSource(target)}
                    data-testid="compiled-open-source"
                  >
                    Abrir origem <ExternalLink className="h-3 w-3" />
                  </button>
                )}
              </header>
              <pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs leading-relaxed text-foreground">
                {seg.texto}
              </pre>
            </section>
          );
        })}
      </div>
    );
  },
);
