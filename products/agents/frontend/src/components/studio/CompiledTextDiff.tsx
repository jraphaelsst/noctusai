/**
 * Side-by-side line diff of two compiled prompts. Product-local: the seed has
 * no diff organ, and this one is shaped around compiled-prompt review
 * (monospace, line numbers, whole-text scroll). If a second product needs a
 * text diff, promote `lineDiff.ts` + this view to `@noctusai/lib`.
 */
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { lineDiff, type DiffRowKind } from "./lineDiff";

const LEFT_BG: Record<DiffRowKind, string> = {
  igual: "",
  removida: "bg-rose-500/10",
  alterada: "bg-amber-500/10",
  adicionada: "bg-muted/40",
};
const RIGHT_BG: Record<DiffRowKind, string> = {
  igual: "",
  removida: "bg-muted/40",
  alterada: "bg-amber-500/10",
  adicionada: "bg-emerald-500/10",
};

export function CompiledTextDiff({
  textoA,
  textoB,
  rotuloA,
  rotuloB,
}: {
  textoA: string;
  textoB: string;
  rotuloA: string;
  rotuloB: string;
}) {
  const diff = useMemo(() => lineDiff(textoA, textoB), [textoA, textoB]);

  if (diff.demasiado) {
    return (
      <div className="space-y-2" data-testid="compiled-diff-too-large">
        <p className="text-xs text-amber-600">
          Textos grandes demais para a comparação linha a linha — exibindo os dois lado a lado, sem marcação.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {[textoA, textoB].map((t, i) => (
            <pre key={i} className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded border border-border p-2 font-mono text-[11px]">
              {t}
            </pre>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="compiled-diff">
      <p className="text-xs text-muted-foreground">
        <span className="text-emerald-600">+{diff.adicionadas}</span> ·{" "}
        <span className="text-rose-600">−{diff.removidas}</span> linhas
      </p>
      <div className="max-h-[60vh] overflow-auto rounded-lg border border-border">
        <table className="w-full table-fixed border-collapse font-mono text-[11px]">
          <thead className="sticky top-0 bg-card">
            <tr className="text-left text-muted-foreground">
              <th className="w-10" />
              <th className="px-2 py-1 font-medium">{rotuloA}</th>
              <th className="w-10" />
              <th className="px-2 py-1 font-medium">{rotuloB}</th>
            </tr>
          </thead>
          <tbody>
            {diff.linhas.map((row, idx) => (
              <tr key={idx} data-diff={row.tipo}>
                <td className="select-none px-1 text-right align-top text-muted-foreground">{row.linhaA ?? ""}</td>
                <td className={cn("whitespace-pre-wrap break-words px-2 align-top", LEFT_BG[row.tipo])}>
                  {row.esquerda ?? ""}
                </td>
                <td className="select-none border-l border-border px-1 text-right align-top text-muted-foreground">
                  {row.linhaB ?? ""}
                </td>
                <td className={cn("whitespace-pre-wrap break-words px-2 align-top", RIGHT_BG[row.tipo])}>
                  {row.direita ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
