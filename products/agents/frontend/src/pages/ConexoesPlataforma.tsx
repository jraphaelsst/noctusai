/**
 * Conexões da plataforma — `/conexoes-plataforma` (platform admin only, server-enforced by
 * `require_platform_admin`; Julia-line S5).
 *
 * Wires an agent to a product for an org in a few clicks: agente → produto → organização → confirmar. The server
 * mints and DELIVERS the credential to the product; nobody copies or pastes a token and no secret reaches the
 * browser. Rotate and revoke ask for confirmation through the canonical `useConfirm` organ.
 */
import { useMemo, useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Link2, Plus, RefreshCw, ShieldAlert, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, EmptyState } from "@noctusai/lib/design-system";
import { useConfirm } from "@noctusai/lib/components";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import {
  showPrefix,
  useCreateGrant,
  useGrantOpcoes,
  useGrants,
  useRevokeGrant,
  useRotateGrant,
  type Grant,
  GRANT_STATUS_BADGE,
} from "@/hooks/useGrants";
import { ApiError, errorMessage } from "@/lib/errors";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/50";

const STATUS_BADGE = GRANT_STATUS_BADGE;

const EXPIRACOES: ReadonlyArray<{ valor: string; rotulo: string }> = [
  { valor: "", rotulo: "Sem expiração" },
  { valor: "90", rotulo: "90 dias" },
  { valor: "365", rotulo: "1 ano" },
];

function fmt(value: string | null): string {
  return value ? format(new Date(value), "dd/MM/yyyy HH:mm", { locale: ptBR }) : "—";
}

function NovaConexaoDialog({ onClose }: { onClose: () => void }) {
  const [agentKey, setAgentKey] = useState("");
  const [product, setProduct] = useState("");
  const [orgId, setOrgId] = useState("");
  const [busca, setBusca] = useState("");
  const [expira, setExpira] = useState("");
  const opcoes = useGrantOpcoes(busca.trim());
  const create = useCreateGrant();

  const produtos = useMemo(() => opcoes.data?.produtos ?? [], [opcoes.data?.produtos]);
  const orgs = opcoes.data?.orgs ?? [];
  const agentes = useMemo(() => [...new Set(produtos.flatMap((p) => p.agent_keys))].sort(), [produtos]);
  const produtosDoAgente = produtos.filter((p) => p.agent_keys.includes(agentKey));
  const produtoLabel = produtos.find((p) => p.slug === product)?.label ?? product;
  const orgNome = orgs.find((o) => o.id === orgId)?.nome;
  const pronto = Boolean(agentKey && product && orgId);

  async function handleCreate() {
    try {
      await create.mutateAsync({
        agent_key: agentKey,
        product,
        org_id: orgId,
        ...(expira ? { expira_em_dias: Number(expira) } : {}),
      });
      toast.success("Conexão criada e entregue ao produto.");
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError && err.status === 409 ? "Já existe uma conexão ativa para esta combinação." : errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title="Nova conexão">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Nova conexão</h2>
        <p className="text-sm text-muted-foreground">
          A credencial é gerada e entregue ao produto automaticamente. Você não copia nem cola nada.
        </p>
      </DialogHeader>
      <DialogBody>
        {opcoes.showSkeleton ? (
          <StudioLoading rows={2} testId="grants-opcoes-skeleton" />
        ) : opcoes.isError ? (
          <StudioError error={opcoes.error} onRetry={opcoes.refetch} />
        ) : agentes.length === 0 ? (
          <EmptyState message="Nenhum produto aceita conexões de agente no momento." />
        ) : (
          <div className="space-y-3">
            <div>
              <label htmlFor="grant-agente" className="mb-1 block text-xs font-medium">1. Agente</label>
              <select
                id="grant-agente"
                className={INPUT_CLASS}
                value={agentKey}
                onChange={(e) => {
                  setAgentKey(e.target.value);
                  setProduct("");
                }}
                data-testid="grant-agente"
              >
                <option value="">Selecione o agente</option>
                {agentes.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="grant-produto" className="mb-1 block text-xs font-medium">2. Produto</label>
              <select
                id="grant-produto"
                className={INPUT_CLASS}
                value={product}
                disabled={!agentKey}
                onChange={(e) => setProduct(e.target.value)}
                data-testid="grant-produto"
              >
                <option value="">Selecione o produto</option>
                {produtosDoAgente.map((p) => (
                  <option key={p.slug} value={p.slug}>{p.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="grant-org-busca" className="mb-1 block text-xs font-medium">3. Organização</label>
              <input
                id="grant-org-busca"
                className={`${INPUT_CLASS} mb-2`}
                placeholder="Buscar organização pelo nome"
                value={busca}
                maxLength={100}
                onChange={(e) => setBusca(e.target.value)}
                data-testid="grant-org-busca"
              />
              <select
                aria-label="Organização"
                className={INPUT_CLASS}
                value={orgId}
                disabled={!product}
                onChange={(e) => setOrgId(e.target.value)}
                data-testid="grant-org"
              >
                <option value="">{orgs.length === 0 ? "Nenhuma organização encontrada" : "Selecione a organização"}</option>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>{o.nome}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="grant-expira" className="mb-1 block text-xs font-medium">Validade</label>
              <select id="grant-expira" className={INPUT_CLASS} value={expira} onChange={(e) => setExpira(e.target.value)} data-testid="grant-expira">
                {EXPIRACOES.map((x) => (
                  <option key={x.valor} value={x.valor}>{x.rotulo}</option>
                ))}
              </select>
            </div>
            {pronto && (
              <p className="rounded-md border border-border bg-muted p-2 text-sm" data-testid="grant-resumo">
                Conectar <strong>{agentKey}</strong> a <strong>{produtoLabel}</strong> para <strong>{orgNome ?? "a organização selecionada"}</strong>.
              </p>
            )}
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>Cancelar</Button>
        <Button onClick={handleCreate} disabled={!pronto || create.isPending} data-testid="grant-confirmar">
          {create.isPending ? "Conectando..." : "Confirmar conexão"}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

function GrantRow({ grant }: { grant: Grant }) {
  const confirm = useConfirm();
  const rotate = useRotateGrant();
  const revoke = useRevokeGrant();
  const badge = STATUS_BADGE[grant.status] ?? STATUS_BADGE.pendente;
  const revogado = grant.status === "revogado";

  async function handleRotate() {
    if (!(await confirm({
      title: "Rotacionar a credencial?",
      description: "Uma nova credencial é entregue ao produto e a anterior é revogada em seguida.",
      confirmLabel: "Rotacionar",
    }))) return;
    try {
      await rotate.mutateAsync(grant.id);
      toast.success("Credencial rotacionada.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function handleRevoke() {
    if (!(await confirm({
      title: "Revogar a conexão?",
      description: `${grant.product} deixa de conseguir falar com o agente ${grant.agent_key}. Não dá para desfazer.`,
      confirmLabel: "Revogar",
      tone: "danger",
    }))) return;
    try {
      await revoke.mutateAsync(grant.id);
      toast.success("Conexão revogada.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <li className="space-y-1 py-3 text-sm" data-testid={`grant-${grant.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium">
          {grant.agent_key} <span className="text-muted-foreground">→</span> {grant.product}{" "}
          <span className="text-muted-foreground">· {grant.org_nome ?? grant.org_id}</span>
        </p>
        <div className="flex items-center gap-2">
          <Badge variant={badge.variant}>{badge.label}</Badge>
          {!revogado && (
            <>
              <Button size="sm" variant="outline" onClick={handleRotate} disabled={rotate.isPending} data-testid={`grant-rotate-${grant.id}`}>
                <RefreshCw className="mr-1 h-3.5 w-3.5" /> Rotacionar
              </Button>
              <Button size="sm" variant="outline" onClick={handleRevoke} disabled={revoke.isPending} data-testid={`grant-revoke-${grant.id}`}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> Revogar
              </Button>
            </>
          )}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Credencial <span className="font-mono">{showPrefix(grant.token_prefix)}</span> · expira {grant.expires_at ? fmt(grant.expires_at) : "nunca"} ·
        última entrega {fmt(grant.last_delivered_at)}
      </p>
      {grant.last_error && (
        <p className="text-xs text-destructive" data-testid={`grant-error-${grant.id}`}>Último erro: {grant.last_error}</p>
      )}
    </li>
  );
}

export default function ConexoesPlataforma() {
  const grants = useGrants();
  const [novo, setNovo] = useState(false);
  const forbidden = grants.isError && grants.error instanceof ApiError && grants.error.status === 403;

  return (
    <div className="space-y-4" data-testid="conexoes-plataforma-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link2 className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Conexões da plataforma</h1>
            <p className="text-sm text-muted-foreground">
              Liga um agente a um produto para uma organização. A credencial é entregue direto ao produto — ninguém copia nem cola token.
              {grants.isRefreshing && <span className="ml-2 text-xs">Atualizando…</span>}
            </p>
          </div>
        </div>
        {!forbidden && (
          <Button variant="primary" onClick={() => setNovo(true)} data-testid="grant-nova">
            <Plus className="mr-1 h-4 w-4" /> Nova conexão
          </Button>
        )}
      </div>

      {forbidden ? (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground" role="alert" data-testid="conexoes-forbidden">
          <ShieldAlert className="h-5 w-5 text-destructive" />
          Apenas administradores da plataforma gerenciam as conexões.
        </div>
      ) : grants.showSkeleton ? (
        <StudioLoading rows={3} testId="grants-skeleton" />
      ) : grants.isError ? (
        <StudioError error={grants.error} onRetry={grants.refetch} />
      ) : !grants.data || grants.data.items.length === 0 ? (
        <EmptyState message="Nenhuma conexão ainda. Crie a primeira em “Nova conexão”." />
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card px-4" data-testid="grants-list">
          {grants.data.items.map((g) => (
            <GrantRow key={g.id} grant={g} />
          ))}
        </ul>
      )}

      {novo && <NovaConexaoDialog onClose={() => setNovo(false)} />}
    </div>
  );
}
