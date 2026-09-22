/**
 * Agent Studio — `/studio` (CONTRACT §G): every agent of the org, studio and
 * legacy. Legacy agents (Julia) are listed read-only — their studio routes
 * answer 409 `not_studio_agent`, so they link to `/agentes` instead.
 * "Novo agente" + the ativo toggle are admin-only (server-enforced too).
 */
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Boxes, Plus, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import { SLUG_RE, type AgentSummary } from "@/api/studio/types";
import { StudioEmpty, StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { ImportBundleDialog } from "@/components/studio/ImportBundleDialog";
import { PromptMarkdownField } from "@/components/studio/PromptMarkdownField";
import { useCreateStudioAgent, useStudioAgents, useUpdateStudioAgent } from "@/hooks/studio/useStudioAgents";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { studioTabHref } from "./studioTabs";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

function AtivoToggle({ agent, isAdmin }: { agent: AgentSummary; isAdmin: boolean }) {
  const update = useUpdateStudioAgent(agent.key);
  if (!isAdmin || agent.definition_mode === "legacy") {
    return (
      <Badge variant={agent.ativo ? "default" : "muted"} data-testid={`studio-ativo-${agent.key}`}>
        {agent.ativo ? "Ativo" : "Inativo"}
      </Badge>
    );
  }
  async function toggle() {
    try {
      await update.mutateAsync({ ativo: !agent.ativo });
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }
  return (
    <button
      type="button"
      role="switch"
      aria-checked={agent.ativo}
      aria-label={`Ativar/desativar ${agent.nome}`}
      disabled={update.isPending}
      onClick={toggle}
      data-testid={`studio-toggle-${agent.key}`}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        agent.ativo ? "bg-primary" : "bg-muted"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 rounded-full bg-background shadow transition-transform ${
          agent.ativo ? "translate-x-4" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

function NovoAgenteDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateStudioAgent();
  const navigate = useNavigate();
  const [key, setKey] = useState("");
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!SLUG_RE.test(key)) {
      setErro("A chave deve usar letras minúsculas, números e hífens (ex.: minha-agente).");
      return;
    }
    try {
      const created = await create.mutateAsync({ key, nome: nome.trim(), descricao: descricao.trim() || undefined });
      toast.success(`Agente ${created.nome} criado com um rascunho v1.`);
      onClose();
      navigate(`/studio/${encodeURIComponent(created.key)}`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Novo agente" className="max-w-lg">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-base font-semibold text-foreground">Novo agente</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div>
            <label htmlFor="novo-agente-key" className="mb-1 block text-sm font-medium">
              Chave *
            </label>
            <input
              id="novo-agente-key"
              className={`${INPUT_CLASS} font-mono`}
              value={key}
              required
              placeholder="ex.: estrategista-conteudo"
              onChange={(e) => setKey(e.target.value.toLowerCase())}
            />
            <p className="mt-1 text-xs text-muted-foreground">Identificador permanente, usado nas URLs.</p>
          </div>
          <div>
            <label htmlFor="novo-agente-nome" className="mb-1 block text-sm font-medium">
              Nome *
            </label>
            <input
              id="novo-agente-nome"
              className={INPUT_CLASS}
              value={nome}
              required
              onChange={(e) => setNome(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="novo-agente-descricao" className="mb-1 block text-sm font-medium">
              Descrição
            </label>
            <PromptMarkdownField
              id="novo-agente-descricao"
              value={descricao}
              onChange={setDescricao}
              rows={3}
              mono={false}
              semTokens
            />
          </div>
          {erro && (
            <p className="text-sm text-destructive" data-testid="novo-agente-erro">
              {erro}
            </p>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Criando..." : "Criar agente"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

export default function StudioList() {
  const isAdmin = useIsAdmin();
  const { data: agents, showSkeleton, isRefreshing, isError, error, refetch } = useStudioAgents();
  const [novoOpen, setNovoOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Boxes className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agent Studio</h1>
          <p className="text-sm text-muted-foreground">
            Agentes definidos por versões: prompt, skills, conhecimento e avaliações.
          </p>
        </div>
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
        {isAdmin && (
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" onClick={() => setImportOpen(true)} data-testid="studio-importar-pacote">
              <Upload className="mr-1 h-4 w-4" /> Importar pacote
            </Button>
            <Button variant="primary" onClick={() => setNovoOpen(true)} data-testid="studio-novo-agente">
              <Plus className="mr-1 h-4 w-4" /> Novo agente
            </Button>
          </div>
        )}
      </div>

      {showSkeleton ? (
        <StudioLoading rows={4} testId="studio-list-skeleton" />
      ) : isError ? (
        <StudioError error={error} onRetry={refetch} />
      ) : !agents || agents.length === 0 ? (
        <StudioEmpty titulo="Nenhum agente ainda.">
          {isAdmin && <p className="text-xs">Use “Novo agente” para criar o primeiro.</p>}
        </StudioEmpty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-sm" data-testid="studio-agents-table">
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Agente</th>
                <th className="px-4 py-2 font-medium">Chave</th>
                <th className="px-4 py-2 font-medium">Modo</th>
                <th className="px-4 py-2 font-medium">Ativo</th>
                <th className="px-4 py-2 font-medium">Versão ativa</th>
                <th className="px-4 py-2 font-medium">Rascunho</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.id} className="border-b border-border last:border-0" data-testid={`studio-row-${a.key}`}>
                  <td className="px-4 py-3">
                    {a.definition_mode === "studio" ? (
                      <Link to={`/studio/${encodeURIComponent(a.key)}`} className="font-medium text-primary hover:underline">
                        {a.nome}
                      </Link>
                    ) : (
                      <Link to="/agentes" className="font-medium text-foreground hover:underline">
                        {a.nome}
                      </Link>
                    )}
                    {a.descricao && <p className="line-clamp-1 text-xs text-muted-foreground">{a.descricao}</p>}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{a.key}</td>
                  <td className="px-4 py-3">
                    {a.definition_mode === "studio" ? (
                      <Badge variant="outline">Studio</Badge>
                    ) : (
                      <Badge variant="muted" title="Definido no código — somente leitura aqui">
                        Legado · somente leitura
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <AtivoToggle agent={a} isAdmin={isAdmin} />
                  </td>
                  <td className="px-4 py-3 tabular-nums">{a.versao_ativa !== null ? `v${a.versao_ativa}` : "—"}</td>
                  <td className="px-4 py-3">
                    {a.tem_rascunho ? <Badge variant="outline">Rascunho</Badge> : <span className="text-muted-foreground">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isAdmin && <NovoAgenteDialog open={novoOpen} onClose={() => setNovoOpen(false)} />}
      {isAdmin && importOpen && (
        <ImportBundleDialog
          onClose={() => setImportOpen(false)}
          onImported={(key) => {
            setImportOpen(false);
            toast.success("Pacote importado.");
            navigate(studioTabHref(key, "versoes"));
          }}
        />
      )}
    </div>
  );
}
