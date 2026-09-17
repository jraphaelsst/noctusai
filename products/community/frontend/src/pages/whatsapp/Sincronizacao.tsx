/**
 * Sincronização — `/whatsapp/sincronizacao` (community-m3-contract.md §4),
 * the manager-confirmed state machine:
 * `proposto -> confirmado -> aplicado | aplicado_parcial`, or
 * `-> cancelado` / `-> expirado`.
 *
 * THE SAFETY-CRITICAL SURFACE OF THIS MODULE (contract §4/§5):
 * - The full per-participant preview (nome, telefone masked to last 4,
 *   ação) renders BEFORE confirming — and stays visible through every
 *   later state, so a manager can always see exactly who this lote touches.
 * - Confirming requires an explicit checkbox ("Confirmo a <ação> de N
 *   participantes") AND a typed confirmation ("CONFIRMAR"), both gates on
 *   the SAME "Confirmar" button — neither alone enables it.
 * - "Aplicar" is a SEPARATE button, enabled ONLY while `estado ===
 *   "confirmado"`. Nothing auto-advances proposto -> confirmado ->
 *   aplicado; each transition is its own explicit click.
 * - `aplicado_parcial` renders as a warning (never as a subdued/ok state)
 *   with per-item outcome badges and a "Repetir o restante" action that
 *   creates a brand-new lote via `useCreateLoteSincronizacao` — it never
 *   mutates the already-applied one.
 * - "Convites pendentes" (admin-only — the whole panel, contract endpoint
 *   13) is what makes `convite_necessario` actionable instead of a
 *   swallowed failure: the group's invite link plus copy-the-link and
 *   copy-the-message helpers per pending member.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useMemo, useState } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";
import { Badge, Button, Dialog, DialogHeader, DialogBody, DialogFooter } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { Checkbox, EmptyState, ErrorState, Field, FormError, Select } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { maskPhone } from "@/lib/phone";
import { useGruposWhatsApp } from "@/hooks/useGruposWhatsApp";
import {
  useLotesSincronizacao,
  useLoteSincronizacao,
  useCreateLoteSincronizacao,
  useConfirmarLote,
  useAplicarLote,
  useCancelarLote,
  useConvitesPendentes,
  type Lote,
  type LoteEstado,
  type LoteItemResultado,
} from "@/hooks/useLotesSincronizacao";

const CONFIRM_PHRASE = "CONFIRMAR";

function formatDateBR(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("pt-BR");
}

const ESTADO_LABELS: Record<LoteEstado, string> = {
  proposto: "Proposto",
  confirmado: "Confirmado",
  aplicado: "Aplicado",
  aplicado_parcial: "Aplicado parcialmente",
  cancelado: "Cancelado",
  expirado: "Expirado",
};

function estadoBadgeVariant(estado: LoteEstado): BadgeVariant {
  switch (estado) {
    case "aplicado":
      return "default";
    case "aplicado_parcial":
      return "outline";
    case "cancelado":
    case "expirado":
      return "destructive";
    default:
      return "outline";
  }
}

const ACAO_LABELS: Record<string, string> = { adicionar: "Adição", remover: "Remoção" };
const ACAO_SUBSTANTIVO: Record<string, string> = { adicionar: "adição", remover: "remoção" };

const RESULTADO_LABELS: Record<LoteItemResultado, string> = {
  pendente: "Pendente",
  adicionado: "Adicionado",
  removido: "Removido",
  convite_necessario: "Convite necessário",
  falhou: "Falhou",
};

function resultadoBadgeVariant(resultado: LoteItemResultado): BadgeVariant {
  switch (resultado) {
    case "adicionado":
    case "removido":
      return "default";
    case "falhou":
      return "destructive";
    case "convite_necessario":
      return "outline";
    default:
      return "outline";
  }
}

export default function Sincronizacao() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin = ssoCtx.isProductAdmin || ssoCtx.org.role === "admin";

  const [grupoFiltro, setGrupoFiltro] = useState("");
  const [estadoFiltro, setEstadoFiltro] = useState<LoteEstado | "">("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const params = useMemo(
    () => ({
      grupo_id: grupoFiltro || undefined,
      estado: estadoFiltro || undefined,
      page: 1,
      page_size: 50,
    }),
    [grupoFiltro, estadoFiltro],
  );

  const { data, isPending, isFetching, error } = useLotesSincronizacao(params);
  const { data: gruposData } = useGruposWhatsApp({ page_size: 100 });

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  function grupoNome(lote: Lote): string {
    if (lote.grupo_nome) return lote.grupo_nome;
    return gruposData?.items.find((g) => g.id === lote.grupo_id)?.nome ?? lote.grupo_id;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Sincronização</h1>
        <p className="text-sm text-muted-foreground">
          Lotes de adição e remoção de participantes nos grupos do WhatsApp.
          {isRefreshing ? " Atualizando…" : ""}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select className="w-56" value={grupoFiltro} onChange={(e) => setGrupoFiltro(e.target.value)} aria-label="Filtrar por grupo">
          <option value="">Todos os grupos</option>
          {(gruposData?.items ?? []).map((g) => (
            <option key={g.id} value={g.id}>
              {g.nome}
            </option>
          ))}
        </Select>
        <Select
          className="w-56"
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value as LoteEstado | "")}
          aria-label="Filtrar por estado"
        >
          <option value="">Todos os estados</option>
          {(Object.keys(ESTADO_LABELS) as LoteEstado[]).map((e) => (
            <option key={e} value={e}>
              {ESTADO_LABELS[e]}
            </option>
          ))}
        </Select>
      </div>

      {showSkeleton ? (
        <div className="h-40 animate-pulse rounded-lg bg-muted" data-testid="lotes-skeleton" />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhum lote de sincronização encontrado." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-4 py-3 font-medium">Grupo</th>
                <th className="px-4 py-3 font-medium">Ação</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium">Participantes</th>
                <th className="px-4 py-3 font-medium">Proposto em</th>
                <th className="px-4 py-3 font-medium">Expira em</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr
                  key={l.id}
                  className="cursor-pointer border-b border-border last:border-0 hover:bg-accent/50"
                  onClick={() => setSelectedId(l.id)}
                  data-testid={`lote-row-${l.id}`}
                >
                  <td className="px-4 py-3 text-foreground">{grupoNome(l)}</td>
                  <td className="px-4 py-3 text-foreground">{ACAO_LABELS[l.acao] ?? l.acao}</td>
                  <td className="px-4 py-3">
                    <Badge variant={estadoBadgeVariant(l.estado)}>{ESTADO_LABELS[l.estado]}</Badge>
                  </td>
                  <td className="px-4 py-3 text-foreground">{l.total_itens}</td>
                  <td className="px-4 py-3 text-foreground">{formatDateBR(l.proposto_em)}</td>
                  <td className="px-4 py-3 text-foreground">{formatDateBR(l.expira_em)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedId && (
        <LoteDetailDialog loteId={selectedId} isAdmin={isAdmin} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

function LoteDetailDialog({ loteId, isAdmin, onClose }: { loteId: string; isAdmin: boolean; onClose: () => void }) {
  const { data: lote, isPending, error } = useLoteSincronizacao(loteId);
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const confirmarLote = useConfirmarLote();
  const aplicarLote = useAplicarLote();
  const cancelarLote = useCancelarLote();
  const criarNovoLote = useCreateLoteSincronizacao();

  if (isPending) {
    return (
      <Dialog open onClose={onClose} title="Lote" className="max-w-2xl">
        <DialogBody>
          <div className="h-40 animate-pulse rounded-md bg-muted" data-testid="lote-detail-skeleton" />
        </DialogBody>
      </Dialog>
    );
  }
  if (error || !lote) {
    return (
      <Dialog open onClose={onClose} title="Lote" className="max-w-2xl">
        <DialogBody>
          <ErrorState message={error ? errorMessage(error) : "Lote não encontrado."} />
        </DialogBody>
      </Dialog>
    );
  }

  const expirado = lote.estado === "proposto" && new Date(lote.expira_em).getTime() < Date.now();
  const podeConfirmar = lote.estado === "proposto" && !expirado;
  const podeAplicar = lote.estado === "confirmado";
  const podeCancelar = lote.estado === "proposto" || lote.estado === "confirmado";
  const confirmValido = confirmChecked && confirmText.trim().toUpperCase() === CONFIRM_PHRASE;
  const temConviteNecessario = lote.itens.some((i) => i.resultado === "convite_necessario");

  async function handleConfirmar() {
    if (!lote) return;
    try {
      await confirmarLote.mutateAsync(lote.id);
      toast.success("Lote confirmado.");
      setConfirmChecked(false);
      setConfirmText("");
    } catch (err) {
      toast.error("Erro ao confirmar lote", { description: errorMessage(err) });
    }
  }

  async function handleAplicar() {
    if (!lote) return;
    try {
      const res = await aplicarLote.mutateAsync(lote.id);
      if (res.estado === "aplicado_parcial") {
        toast.warning("Lote aplicado parcialmente — veja os itens com falha.");
      } else {
        toast.success("Lote aplicado.");
      }
    } catch (err) {
      toast.error("Erro ao aplicar lote", { description: errorMessage(err) });
    }
  }

  async function handleCancelar() {
    if (!lote) return;
    if (!window.confirm("Cancelar este lote?")) return;
    try {
      await cancelarLote.mutateAsync(lote.id);
      toast.success("Lote cancelado.");
      onClose();
    } catch (err) {
      toast.error("Erro ao cancelar lote", { description: errorMessage(err) });
    }
  }

  /** Never mutates the applied lote — computes a brand-new one for the
   * SAME grupo+ação, which the backend re-derives freshly (contract §4). */
  async function handleRepetirRestante() {
    if (!lote) return;
    try {
      await criarNovoLote.mutateAsync({ grupoId: lote.grupo_id, acao: lote.acao });
      toast.success("Novo lote gerado para o restante.");
      onClose();
    } catch (err) {
      toast.error("Erro ao gerar novo lote", { description: errorMessage(err) });
    }
  }

  return (
    <Dialog open onClose={onClose} title={`Lote — ${ACAO_LABELS[lote.acao] ?? lote.acao}`} className="max-w-2xl">
      <DialogHeader>
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-foreground">Lote de {ACAO_SUBSTANTIVO[lote.acao] ?? lote.acao}</h2>
          <Badge variant={estadoBadgeVariant(lote.estado)}>{ESTADO_LABELS[lote.estado]}</Badge>
        </div>
      </DialogHeader>
      <DialogBody className="space-y-4">
        {lote.estado === "aplicado_parcial" && (
          <div
            className="rounded-md border border-amber-400/50 bg-amber-400/10 p-3 text-sm text-amber-900"
            role="alert"
            data-testid="lote-aviso-parcial"
          >
            <p className="font-medium">Este lote foi aplicado parcialmente.</p>
            <p className="mt-1 text-xs">
              Alguns participantes não puderam ser processados. Veja os itens marcados abaixo e use
              "Repetir o restante" para gerar um novo lote — o lote já aplicado nunca é alterado.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() => void handleRepetirRestante()}
              disabled={criarNovoLote.isPending}
              data-testid="lote-repetir-restante"
            >
              {criarNovoLote.isPending ? "Gerando..." : "Repetir o restante"}
            </Button>
          </div>
        )}

        {expirado && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
            Este lote expirou. Gere um novo lote a partir da tela de grupos.
          </div>
        )}

        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Participantes ({lote.itens.length})
          </h3>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm" data-testid="lote-itens-tabela">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Nome</th>
                  <th className="px-3 py-2 font-medium">Telefone</th>
                  <th className="px-3 py-2 font-medium">Ação</th>
                  {lote.estado !== "proposto" && lote.estado !== "confirmado" && (
                    <th className="px-3 py-2 font-medium">Resultado</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {lote.itens.map((item) => (
                  <tr key={item.id} className="border-b border-border last:border-0" data-testid={`lote-item-${item.id}`}>
                    <td className="px-3 py-2 text-foreground">{item.membro_nome ?? "Não vinculado"}</td>
                    <td className="px-3 py-2 text-foreground" data-testid={`lote-item-telefone-${item.id}`}>
                      {maskPhone(item.telefone)}
                    </td>
                    <td className="px-3 py-2 text-foreground">{ACAO_LABELS[lote.acao] ?? lote.acao}</td>
                    {lote.estado !== "proposto" && lote.estado !== "confirmado" && (
                      <td className="px-3 py-2">
                        <Badge variant={resultadoBadgeVariant(item.resultado)} data-testid={`lote-item-resultado-${item.id}`}>
                          {RESULTADO_LABELS[item.resultado]}
                        </Badge>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {lote.ignorados.length > 0 && (
          <div data-testid="lote-ignorados">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Ignorados ({lote.ignorados.length})
            </h3>
            <ul className="space-y-1 text-sm text-muted-foreground">
              {lote.ignorados.map((ig) => (
                <li key={ig.membro_id}>
                  {ig.nome} — {ig.motivo}
                </li>
              ))}
            </ul>
          </div>
        )}

        {podeConfirmar && (
          <div className="space-y-2 border-t border-border pt-4" data-testid="lote-confirmar-secao">
            <Checkbox
              id="lote-confirmo"
              label={`Confirmo a ${ACAO_SUBSTANTIVO[lote.acao] ?? lote.acao} de ${lote.itens.length} participantes`}
              checked={confirmChecked}
              onChange={(e) => setConfirmChecked(e.target.checked)}
              data-testid="lote-confirmo-checkbox"
            />
            <Field label={`Digite "${CONFIRM_PHRASE}" para confirmar`} required>
              <input
                className="w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={CONFIRM_PHRASE}
                data-testid="lote-confirmo-texto"
              />
            </Field>
          </div>
        )}

        {isAdmin && temConviteNecessario && <ConvitesPendentesPanel loteId={lote.id} />}
      </DialogBody>
      <DialogFooter className="justify-between gap-2">
        <div className="flex gap-2">
          {podeCancelar && (
            <Button
              variant="outline"
              onClick={() => void handleCancelar()}
              disabled={cancelarLote.isPending}
              data-testid="lote-cancelar"
            >
              Cancelar lote
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          {podeConfirmar && (
            <Button
              variant="primary"
              onClick={() => void handleConfirmar()}
              disabled={!confirmValido || confirmarLote.isPending}
              data-testid="lote-confirmar"
            >
              {confirmarLote.isPending ? "Confirmando..." : "Confirmar"}
            </Button>
          )}
          {/* "Aplicar" is a SEPARATE button — enabled ONLY once `estado ===
              "confirmado"`. Never collapsed with "Confirmar" into one click
              (contract §4). */}
          <Button
            variant="primary"
            onClick={() => void handleAplicar()}
            disabled={!podeAplicar || aplicarLote.isPending}
            data-testid="lote-aplicar"
          >
            {aplicarLote.isPending ? "Aplicando..." : "Aplicar"}
          </Button>
        </div>
      </DialogFooter>
    </Dialog>
  );
}

function buildConviteMensagem(nome: string | null, link: string | null): string {
  const saudacao = nome ? `Olá, ${nome}!` : "Olá!";
  return `${saudacao} Aqui está o link para entrar no nosso grupo do WhatsApp: ${link ?? ""}`;
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Copiado.");
  } catch {
    // Clipboard access can be denied by the browser — the text is still
    // visible/selectable, so nothing is actually lost.
  }
}

/** Admin-only panel (contract endpoint 13 is admin-only end-to-end). The
 * PARENT gates rendering on `isAdmin` too, so this never mounts for a
 * moderador — belt-and-suspenders with the server's own 403. */
function ConvitesPendentesPanel({ loteId }: { loteId: string }) {
  const { data, isPending, error } = useConvitesPendentes(loteId);

  return (
    <div className="border-t border-border pt-4" data-testid="convites-pendentes-panel">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Convites pendentes
      </h3>
      {isPending ? (
        <div className="h-12 animate-pulse rounded-md bg-muted" />
      ) : error ? (
        <p className="text-sm text-destructive">{errorMessage(error)}</p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum convite pendente.</p>
      ) : (
        <div className="space-y-3">
          {data.link && (
            <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/50 p-2">
              <p className="break-all text-xs" data-testid="convites-pendentes-link">
                {data.link}
              </p>
              <Button variant="outline" size="sm" onClick={() => void copyToClipboard(data.link ?? "")}>
                <Copy className="h-3.5 w-3.5" /> Copiar link
              </Button>
            </div>
          )}
          <ul className="space-y-2">
            {data.items.map((item) => (
              <li
                key={item.participante_jid}
                className="flex items-center justify-between gap-2 text-sm"
                data-testid={`convite-pendente-${item.participante_jid}`}
              >
                <span className="text-foreground">{item.nome ?? "Não vinculado"}</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void copyToClipboard(buildConviteMensagem(item.nome, data.link))}
                >
                  <Copy className="h-3.5 w-3.5" /> Copiar mensagem
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
