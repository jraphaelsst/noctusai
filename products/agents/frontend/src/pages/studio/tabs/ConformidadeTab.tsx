/**
 * Agent Studio — "Conformidade" (Julia v2 CONTRACT §3.5 E3): per rule on/off + policy
 * (registrar | bloquear) and the list of violations the post-turn detectors recorded.
 *
 * NOC-REMEDIATE[julia-studio-conformidade-api]: the HTTP routes do not exist yet (see
 * `hooks/studio/useConformidade.ts`); a 404/405 shows the honest unavailable state.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Badge, EmptyState, Select, Switch } from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { RestrictedNotice } from "@/components/studio/ConteudoChrome";
import { useConformidadeRegras, useConformidadeViolacoes, useDefinirRegra } from "@/hooks/studio/useConformidade";
import { ApiError, errorMessage } from "@/lib/errors";

function indisponivel(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 405);
}

export default function ConformidadeTab({ agentKey }: { agentKey: string }) {
  const regras = useConformidadeRegras(agentKey);
  const violacoes = useConformidadeViolacoes(agentKey);
  const definir = useDefinirRegra(agentKey);
  const [erro, setErro] = useState<string | null>(null);

  if (regras.showSkeleton) return <StudioLoading rows={3} />;
  if (regras.isError) {
    if (indisponivel(regras.error)) {
      return <EmptyState message="A API de conformidade ainda não está disponível neste ambiente." />;
    }
    if ((regras.error as { status?: number }).status === 403) return <RestrictedNotice error={regras.error} />;
    return <StudioError error={regras.error} onRetry={regras.refetch} />;
  }

  async function mudar(regra: string, p: { ativo?: boolean; politica?: "registrar" | "bloquear" }) {
    setErro(null);
    try {
      await definir.mutateAsync({ regra, ...p });
      toast.success("Regra atualizada.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-6" data-testid="conformidade-tab">
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Regras</h2>
        {regras.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
        {(regras.data ?? []).length === 0 ? (
          <EmptyState message="Nenhuma regra de conformidade configurada." />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border bg-card">
            {(regras.data ?? []).map((r) => (
              <li key={r.regra} className="flex flex-wrap items-center gap-3 px-4 py-3" data-testid={`regra-${r.regra}`}>
                <span className="font-mono text-sm">{r.regra}</span>
                <Switch checked={r.ativo} aria-label={`Ativar ${r.regra}`} disabled={definir.isPending} onCheckedChange={(v) => mudar(r.regra, { ativo: v })} />
                <Select
                  aria-label={`Política de ${r.regra}`}
                  className="ml-auto w-40"
                  value={r.politica}
                  disabled={definir.isPending}
                  onChange={(e) => mudar(r.regra, { politica: e.target.value as "registrar" | "bloquear" })}
                >
                  <option value="registrar">Registrar</option>
                  <option value="bloquear">Bloquear</option>
                </Select>
              </li>
            ))}
          </ul>
        )}
        {erro && <p className="text-sm text-destructive" role="alert" data-testid="conformidade-erro">{erro}</p>}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Violações recentes</h2>
        {violacoes.showSkeleton ? (
          <StudioLoading rows={2} />
        ) : violacoes.isError ? (
          <StudioError error={violacoes.error} onRetry={violacoes.refetch} />
        ) : (violacoes.data ?? []).length === 0 ? (
          <EmptyState message="Nenhuma violação registrada." />
        ) : (
          <table className="w-full rounded-lg border border-border bg-card text-sm" data-testid="violacoes-tabela">
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Quando</th>
                <th className="px-3 py-2">Regra</th>
                <th className="px-3 py-2">Política</th>
                <th className="px-3 py-2">Resultado</th>
              </tr>
            </thead>
            <tbody>
              {(violacoes.data ?? []).map((v) => (
                <tr key={v.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 tabular-nums">{new Date(v.created_at).toLocaleString("pt-BR")}</td>
                  <td className="px-3 py-2 font-mono text-xs">{v.regra}</td>
                  <td className="px-3 py-2">{v.politica}</td>
                  <td className="px-3 py-2">{v.bloqueada ? <Badge variant="outline">Resposta bloqueada</Badge> : <Badge variant="muted">Registrada</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
