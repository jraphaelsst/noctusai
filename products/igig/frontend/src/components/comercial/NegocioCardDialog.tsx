/**
 * The negócio funnel card — the seed `CardHubDialog` (roadmap R9: the SAME
 * card organ the cliente card uses), with igig's subpage registry:
 *
 *   Geral        the seed spine (`GeralSubpage` + `GeralActions`): etiquetas,
 *                membros, descrição, anexos, checklists — plus the negócio
 *                summary (valor, responsável) in the `afterTags` slot
 *   Lead         the lead's contact data, editable
 *   Orçamentos   this negócio's orçamentos + "Gerar orçamento"
 *   Assistente   Claude: resumo / próxima ação / rascunho de mensagem (E2)
 *
 * Header actions: "Gerar orçamento" and "Marcar como perdido" (motivo
 * required — the loss statistics need it).
 *
 * Data: the seed card-hub hooks (`@/hooks/useNegocioCardHub`); this file only
 * maps them onto the organ's props. Only the ACTIVE subpage renders (the
 * organ's registry is thunked), so an unopened tab fetches nothing.
 */
import { useEffect, useState } from "react";
import { Bot, Copy, FilePlus2, FileText, ThumbsDown, UserRound } from "lucide-react";
import { CardHubDialog, MotivoMoveDialog, TooltipIconButton, type CardSubpage } from "@noctusai/lib/components";
import { Badge, Button, Field, FormError, Input, Select, Skeleton, Textarea } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { useAssistenteNegocio, useAtualizarLead, useAtualizarNegocio, useLeads, usePerderNegocio } from "@/hooks/useComercial";
import { useProfissionais } from "@/hooks/useCustos";
import { useCardHubGeral } from "@/components/common/useCardHubGeral";
import { negocioCardHub as hub } from "@/hooks/useNegocioCardHub";
import { useOrcamentos } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import { brl, dataBR } from "@/lib/format";
import { ORCAMENTO_STATUS_LABEL, ORIGEM_LABEL, type AssistenteAcao, type Negocio } from "@/types/crm";

type SubpageKey = "geral" | "lead" | "orcamentos" | "assistente";

export interface NegocioCardDialogProps {
  negocio: Negocio | null;
  onClose: () => void;
  onGerarOrcamento: (negocio: Negocio) => void;
  onAbrirOrcamento: (orcamentoId: string) => void;
}

export function NegocioCardDialog({ negocio, onClose, onGerarOrcamento, onAbrirOrcamento }: NegocioCardDialogProps) {
  const id = negocio?.id ?? null;
  const nomeCard = negocio ? negocio.lead?.empresa || negocio.lead?.nome || negocio.titulo : "";

  // ── Seed card-hub data: the shared Geral spine + activity column ────────
  const hubGeral = useCardHubGeral(hub, id, {
    afterTags: negocio ? <NegocioResumo negocio={negocio} /> : null,
  });
  const [perdendo, setPerdendo] = useState(false);
  const perder = usePerderNegocio();

  const erroToast = (fallback: string) => (err: unknown) => toast.error(describeError(err, fallback));

  const subpages: CardSubpage<SubpageKey>[] = [
    hubGeral.geral,
    { key: "lead", label: "Lead", icon: UserRound, render: () => (negocio ? <LeadSubpage negocio={negocio} /> : null) },
    {
      key: "orcamentos",
      label: "Orçamentos",
      icon: FileText,
      render: () =>
        negocio ? (
          <OrcamentosSubpage negocio={negocio} onGerar={() => onGerarOrcamento(negocio)} onAbrir={onAbrirOrcamento} />
        ) : null,
    },
    {
      key: "assistente",
      label: "Assistente",
      icon: Bot,
      render: () => (negocio ? <AssistenteSubpage negocioId={negocio.id} /> : null),
    },
  ];

  return (
    <>
      <CardHubDialog<SubpageKey>
        open={!!negocio}
        onClose={onClose}
        isLoading={hubGeral.showSkeleton}
        error={hubGeral.error}
        nome={nomeCard}
        testId="negocio-card-dialog"
        headerActions={
          negocio && negocio.status === "aberto" ? (
            <>
              <TooltipIconButton
                label="Gerar orçamento"
                icon={FilePlus2}
                variant="outline"
                testId="negocio-gerar-orcamento"
                onClick={() => onGerarOrcamento(negocio)}
              />
              <TooltipIconButton
                label="Marcar como perdido"
                icon={ThumbsDown}
                variant="outline"
                testId="negocio-marcar-perdido"
                className="text-destructive"
                onClick={() => setPerdendo(true)}
              />
            </>
          ) : null
        }
        subpages={subpages}
        defaultSubpage="geral"
        activity={hubGeral.activity}
      />
      <PerderNegocioDialog
        negocio={perdendo ? negocio : null}
        onCancel={() => setPerdendo(false)}
        busy={perder.isPending}
        onConfirm={(motivo) =>
          negocio &&
          perder.mutate(
            { id: negocio.id, motivo },
            {
              onSuccess: () => {
                toast.success("Negócio marcado como perdido.");
                setPerdendo(false);
                onClose();
              },
              onError: erroToast("Não foi possível marcar como perdido."),
            },
          )
        }
      />
    </>
  );
}

/**
 * "Marcar como perdido" — the seed `MotivoMoveDialog` with `required`: the
 * motivo is what the loss statistics are made of, so confirm stays disabled
 * until one is typed.
 */
export function PerderNegocioDialog({
  negocio,
  onConfirm,
  onCancel,
  busy,
}: {
  negocio: Negocio | null;
  onConfirm: (motivo: string) => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  return (
    <MotivoMoveDialog
      open={!!negocio}
      title="Marcar como perdido"
      description="O negócio sai do funil e fica no arquivo com o motivo, a etapa e o tempo parado — é disso que saem as estatísticas de perda."
      placeholder="Ex.: sem orçamento, escolheu outra agência, sem resposta…"
      required
      confirmLabel="Marcar como perdido"
      busy={busy}
      onConfirm={(motivo) => {
        if (motivo && motivo.trim()) onConfirm(motivo.trim());
      }}
      onCancel={onCancel}
    />
  );
}

// ─── Geral slot: negócio summary ─────────────────────────────────────────────

function NegocioResumo({ negocio }: { negocio: Negocio }) {
  const atualizar = useAtualizarNegocio();
  const { profissionais } = useProfissionais();
  const [valor, setValor] = useState(negocio.valor_estimado != null ? String(negocio.valor_estimado) : "");
  useEffect(() => {
    setValor(negocio.valor_estimado != null ? String(negocio.valor_estimado) : "");
  }, [negocio.id, negocio.valor_estimado]);

  function salvarValor() {
    const novo = valor.trim() === "" ? null : Math.max(0, Number(valor) || 0);
    if (novo === (negocio.valor_estimado ?? null)) return;
    atualizar.mutate(
      { id: negocio.id, valor_estimado: novo },
      { onError: (e) => toast.error(describeError(e, "Não foi possível salvar o valor.")) },
    );
  }

  return (
    <div className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2" data-testid="negocio-resumo">
      <Field label="Valor estimado (R$/mês)">
        <Input
          type="number"
          inputMode="decimal"
          min={0}
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          onBlur={salvarValor}
          disabled={negocio.status !== "aberto"}
        />
      </Field>
      <Field label="Responsável">
        <Select
          value={negocio.responsavel_id ?? ""}
          disabled={negocio.status !== "aberto" || atualizar.isPending}
          onChange={(e) =>
            atualizar.mutate(
              { id: negocio.id, responsavel_id: e.target.value || null },
              { onError: (err) => toast.error(describeError(err, "Não foi possível trocar o responsável.")) },
            )
          }
        >
          <option value="">Sem responsável</option>
          {profissionais
            .filter((p) => p.ativo || p.id === negocio.responsavel_id)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
        </Select>
      </Field>
      {negocio.status === "ganho" ? (
        <p className="text-xs text-muted-foreground sm:col-span-2">
          Ganho em {dataBR(negocio.ganho_em)} — o cliente já foi criado.
        </p>
      ) : null}
    </div>
  );
}

// ─── Lead subpage ────────────────────────────────────────────────────────────

function LeadSubpage({ negocio }: { negocio: Negocio }) {
  const { leads, loading, isError, error } = useLeads();
  const lead = leads.find((l) => l.id === negocio.lead_id) ?? null;
  const atualizar = useAtualizarLead();
  const [f, setF] = useState({ nome: "", empresa: "", email: "", telefone: "", instagram: "", observacoes: "" });
  const [sujo, setSujo] = useState(false);

  useEffect(() => {
    const base = lead ?? negocio.lead;
    if (!base || sujo) return;
    setF({
      nome: base.nome ?? "",
      empresa: base.empresa ?? "",
      email: base.email ?? "",
      telefone: base.telefone ?? "",
      instagram: base.instagram ?? "",
      observacoes: (lead?.observacoes as string | null | undefined) ?? "",
    });
    // Re-seed only when the lead itself changes, never over an in-progress edit.
  }, [lead, negocio.lead, sujo]);

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setF((p) => ({ ...p, [k]: e.target.value }));
    setSujo(true);
  };

  if (loading && !negocio.lead) return <Skeleton className="h-40 w-full" />;
  if (isError && !negocio.lead) {
    return <p role="alert" className="text-sm text-destructive">{describeError(error, "Não foi possível carregar o lead.")}</p>;
  }

  const origem = negocio.lead?.origem ?? lead?.origem ?? null;
  const opt = (v: string) => (v.trim() ? v.trim() : null);

  return (
    <div className="space-y-3" data-testid="lead-subpage">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {origem ? <Badge variant="outline">{ORIGEM_LABEL[origem] ?? origem}</Badge> : null}
        {lead?.como_conheceu ? <span>Como conheceu: {lead.como_conheceu}</span> : null}
        {lead?.created_at ? <span>Desde {dataBR(lead.created_at)}</span> : null}
      </div>
      <Field label="Nome" required>
        <Input value={f.nome} onChange={set("nome")} />
      </Field>
      <Field label="Empresa">
        <Input value={f.empresa} onChange={set("empresa")} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="E-mail">
          <Input type="email" inputMode="email" value={f.email} onChange={set("email")} />
        </Field>
        <Field label="Telefone">
          <Input type="tel" inputMode="tel" value={f.telefone} onChange={set("telefone")} />
        </Field>
      </div>
      <Field label="Instagram">
        <Input value={f.instagram} onChange={set("instagram")} />
      </Field>
      <Field label="Observações">
        <Textarea rows={3} value={f.observacoes} onChange={set("observacoes")} />
      </Field>
      {lead?.dores || lead?.nicho || lead?.orcamento_disponivel != null ? (
        <dl className="grid gap-2 rounded-lg bg-muted/40 p-3 text-xs sm:grid-cols-2">
          {lead?.nicho ? (
            <div>
              <dt className="text-muted-foreground">Nicho</dt>
              <dd className="text-foreground">{lead.nicho}</dd>
            </div>
          ) : null}
          {lead?.orcamento_disponivel != null ? (
            <div>
              <dt className="text-muted-foreground">Orçamento disponível</dt>
              <dd className="text-foreground">{brl(lead.orcamento_disponivel)}</dd>
            </div>
          ) : null}
          {lead?.dores ? (
            <div className="sm:col-span-2">
              <dt className="text-muted-foreground">Dores</dt>
              <dd className="whitespace-pre-wrap text-foreground">{lead.dores}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
      <FormError message={atualizar.isError ? describeError(atualizar.error, "Não foi possível salvar o lead.") : null} />
      <div className="flex justify-end">
        <Button
          disabled={!sujo || !f.nome.trim() || atualizar.isPending}
          onClick={() =>
            atualizar.mutate(
              {
                id: negocio.lead_id,
                nome: f.nome.trim(),
                empresa: opt(f.empresa),
                email: opt(f.email),
                telefone: opt(f.telefone),
                instagram: opt(f.instagram),
                observacoes: opt(f.observacoes),
              },
              {
                onSuccess: () => {
                  setSujo(false);
                  toast.success("Lead atualizado.");
                },
              },
            )
          }
        >
          {atualizar.isPending ? "Salvando…" : "Salvar lead"}
        </Button>
      </div>
    </div>
  );
}

// ─── Orçamentos subpage ──────────────────────────────────────────────────────

function OrcamentosSubpage({
  negocio,
  onGerar,
  onAbrir,
}: {
  negocio: Negocio;
  onGerar: () => void;
  onAbrir: (id: string) => void;
}) {
  const { orcamentos, showSkeleton, isError, error } = useOrcamentos({ negocio_id: negocio.id });
  return (
    <div className="space-y-3" data-testid="orcamentos-subpage">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {orcamentos.length === 1 ? "1 orçamento" : `${orcamentos.length} orçamentos`}
        </p>
        {negocio.status === "aberto" ? (
          <Button size="sm" onClick={onGerar}>
            <FilePlus2 className="mr-1 h-4 w-4" /> Gerar orçamento
          </Button>
        ) : null}
      </div>
      {showSkeleton ? (
        <Skeleton className="h-20 w-full" />
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">{describeError(error, "Não foi possível carregar os orçamentos.")}</p>
      ) : orcamentos.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          Nenhum orçamento ainda.
        </p>
      ) : (
        <ul className="space-y-2">
          {orcamentos.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                onClick={() => onAbrir(o.id)}
                className="flex w-full items-center gap-3 rounded-lg border border-border p-3 text-left text-sm hover:bg-muted"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-foreground">
                    {o.titulo} · v{o.versao}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {brl(o.total_mensal)}/mês · {dataBR(o.created_at)}
                  </span>
                </span>
                <Badge variant={o.status === "aceito" ? "default" : o.status === "recusado" ? "destructive" : "outline"}>
                  {ORCAMENTO_STATUS_LABEL[o.status]}
                </Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Assistente subpage (Slice E2) ───────────────────────────────────────────

const ACOES: { acao: AssistenteAcao; rotulo: string }[] = [
  { acao: "resumo", rotulo: "Resumo" },
  { acao: "proxima_acao", rotulo: "Próxima ação" },
  { acao: "rascunho_mensagem", rotulo: "Rascunho de mensagem" },
];

function AssistenteSubpage({ negocioId }: { negocioId: string }) {
  const assistente = useAssistenteNegocio();
  const [canal, setCanal] = useState<"email" | "whatsapp">("whatsapp");
  const texto = assistente.data?.texto ?? null;

  return (
    <div className="space-y-3" data-testid="assistente-subpage">
      <p className="text-sm text-muted-foreground">
        O assistente lê o lead, o histórico e os orçamentos deste negócio.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {ACOES.map((a) => (
          <Button
            key={a.acao}
            size="sm"
            variant={assistente.variables?.acao === a.acao ? "primary" : "outline"}
            disabled={assistente.isPending}
            onClick={() =>
              assistente.mutate({
                negocioId,
                acao: a.acao,
                canal: a.acao === "rascunho_mensagem" ? canal : undefined,
              })
            }
          >
            {a.rotulo}
          </Button>
        ))}
        <Select
          aria-label="Canal do rascunho"
          value={canal}
          onChange={(e) => setCanal(e.target.value as "email" | "whatsapp")}
          className="h-9 w-auto"
        >
          <option value="whatsapp">WhatsApp</option>
          <option value="email">E-mail</option>
        </Select>
      </div>
      {assistente.isPending ? (
        <div className="space-y-2" aria-label="Gerando">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : assistente.isError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(assistente.error, "O assistente não respondeu.")}
        </p>
      ) : texto ? (
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <p className="whitespace-pre-wrap text-sm text-foreground">{texto}</p>
          <div className="mt-2 flex justify-end">
            <button
              type="button"
              onClick={() =>
                navigator.clipboard
                  ?.writeText(texto)
                  .then(() => toast.success("Copiado."))
                  .catch(() => toast.error("Não foi possível copiar."))
              }
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <Copy className="h-3 w-3" /> Copiar
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
