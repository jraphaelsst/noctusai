/**
 * Agent Studio — "Visão geral" (CONTRACT §G): status, versão ativa/rascunho,
 * last eval score vs limiar, quick actions (criar rascunho, publicar, abrir
 * inspector), and the agent's nome/descrição (admin-editable, §D1 PATCH).
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FilePlus2, Rocket, ScanSearch, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState } from "@noctusai/lib/design-system";
import type { VersionSummary } from "@/api/studio/types";
import { ImportBundleDialog } from "@/components/studio/ImportBundleDialog";
import { PromptMarkdownField } from "@/components/studio/PromptMarkdownField";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { shortHash } from "@/components/studio/compiledSegments";
import { VersionStatusBadge } from "@/components/studio/VersionStatusBadge";
import { useUpdateStudioAgent } from "@/hooks/studio/useStudioAgents";
import { useAgentVersionRefs, useCreateDraft } from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { studioTabHref } from "../studioTabs";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : `${Math.round(score * 1000) / 10}%`;
}

function VersionCard({ titulo, versao, agentKey }: { titulo: string; versao: VersionSummary | null; agentKey: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4" data-testid={`overview-card-${titulo.toLowerCase()}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{titulo}</p>
      {versao ? (
        <div className="mt-2 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xl font-semibold tabular-nums">v{versao.versao}</span>
            <VersionStatusBadge status={versao.status} />
          </div>
          <p className="text-xs text-muted-foreground">{versao.model}</p>
          <p className="font-mono text-[11px] text-muted-foreground">{shortHash(versao.compiled_hash)}</p>
          <p className="text-xs">Avaliação: {formatScore(versao.eval_score)}</p>
          <Link to={studioTabHref(agentKey, "compilado", { versao: versao.id })} className="text-xs text-primary hover:underline">
            Ver prompt compilado
          </Link>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">Nenhuma.</p>
      )}
    </div>
  );
}

export default function OverviewTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const { data: agent, draft, ativa, showSkeleton, isError, error, refetch, isPlaceholderData } =
    useAgentVersionRefs(agentKey);
  const createDraft = useCreateDraft(agentKey);
  const updateAgent = useUpdateStudioAgent(agentKey);
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    if (!agent || isPlaceholderData) return;
    setNome(agent.nome);
    setDescricao(agent.descricao ?? "");
  }, [agent, isPlaceholderData]);

  if (showSkeleton) return <StudioLoading rows={3} />;
  if (isError) return <StudioError error={error} onRetry={refetch} />;
  if (!agent) return <EmptyState message="Agente sem dados." />;

  const ultimaAvaliacao = draft?.eval_score ?? ativa?.eval_score ?? null;
  const gateOk = ultimaAvaliacao !== null && ultimaAvaliacao >= agent.publicacao_limiar;

  async function handleCreateDraft() {
    try {
      const d = await createDraft.mutateAsync();
      toast.success(`Rascunho v${d.versao} criado.`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function handleSaveInfo() {
    try {
      await updateAgent.mutateAsync({ nome: nome.trim(), descricao: descricao.trim() });
      toast.success("Agente atualizado.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const infoDirty = nome.trim() !== agent.nome || descricao.trim() !== (agent.descricao ?? "");

  return (
    <div className="space-y-6" data-testid="overview-tab">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Status</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge variant={agent.ativo ? "default" : "muted"}>{agent.ativo ? "Ativo" : "Inativo"}</Badge>
            {!ativa && <Badge variant="outline">Sem versão publicada</Badge>}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {agent.ativo && ativa
              ? "Novas conversas usam a versão ativa."
              : "O agente só conversa quando está ativo e tem uma versão publicada."}
          </p>
        </div>
        <VersionCard titulo="Ativa" versao={ativa} agentKey={agentKey} />
        <VersionCard titulo="Rascunho" versao={draft} agentKey={agentKey} />
        <div className="rounded-lg border border-border bg-card p-4" data-testid="overview-gate">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Avaliação × limiar</p>
          <p className="mt-2 text-xl font-semibold tabular-nums">
            {formatScore(ultimaAvaliacao)} <span className="text-sm font-normal text-muted-foreground">/ {formatScore(agent.publicacao_limiar)}</span>
          </p>
          <p className={`text-xs ${gateOk ? "text-emerald-600" : "text-muted-foreground"}`}>
            {ultimaAvaliacao === null
              ? "Nenhuma avaliação concluída."
              : gateOk
                ? "Acima do limiar de publicação."
                : "Abaixo do limiar de publicação."}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {isAdmin && !draft && (
          <Button variant="primary" onClick={handleCreateDraft} disabled={createDraft.isPending} data-testid="overview-criar-rascunho">
            <FilePlus2 className="mr-1 h-4 w-4" />
            {createDraft.isPending ? "Criando..." : ativa ? `Criar rascunho a partir da v${ativa.versao}` : "Criar rascunho"}
          </Button>
        )}
        {isAdmin && draft && (
          <Link
            to={studioTabHref(agentKey, "versoes", { publicar: "1" })}
            className="inline-flex items-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            data-testid="overview-publicar"
          >
            <Rocket className="mr-1 h-4 w-4" /> Publicar rascunho v{draft.versao}
          </Link>
        )}
        <Link
          to={studioTabHref(agentKey, "compilado")}
          className="inline-flex items-center rounded-md border border-input px-3 py-2 text-sm font-medium hover:bg-accent"
        >
          <ScanSearch className="mr-1 h-4 w-4" /> Abrir inspector
        </Link>
        {isAdmin && (
          <Button variant="outline" onClick={() => setImportOpen(true)} data-testid="overview-importar-pacote">
            <Upload className="mr-1 h-4 w-4" /> Importar pacote
          </Button>
        )}
      </div>

      {isAdmin && importOpen && (
        <ImportBundleDialog
          expectedAgentKey={agentKey}
          onClose={() => setImportOpen(false)}
          onImported={(key) => {
            setImportOpen(false);
            toast.success("Pacote importado.");
            navigate(studioTabHref(key, "versoes"));
          }}
        />
      )}

      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">Identificação</h2>
        {isAdmin ? (
          <>
            <div>
              <label htmlFor="overview-nome" className="mb-1 block text-xs font-medium">
                Nome
              </label>
              <input id="overview-nome" className={INPUT_CLASS} value={nome} onChange={(e) => setNome(e.target.value)} />
            </div>
            <div>
              <label htmlFor="overview-descricao" className="mb-1 block text-xs font-medium">
                Descrição
              </label>
              <PromptMarkdownField id="overview-descricao" value={descricao} onChange={setDescricao} rows={3} mono={false} semTokens />
            </div>
            <div className="flex justify-end">
              <Button size="sm" variant="primary" onClick={handleSaveInfo} disabled={!infoDirty || !nome.trim() || updateAgent.isPending}>
                Salvar
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm">{agent.nome}</p>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{agent.descricao || "Sem descrição."}</p>
          </>
        )}
      </div>
    </div>
  );
}
