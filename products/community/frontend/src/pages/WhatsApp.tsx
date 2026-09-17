/**
 * WhatsApp — `/whatsapp` (community-m3-contract.md §4).
 *
 * Session banner distinguishing WORKING from needing pairing — pairing is
 * explicitly an OPERATOR action (no QR endpoint exists; contract §3#Grupos
 * endpoint 7). Groups table + create dialog (register-existing OR
 * create-new, contract endpoint 2's two shapes), row -> detail dialog with
 * roster, "Sincronizar roster", "Gerar lote de adição/remoção", and the
 * admin-only, click-to-reveal invite link section.
 *
 * The invite-link section and the "Convites" affordance are gated on
 * `isAdmin` via a plain conditional render (`{isAdmin && (...)}`), not CSS —
 * for a `moderador` session that whole subtree never mounts, so it is
 * genuinely ABSENT from the DOM (contract §4, consistent with D3's
 * server-side 403 on the same endpoint). Phones in the roster render
 * through `maskPhone()` unconditionally (§4/§5 safety posture).
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 *
 * Admin-only banner below the session banner links to `/whatsapp/conexoes`
 * (`Conexoes.tsx`, not in nav) — the new, separate multi-line WAHA
 * connection admin surface (`createWhatsAppConnectionsHooks` +
 * `<WhatsAppConnectionsPage/>`, `@noctusai/lib/components`). Distinct from
 * THIS page's own group-sync session above: WhatsApp is not connected
 * through the new page yet (2026-09-17 user decision) — the banner and the
 * new page say so honestly, in the same words.
 */
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";
import {
  Badge,
  Button,
  Input,
  TableSkeleton,
  Dialog,
  DialogHeader,
  DialogBody,
  DialogFooter,
} from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { EntityDetailDialog } from "@noctusai/lib/components";
import type { DetailSection } from "@noctusai/lib/components";
import { EmptyState, ErrorState, Field, FormError, Select } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { maskPhone } from "@/lib/phone";
import {
  useGruposWhatsApp,
  useGrupoMembros,
  useCreateGrupoWhatsApp,
  useUpdateGrupoWhatsApp,
  useSincronizarRoster,
  useGrupoConvite,
  useRevogarConvite,
  useSessaoWhatsApp,
  type Grupo,
  type GrupoAcao,
} from "@/hooks/useGruposWhatsApp";
import { useCreateLoteSincronizacao } from "@/hooks/useLotesSincronizacao";

function formatDateBR(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("pt-BR");
}

const SESSAO_LABELS: Record<string, string> = {
  WORKING: "Conectado",
  SCAN_QR_CODE: "Aguardando pareamento",
  STARTING: "Iniciando",
  FAILED: "Falhou",
  STOPPED: "Parado",
};

function SessionBanner() {
  const { data, isPending, error } = useSessaoWhatsApp();

  if (isPending) {
    return <div className="h-14 animate-pulse rounded-lg bg-muted" data-testid="sessao-skeleton" />;
  }
  if (error) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive" data-testid="sessao-erro">
        {errorMessage(error)}
      </div>
    );
  }
  const working = data?.estado === "WORKING";
  return (
    <div
      className={`rounded-lg border p-4 ${working ? "border-border bg-card" : "border-amber-400/40 bg-amber-400/10"}`}
      data-testid="sessao-banner"
    >
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${working ? "bg-emerald-500" : "bg-amber-500"}`} />
        <p className="text-sm font-medium text-foreground">
          Sessão do WhatsApp: {SESSAO_LABELS[data?.estado ?? ""] ?? data?.estado ?? "Desconhecida"}
        </p>
      </div>
      {!working && (
        <p className="mt-1 text-xs text-muted-foreground">
          O pareamento do número da comunidade é uma ação de operador, feita fora desta tela (não
          há um endpoint de QR code aqui). Fale com o time técnico para reconectar.
        </p>
      )}
    </div>
  );
}

export default function WhatsApp() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin = ssoCtx.isProductAdmin || ssoCtx.org.role === "admin";

  const [ativoFiltro, setAtivoFiltro] = useState<"todos" | "ativo" | "inativo">("todos");
  const [selected, setSelected] = useState<Grupo | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const params = useMemo(
    () => ({
      ativo: ativoFiltro === "todos" ? undefined : ativoFiltro === "ativo",
      page: 1,
      page_size: 50,
    }),
    [ativoFiltro],
  );

  const { data, isPending, isFetching, error } = useGruposWhatsApp(params);
  const createLote = useCreateLoteSincronizacao();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  async function handleGerarLote(grupo: Grupo, acao: GrupoAcao) {
    try {
      await createLote.mutateAsync({ grupoId: grupo.id, acao });
      toast.success(acao === "adicionar" ? "Lote de adição gerado." : "Lote de remoção gerado.");
      setSelected(null);
      navigate("/whatsapp/sincronizacao");
    } catch (err) {
      toast.error("Erro ao gerar lote", { description: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">WhatsApp</h1>
          <p className="text-sm text-muted-foreground">
            Grupos oficiais da comunidade.
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        {isAdmin && (
          <Button variant="primary" onClick={() => setCreateOpen(true)} data-testid="whatsapp-novo-grupo">
            + Novo grupo
          </Button>
        )}
      </div>

      <SessionBanner />

      {isAdmin && (
        <div
          className="flex items-center justify-between gap-3 rounded-lg border border-amber-400/40 bg-amber-400/10 p-4"
          data-testid="whatsapp-conexoes-link-banner"
        >
          <p className="text-sm text-foreground">
            Integração futura — o WhatsApp ainda não está conectado a este produto pela nova área de
            Conexões. A conexão será feita numa próxima etapa.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => navigate("/whatsapp/conexoes")}
            data-testid="whatsapp-conexoes-link"
          >
            Ver Conexões WhatsApp
          </Button>
        </div>
      )}

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Filtro de grupos">
        <Button variant={ativoFiltro === "todos" ? "primary" : "outline"} size="sm" onClick={() => setAtivoFiltro("todos")}>
          Todos
        </Button>
        <Button variant={ativoFiltro === "ativo" ? "primary" : "outline"} size="sm" onClick={() => setAtivoFiltro("ativo")}>
          Ativos
        </Button>
        <Button variant={ativoFiltro === "inativo" ? "primary" : "outline"} size="sm" onClick={() => setAtivoFiltro("inativo")}>
          Inativos
        </Button>
      </div>

      {showSkeleton ? (
        <TableSkeleton rows={6} columns={5} />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhum grupo cadastrado." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-4 py-3 font-medium">Nome</th>
                <th className="px-4 py-3 font-medium">Participantes observados</th>
                <th className="px-4 py-3 font-medium">Membros elegíveis</th>
                <th className="px-4 py-3 font-medium">Sincronizado em</th>
                <th className="px-4 py-3 font-medium">Ativo</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((g) => (
                <tr
                  key={g.id}
                  className="cursor-pointer border-b border-border last:border-0 hover:bg-accent/50"
                  onClick={() => setSelected(g)}
                  data-testid={`grupo-row-${g.id}`}
                >
                  <td className="px-4 py-3 text-foreground">{g.nome}</td>
                  <td className="px-4 py-3 text-foreground">{g.participantes_observados}</td>
                  <td className="px-4 py-3 text-foreground">{g.membros_elegiveis ?? "—"}</td>
                  <td className="px-4 py-3 text-foreground">{formatDateBR(g.sincronizado_em)}</td>
                  <td className="px-4 py-3">
                    <Badge variant={g.ativo ? "default" : "outline"}>{g.ativo ? "Ativo" : "Inativo"}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <GrupoDetailDialog
          grupo={selected}
          isAdmin={isAdmin}
          onClose={() => setSelected(null)}
          onGerarLote={handleGerarLote}
        />
      )}
      {createOpen && <GrupoFormDialog onClose={() => setCreateOpen(false)} />}
    </div>
  );
}

function grupoDetailSections(g: Grupo): DetailSection[] {
  return [
    {
      fields: [
        { label: "Chat ID", value: g.chat_id },
        { label: "Descrição", value: g.descricao ?? undefined, wide: true },
        { label: "Somente admin adiciona", value: g.somente_admin ? "Sim" : "Não" },
      ],
    },
  ];
}

function GrupoDetailDialog({
  grupo,
  isAdmin,
  onClose,
  onGerarLote,
}: {
  grupo: Grupo;
  isAdmin: boolean;
  onClose: () => void;
  onGerarLote: (grupo: Grupo, acao: GrupoAcao) => void;
}) {
  const sincronizar = useSincronizarRoster();
  const updateGrupo = useUpdateGrupoWhatsApp();

  async function handleSincronizar() {
    try {
      const res = await sincronizar.mutateAsync(grupo.id);
      toast.success(`Roster sincronizado: ${res.participantes} participantes.`);
    } catch (err) {
      toast.error("Erro ao sincronizar roster", { description: errorMessage(err) });
    }
  }

  async function handleToggleAtivo() {
    try {
      await updateGrupo.mutateAsync({ id: grupo.id, ativo: !grupo.ativo });
      toast.success(grupo.ativo ? "Grupo desativado." : "Grupo ativado.");
    } catch (err) {
      toast.error("Erro ao atualizar grupo", { description: errorMessage(err) });
    }
  }

  return (
    <EntityDetailDialog
      open
      onClose={onClose}
      title={grupo.nome}
      badges={[{ label: grupo.ativo ? "Ativo" : "Inativo", variant: grupo.ativo ? "default" : "outline" }]}
      sections={grupoDetailSections(grupo)}
      actions={[
        {
          label: grupo.ativo ? "Desativar" : "Ativar",
          variant: "outline",
          align: "start",
          onClick: () => void handleToggleAtivo(),
          disabled: updateGrupo.isPending,
          testId: "grupo-toggle-ativo",
        },
        {
          label: sincronizar.isPending ? "Sincronizando..." : "Sincronizar roster",
          variant: "outline",
          onClick: () => void handleSincronizar(),
          disabled: sincronizar.isPending,
          testId: "grupo-sincronizar-roster",
        },
        {
          label: "Gerar lote de adição",
          variant: "primary",
          onClick: () => onGerarLote(grupo, "adicionar"),
          testId: "grupo-lote-adicionar",
        },
        {
          label: "Gerar lote de remoção",
          variant: "destructive",
          onClick: () => onGerarLote(grupo, "remover"),
          testId: "grupo-lote-remover",
        },
      ]}
      testId="grupo-detail-dialog"
    >
      <GrupoRoster grupoId={grupo.id} />
      {/* Absent from the DOM for a moderador — a conditional render, not
          CSS (community-m3-contract.md §4). */}
      {isAdmin && <ConviteSection grupoId={grupo.id} />}
    </EntityDetailDialog>
  );
}

function GrupoRoster({ grupoId }: { grupoId: string }) {
  const { data, isPending, isFetching, error } = useGrupoMembros(grupoId, { page_size: 20 });
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <div className="mt-4 border-t border-border pt-4" data-testid="grupo-roster">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Participantes observados
        {/* lying-loading-ok: text-only suffix, never unmounts the table below */}
        {isRefreshing ? " · atualizando…" : ""}
      </h3>
      {showSkeleton ? (
        <div className="h-16 animate-pulse rounded-md bg-muted" data-testid="grupo-roster-skeleton" />
      ) : error ? (
        <p className="text-sm text-destructive" data-testid="grupo-roster-erro">
          {errorMessage(error)}
        </p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="grupo-roster-vazio">
          Nenhum participante observado ainda. Use "Sincronizar roster".
        </p>
      ) : (
        <ul className="space-y-1.5" data-testid="grupo-roster-lista">
          {data.items.map((m) => (
            <li key={m.id} className="flex items-center justify-between text-sm" data-testid={`grupo-roster-item-${m.id}`}>
              <span className="text-foreground">{m.membro_nome ?? "Não vinculado"}</span>
              <span className="text-muted-foreground">{maskPhone(m.telefone)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConviteSection({ grupoId }: { grupoId: string }) {
  const [revealed, setRevealed] = useState(false);
  const { data, refetch, isFetching, error } = useGrupoConvite(grupoId);
  const revogar = useRevogarConvite();

  async function handleReveal() {
    setRevealed(true);
    const res = await refetch();
    if (res.error) {
      toast.error("Erro ao buscar link de convite", { description: errorMessage(res.error) });
    }
  }

  async function handleRevogar() {
    try {
      await revogar.mutateAsync(grupoId);
      setRevealed(false);
      toast.success("Link de convite revogado.");
    } catch (err) {
      toast.error("Erro ao revogar convite", { description: errorMessage(err) });
    }
  }

  return (
    <div className="mt-4 border-t border-border pt-4" data-testid="grupo-convite-section">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Link de convite
      </h3>
      {!revealed ? (
        <Button variant="outline" size="sm" onClick={() => void handleReveal()} data-testid="grupo-convite-revelar">
          Ver link de convite
        </Button>
      ) : isFetching ? (
        <p className="text-sm text-muted-foreground">Carregando…</p>
      ) : error ? (
        <p className="text-sm text-destructive" data-testid="grupo-convite-erro">
          {errorMessage(error)}
        </p>
      ) : (
        <div className="space-y-2">
          <p className="break-all rounded-md border border-border bg-muted/50 p-2 text-xs" data-testid="grupo-convite-link">
            {data?.link}
          </p>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => void handleRevogar()}
            disabled={revogar.isPending}
            data-testid="grupo-convite-revogar"
          >
            {revogar.isPending ? "Revogando..." : "Revogar link"}
          </Button>
        </div>
      )}
    </div>
  );
}

function GrupoFormDialog({ onClose }: { onClose: () => void }) {
  const [modo, setModo] = useState<"existente" | "novo">("existente");
  const [chatId, setChatId] = useState("");
  const [nome, setNome] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const createGrupo = useCreateGrupoWhatsApp();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createGrupo.mutate(modo === "existente" ? { chat_id: chatId } : { criar: true, nome }, {
      onSuccess: () => {
        toast.success("Grupo cadastrado.");
        onClose();
      },
      onError: (err) => setFormError(errorMessage(err)),
    });
  }

  return (
    <Dialog open onClose={onClose} title="Novo grupo" className="max-w-md">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Novo grupo</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <div className="flex gap-3" role="radiogroup" aria-label="Modo de cadastro">
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input type="radio" checked={modo === "existente"} onChange={() => setModo("existente")} />
              Registrar grupo existente
            </label>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input type="radio" checked={modo === "novo"} onChange={() => setModo("novo")} />
              Criar novo grupo
            </label>
          </div>
          {modo === "existente" ? (
            <Field label="Chat ID" required help="ID do grupo no WhatsApp, ex: 12036...@g.us">
              <Input value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="12036xxxxxxxx@g.us" required />
            </Field>
          ) : (
            <Field label="Nome do grupo" required>
              <Input value={nome} onChange={(e) => setNome(e.target.value)} required />
            </Field>
          )}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={createGrupo.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={createGrupo.isPending}>
            {createGrupo.isPending ? "Salvando..." : "Salvar"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
