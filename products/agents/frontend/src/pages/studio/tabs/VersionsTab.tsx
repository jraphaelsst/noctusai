/**
 * Agent Studio — "Versões" (CONTRACT §G, §A3, §A8): the version table,
 * "Criar rascunho a partir desta" (restore = clone into a new draft),
 * discard draft, a two-version diff picker (§D1 diff endpoint), and the
 * publish dialog with the eval-gate status. Deep link `?publicar=1` opens the
 * dialog (the Visão geral quick action).
 */
import { useConfirm } from "@noctusai/lib/components";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FilePlus2, Rocket, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button, EmptyState } from "@noctusai/lib/design-system";
import type { VersionSummary } from "@/api/studio/types";
import { PublishDraftDialog, pct } from "@/components/studio/PublishDraftDialog";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { VersionDiffSummary } from "@/components/studio/VersionDiffSummary";
import { shortHash } from "@/components/studio/compiledSegments";
import { VersionStatusBadge } from "@/components/studio/VersionStatusBadge";
import {
  useAgentVersionRefs,
  useCreateDraft,
  useDiscardDraft,
  useVersionDiff,
} from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";
import { studioTabHref } from "../studioTabs";

const SELECT_CLASS =
  "h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/50";

// ── Tab ───────────────────────────────────────────────────────────────────────

export default function VersionsTab({ agentKey }: { agentKey: string }) {
  const confirm = useConfirm();
  const isAdmin = useIsAdmin();
  const [params, setParams] = useSearchParams();
  const { data: agent, draft, ativa, showSkeleton, isRefreshing, isError, error, refetch } = useAgentVersionRefs(agentKey);
  const createDraft = useCreateDraft(agentKey);
  const discard = useDiscardDraft(agentKey);
  const versoes = useMemo(() => agent?.versoes ?? [], [agent]);

  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  useEffect(() => {
    // Default pair: active → draft; else the two newest.
    if (a || b || versoes.length < 2) return;
    setA((ativa ?? versoes[1]).id);
    setB((draft ?? versoes[0]).id);
  }, [versoes, ativa, draft, a, b]);
  const diff = useVersionDiff(agentKey, a || null, b || null);

  const publishOpen = params.get("publicar") === "1" && isAdmin && !!draft;
  function setPublishOpen(open: boolean) {
    const next = new URLSearchParams(params);
    if (open) next.set("publicar", "1");
    else next.delete("publicar");
    setParams(next);
  }

  if (showSkeleton) return <StudioLoading rows={4} />;
  if (isError) return <StudioError error={error} onRetry={refetch} />;
  if (!agent || versoes.length === 0) return <EmptyState message="Este agente ainda não tem versões." />;

  async function handleRestore(v: VersionSummary) {
    try {
      const d = await createDraft.mutateAsync({ from_version_id: v.id });
      toast.success(`Rascunho v${d.versao} criado a partir da v${v.versao}.`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function handleDiscard(v: VersionSummary) {
    if (!(await confirm({ title: `Descartar o rascunho v${v.versao}?`, description: "Esta ação não pode ser desfeita.", confirmLabel: "Descartar", tone: "danger" }))) return;
    try {
      await discard.mutateAsync({ draftId: v.id });
      toast.success("Rascunho descartado.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const label = (id: string) => {
    const v = versoes.find((x) => x.id === id);
    return v ? `v${v.versao} (${v.status})` : "—";
  };

  return (
    <div className="space-y-6" data-testid="versions-tab">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Versões</h2>
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
        {isAdmin && draft && (
          <Button variant="primary" className="ml-auto" onClick={() => setPublishOpen(true)} data-testid="versions-publicar">
            <Rocket className="mr-1 h-4 w-4" /> Publicar rascunho v{draft.versao}
          </Button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Versão</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Notas</th>
              <th className="px-3 py-2 font-medium">Modelo</th>
              <th className="px-3 py-2 font-medium">Criada</th>
              <th className="px-3 py-2 font-medium">Publicada</th>
              <th className="px-3 py-2 font-medium">Hash</th>
              <th className="px-3 py-2 font-medium">Avaliação</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {versoes.map((v) => (
              <tr key={v.id} className="border-b border-border last:border-0" data-testid={`version-row-${v.versao}`}>
                <td className="px-3 py-2 font-medium tabular-nums">
                  v{v.versao}
                  {v.versao_semver && (
                    <span className="ml-1 font-mono text-xs text-muted-foreground" data-testid={`version-semver-${v.versao}`}>
                      {v.versao_semver}
                      {v.package_sha ? ` · ${v.package_sha.slice(0, 8)}` : ""}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <VersionStatusBadge status={v.status} />
                </td>
                <td className="max-w-[240px] truncate px-3 py-2 text-xs" title={v.notas ?? ""}>
                  {v.notas || "—"}
                </td>
                <td className="px-3 py-2 text-xs">{v.model}</td>
                <td className="px-3 py-2 text-xs">{formatDate(v.created_at, true)}</td>
                <td className="px-3 py-2 text-xs">{formatDate(v.published_at, true)}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{shortHash(v.compiled_hash, 8)}</td>
                <td className="px-3 py-2 text-xs tabular-nums">{pct(v.eval_score)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right">
                  <Link
                    to={studioTabHref(agentKey, "compilado", { versao: v.id })}
                    className="mr-2 text-xs text-primary hover:underline"
                  >
                    Inspecionar
                  </Link>
                  {isAdmin && v.status !== "rascunho" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={!!draft || createDraft.isPending}
                      title={draft ? "Já existe um rascunho — publique ou descarte antes." : undefined}
                      onClick={() => handleRestore(v)}
                      data-testid={`version-restore-${v.versao}`}
                    >
                      <FilePlus2 className="mr-1 h-3.5 w-3.5" /> Criar rascunho a partir desta
                    </Button>
                  )}
                  {isAdmin && v.status === "rascunho" && (
                    <Button size="sm" variant="ghost" disabled={discard.isPending} onClick={() => handleDiscard(v)}>
                      <Trash2 className="mr-1 h-3.5 w-3.5 text-destructive" /> Descartar
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="versions-diff">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">Comparar versões</h3>
          <select aria-label="Versão A" className={SELECT_CLASS} value={a} onChange={(e) => setA(e.target.value)}>
            <option value="">Versão A…</option>
            {versoes.map((v) => (
              <option key={v.id} value={v.id}>
                {label(v.id)}
              </option>
            ))}
          </select>
          <span className="text-muted-foreground">→</span>
          <select aria-label="Versão B" className={SELECT_CLASS} value={b} onChange={(e) => setB(e.target.value)}>
            <option value="">Versão B…</option>
            {versoes.map((v) => (
              <option key={v.id} value={v.id}>
                {label(v.id)}
              </option>
            ))}
          </select>
          {diff.isRefreshing && <span className="text-xs text-muted-foreground">Comparando…</span>}
        </div>
        {!a || !b || a === b ? (
          <p className="text-xs text-muted-foreground">Escolha duas versões diferentes.</p>
        ) : diff.showSkeleton ? (
          <StudioLoading rows={2} />
        ) : diff.isError ? (
          <StudioError error={diff.error} onRetry={diff.refetch} />
        ) : diff.data ? (
          <VersionDiffSummary diff={diff.data} rotuloA={label(a)} rotuloB={label(b)} />
        ) : null}
      </section>

      {publishOpen && draft && (
        <PublishDraftDialog agentKey={agentKey} draft={draft} limiar={agent.publicacao_limiar} onClose={() => setPublishOpen(false)} />
      )}
    </div>
  );
}
