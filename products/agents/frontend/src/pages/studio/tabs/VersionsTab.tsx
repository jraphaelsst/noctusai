/**
 * Agent Studio — "Versões" (CONTRACT §G, §A3, §A8): the version table,
 * "Criar rascunho a partir desta" (restore = clone into a new draft),
 * discard draft, a two-version diff picker (§D1 diff endpoint), and the
 * publish dialog with the eval-gate status. Deep link `?publicar=1` opens the
 * dialog (the Visão geral quick action).
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, FilePlus2, Rocket, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import {
  OVERRIDE_REASON_MIN,
  type CompileWarning,
  type PublishErrorBody,
  type VersionSummary,
} from "@/api/studio/types";
import { PromptMarkdownField } from "@/components/studio/PromptMarkdownField";
import { StudioEmpty, StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { VersionDiffSummary } from "@/components/studio/VersionDiffSummary";
import { shortHash } from "@/components/studio/compiledSegments";
import { VersionStatusBadge } from "@/components/studio/VersionStatusBadge";
import { useCompiled } from "@/hooks/studio/useCompiled";
import {
  useAgentVersionRefs,
  useCreateDraft,
  useDiscardDraft,
  usePublishDraft,
  useVersionDiff,
} from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { ApiError, errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";
import { studioTabHref } from "../studioTabs";

const SELECT_CLASS =
  "h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

const pct = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `${Math.round(n * 1000) / 10}%`);

// ── Publish dialog ────────────────────────────────────────────────────────────

function PublishDialog({
  agentKey,
  draft,
  limiar,
  onClose,
}: {
  agentKey: string;
  draft: VersionSummary;
  limiar: number;
  onClose: () => void;
}) {
  const compiled = useCompiled(agentKey, draft.id);
  const publish = usePublishDraft(agentKey);
  const [notas, setNotas] = useState(draft.notas ?? "");
  const [override, setOverride] = useState("");
  const [serverGate, setServerGate] = useState<PublishErrorBody | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const hashAtual = compiled.data?.hash ?? draft.compiled_hash;
  const bloqueantes: CompileWarning[] = [
    ...(compiled.data?.avisos.filter((a) => a.bloqueante) ?? []),
    ...(serverGate?.code === "compile_blocked" ? (serverGate.avisos ?? []).filter((a) => a.bloqueante) : []),
  ];
  const avisos = compiled.data?.avisos.filter((a) => !a.bloqueante) ?? [];
  const preCheckFails = draft.eval_score === null || draft.eval_score < limiar;
  const gateFails = preCheckFails || serverGate?.code === "eval_required";
  const ultima = serverGate?.ultima_execucao;

  async function handlePublish() {
    setErro(null);
    const reason = override.trim();
    if (gateFails && reason && reason.length < OVERRIDE_REASON_MIN) {
      setErro(`A justificativa precisa de pelo menos ${OVERRIDE_REASON_MIN} caracteres.`);
      return;
    }
    try {
      const published = await publish.mutateAsync({
        notas: notas.trim() || undefined,
        override_reason: gateFails && reason ? reason : undefined,
      });
      toast.success(`Versão v${published.versao} publicada.`);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.body && typeof err.body === "object") {
        const body = err.body as PublishErrorBody;
        if (body.code === "eval_required" || body.code === "compile_blocked") setServerGate(body);
      }
      setErro(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title="Publicar rascunho" className="max-w-xl">
      <DialogHeader>
        <h2 className="text-base font-semibold">Publicar rascunho v{draft.versao}</h2>
      </DialogHeader>
      <DialogBody className="space-y-4" data-testid="publish-dialog">
        <div className="rounded-md border border-border p-3 text-sm" data-testid="publish-gate">
          <p className="font-medium">Portão de avaliação</p>
          <p className="text-xs text-muted-foreground">
            Hash atual: <span className="font-mono">{compiled.showSkeleton ? "compilando…" : shortHash(hashAtual, 16)}</span>
          </p>
          <p className="mt-1">
            Última avaliação: <strong>{pct(ultima ? ultima.score : draft.eval_score)}</strong> · limiar{" "}
            <strong>{pct(ultima ? ultima.limiar : limiar)}</strong>
          </p>
          {ultima && ultima.compiled_hash !== (serverGate?.hash_atual ?? hashAtual) && (
            <p className="text-xs text-amber-700">
              A última avaliação foi feita em outro hash ({shortHash(ultima.compiled_hash)}) — o rascunho mudou desde então.
            </p>
          )}
          {serverGate?.code === "eval_required" && !ultima && (
            <p className="text-xs text-amber-700">Nenhuma avaliação concluída para este rascunho.</p>
          )}
          <p className={`mt-1 text-xs ${gateFails ? "text-amber-700" : "text-emerald-600"}`}>
            {gateFails
              ? "O portão não está satisfeito: rode uma avaliação na aba Avaliações ou registre uma justificativa de exceção."
              : "Avaliação acima do limiar — o servidor confirma no hash atual ao publicar."}
          </p>
        </div>

        {compiled.isError && (
          <p className="text-xs text-destructive">Não foi possível compilar o rascunho: {errorMessage(compiled.error)}</p>
        )}
        {bloqueantes.length > 0 && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3" role="alert" data-testid="publish-bloqueantes">
            <p className="flex items-center gap-1 text-sm font-medium text-destructive">
              <AlertTriangle className="h-4 w-4" /> Avisos bloqueantes — corrija antes de publicar (sem exceção possível):
            </p>
            <ul className="ml-5 list-disc text-xs">
              {bloqueantes.map((a, i) => (
                <li key={`${a.codigo}-${i}`}>{a.mensagem}</li>
              ))}
            </ul>
          </div>
        )}
        {avisos.length > 0 && (
          <ul className="ml-5 list-disc text-xs text-amber-700">
            {avisos.map((a, i) => (
              <li key={`${a.codigo}-${i}`}>{a.mensagem}</li>
            ))}
          </ul>
        )}

        <div>
          <label htmlFor="publish-notas" className="mb-1 block text-xs font-medium">
            Notas da versão
          </label>
          <PromptMarkdownField id="publish-notas" value={notas} onChange={setNotas} rows={3} mono={false} semTokens />
        </div>

        {gateFails && bloqueantes.length === 0 && (
          <div data-testid="publish-override">
            <label htmlFor="publish-override-reason" className="mb-1 block text-xs font-medium">
              Justificativa de exceção (mínimo {OVERRIDE_REASON_MIN} caracteres — fica registrada na versão)
            </label>
            <PromptMarkdownField
              id="publish-override-reason"
              value={override}
              onChange={setOverride}
              rows={3}
              mono={false}
              semTokens
            />
          </div>
        )}

        {erro && (
          <p className="text-sm text-destructive" role="alert" data-testid="publish-erro">
            {erro}
          </p>
        )}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          onClick={handlePublish}
          disabled={
            publish.isPending ||
            bloqueantes.length > 0 ||
            // The client-side pre-check only hints (the server re-checks the
            // gate on the CURRENT hash); an override is mandatory once the
            // server itself has answered `eval_required`.
            (serverGate?.code === "eval_required" && override.trim().length < OVERRIDE_REASON_MIN)
          }
          data-testid="publish-confirm"
        >
          <Rocket className="mr-1 h-4 w-4" />
          {publish.isPending ? "Publicando..." : gateFails && override.trim() ? "Publicar com exceção" : "Publicar"}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

// ── Tab ───────────────────────────────────────────────────────────────────────

export default function VersionsTab({ agentKey }: { agentKey: string }) {
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
  if (!agent || versoes.length === 0) return <StudioEmpty titulo="Este agente ainda não tem versões." />;

  async function handleRestore(v: VersionSummary) {
    try {
      const d = await createDraft.mutateAsync({ from_version_id: v.id });
      toast.success(`Rascunho v${d.versao} criado a partir da v${v.versao}.`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function handleDiscard(v: VersionSummary) {
    if (!window.confirm(`Descartar o rascunho v${v.versao}? Esta ação não pode ser desfeita.`)) return;
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
                <td className="px-3 py-2 font-medium tabular-nums">v{v.versao}</td>
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
        <PublishDialog agentKey={agentKey} draft={draft} limiar={agent.publicacao_limiar} onClose={() => setPublishOpen(false)} />
      )}
    </div>
  );
}
