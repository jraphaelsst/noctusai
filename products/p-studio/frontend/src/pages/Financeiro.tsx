import { useState } from "react";
import { AlertCircle, CheckCircle2, DollarSign, Pencil, Plus, TrendingUp, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import {
  useApiMutation,
  useClientes,
  useLancamentos,
  useNegocios,
  useReceitaPorCliente,
  useResumoFinanceiro,
  useStatusFinanceiro,
} from "@/hooks/useApi";
import {
  BotaoExcluir,
  Button,
  Card,
  EmptyState,
  ErroBox,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  StatCard,
  StatusBadge,
  TBody,
  THead,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { FORMAS_PAGAMENTO, LABEL_FORMA_PAGAMENTO, TOM_FINANCEIRO } from "@/lib/status";
import { fmtData, fmtMoeda, hojeISO } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { Lancamento } from "@/types";

const FORM_VAZIO = {
  cliente_id: "",
  negocio_id: "",
  descricao: "",
  valor: "0",
  status: "a_faturar",
  data_entrega: "",
  vencimento: "",
  forma_pagamento: "",
  observacoes: "",
};

/** Só os status ARMAZENADOS podem ser escolhidos — `atrasado` é derivado. */
const STATUS_EDITAVEIS = ["a_faturar", "faturado", "recebido", "cancelado"];

export default function Financeiro() {
  const [filtro, setFiltro] = useState("");
  const { data: lancamentos, isLoading, error } = useLancamentos(filtro || undefined);
  const { data: resumo } = useResumoFinanceiro();
  const { data: porCliente } = useReceitaPorCliente();
  const { data: statusLista } = useStatusFinanceiro();
  const { data: clientes } = useClientes();
  const { data: negocios } = useNegocios();

  const [modal, setModal] = useState<"novo" | "editar" | null>(null);
  const [selecionado, setSelecionado] = useState<Lancamento | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [baixa, setBaixa] = useState<Lancamento | null>(null);
  const [formBaixa, setFormBaixa] = useState({ pago_em: hojeISO(), forma_pagamento: "pix" });
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const invalida = ["financeiro", "dashboard", "clientes-metricas"];

  const criar = useApiMutation(invalida, (body: any) => api.post("/api/financeiro", body), "Lançamento criado");
  const editar = useApiMutation(
    invalida,
    ({ id, ...body }: any) => api.patch(`/api/financeiro/${id}`, body),
    "Lançamento atualizado"
  );
  const darBaixa = useApiMutation(
    invalida,
    ({ id, ...body }: any) => api.post(`/api/financeiro/${id}/baixa`, body),
    "Recebimento registrado"
  );
  const excluir = useApiMutation(invalida, (id: string) => api.del(`/api/financeiro/${id}`), "Lançamento excluído");

  const rotuloStatus = (id: string) => (statusLista ?? []).find((s) => s.id === id)?.label ?? id;

  const abrirNovo = () => {
    setForm(FORM_VAZIO);
    setSelecionado(null);
    setModal("novo");
  };

  const abrirEditar = (lancamento: Lancamento) => {
    setSelecionado(lancamento);
    setForm({
      cliente_id: lancamento.cliente_id,
      negocio_id: lancamento.negocio_id ?? "",
      descricao: lancamento.descricao ?? "",
      valor: String(lancamento.valor ?? 0),
      status: lancamento.status as string,
      data_entrega: lancamento.data_entrega ?? "",
      vencimento: lancamento.vencimento ?? "",
      forma_pagamento: (lancamento.forma_pagamento as string) ?? "",
      observacoes: lancamento.observacoes ?? "",
    });
    setModal("editar");
  };

  const salvar = async () => {
    const body = {
      cliente_id: form.cliente_id,
      negocio_id: form.negocio_id || null,
      descricao: form.descricao || null,
      valor: Number(form.valor) || 0,
      status: form.status,
      data_entrega: form.data_entrega || null,
      vencimento: form.vencimento || null,
      forma_pagamento: form.forma_pagamento || null,
      observacoes: form.observacoes || null,
    };
    if (modal === "novo") await criar.mutateAsync(body);
    else if (selecionado) await editar.mutateAsync({ id: selecionado.id, ...body });
    setModal(null);
  };

  const confirmarBaixa = async () => {
    if (!baixa) return;
    await darBaixa.mutateAsync({
      id: baixa.id,
      pago_em: formBaixa.pago_em || null,
      forma_pagamento: formBaixa.forma_pagamento || null,
    });
    setBaixa(null);
  };

  if (isLoading) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  return (
    <div>
      <PageHeader
        title="Gestão financeira"
        description="Faturamento, recebimentos e inadimplência."
        action={
          <Button onClick={abrirNovo} disabled={!clientes?.length}>
            <Plus className="h-4 w-4" /> Novo lançamento
          </Button>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Faturamento total"
          value={fmtMoeda(resumo?.faturamento_total)}
          hint={`Ano: ${fmtMoeda(resumo?.receita_ano)}`}
          icon={<DollarSign className="h-4 w-4" />}
        />
        <StatCard
          label="Recebido"
          value={fmtMoeda(resumo?.recebido)}
          hint={`Mês: ${fmtMoeda(resumo?.receita_mes)}`}
          icon={<Wallet className="h-4 w-4" />}
        />
        <StatCard
          label="Em aberto"
          value={fmtMoeda(resumo?.em_aberto)}
          hint={`Ticket médio: ${fmtMoeda(resumo?.ticket_medio)}`}
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <StatCard
          label="Atrasado"
          value={fmtMoeda(resumo?.atrasado)}
          hint={`${resumo?.clientes_inadimplentes ?? 0} cliente(s) inadimplente(s)`}
          icon={<AlertCircle className="h-4 w-4" />}
        />
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => setFiltro("")}
          className={cn(
            "rounded-full border px-3 py-1 text-xs",
            filtro === "" ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
          )}
        >
          Todos
        </button>
        {(statusLista ?? []).map((s) => (
          <button
            key={s.id}
            onClick={() => setFiltro(s.id)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs",
              filtro === s.id
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground"
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {(lancamentos ?? []).length === 0 ? (
        <EmptyState>Nenhum lançamento neste filtro.</EmptyState>
      ) : (
        <Table>
          <THead>
            <tr>
              <Th>Cliente</Th>
              <Th>Descrição</Th>
              <Th>Valor</Th>
              <Th>Entrega</Th>
              <Th>Vencimento</Th>
              <Th>Pagamento</Th>
              <Th>Forma</Th>
              <Th>Status</Th>
              <Th />
            </tr>
          </THead>
          <TBody>
            {(lancamentos ?? []).map((l) => (
              <tr key={l.id} className="hover:bg-muted/30">
                <Td className="font-medium">{l.cliente_nome ?? "—"}</Td>
                <Td className="text-muted-foreground">{l.descricao ?? "—"}</Td>
                <Td>{fmtMoeda(l.valor)}</Td>
                <Td className="text-muted-foreground">{fmtData(l.data_entrega)}</Td>
                <Td className="text-muted-foreground">{fmtData(l.vencimento)}</Td>
                <Td className="text-muted-foreground">{fmtData(l.pago_em)}</Td>
                <Td className="text-muted-foreground">
                  {l.forma_pagamento ? LABEL_FORMA_PAGAMENTO[l.forma_pagamento as string] ?? l.forma_pagamento : "—"}
                </Td>
                <Td>
                  <StatusBadge tom={TOM_FINANCEIRO[l.status_exibido as string] ?? "lead"}>
                    {rotuloStatus(l.status_exibido as string)}
                  </StatusBadge>
                </Td>
                <Td>
                  <div className="flex justify-end gap-1">
                    {l.status !== "recebido" && l.status !== "cancelado" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Dar baixa"
                        onClick={() => {
                          setBaixa(l);
                          setFormBaixa({
                            pago_em: hojeISO(),
                            forma_pagamento: (l.forma_pagamento as string) || "pix",
                          });
                        }}
                      >
                        <CheckCircle2 className="h-4 w-4 text-status-received" />
                      </Button>
                    )}
                    <Button variant="ghost" size="icon" title="Editar" onClick={() => abrirEditar(l)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <BotaoExcluir
                      confirmando={confirmando === l.id}
                      onPedirConfirmacao={() => setConfirmando(l.id)}
                      onConfirmar={() => {
                        excluir.mutate(l.id);
                        setConfirmando(null);
                      }}
                    />
                  </div>
                </Td>
              </tr>
            ))}
          </TBody>
        </Table>
      )}

      {(porCliente ?? []).length > 0 && (
        <Card className="mt-6">
          <h2 className="mb-3 font-display text-lg">Receita recebida por cliente</h2>
          <div className="space-y-2">
            {(porCliente ?? []).slice(0, 10).map((r) => {
              const maior = porCliente![0].valor || 1;
              return (
                <div key={r.cliente_id} className="flex items-center gap-3">
                  <span className="w-40 shrink-0 truncate text-sm">{r.nome ?? "—"}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.max(2, (r.valor / maior) * 100)}%` }}
                    />
                  </div>
                  <span className="w-28 shrink-0 text-right text-sm text-muted-foreground">
                    {fmtMoeda(r.valor)}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* ── Criar / editar ── */}
      <Modal
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === "novo" ? "Novo lançamento" : "Editar lançamento"}
        wide
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Cliente *">
            <Select value={form.cliente_id} onChange={(e) => set("cliente_id", e.target.value)}>
              <option value="">— selecione —</option>
              {(clientes ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Negócio">
            <Select value={form.negocio_id} onChange={(e) => set("negocio_id", e.target.value)}>
              <option value="">— avulso —</option>
              {(negocios ?? []).map((n) => (
                <option key={n.id} value={n.id}>
                  {n.titulo || n.cliente_nome || n.id.slice(0, 8)}
                </option>
              ))}
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Descrição">
              <Input value={form.descricao} onChange={(e) => set("descricao", e.target.value)} />
            </Field>
          </div>
          <Field label="Valor (R$)">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.valor}
              onChange={(e) => set("valor", e.target.value)}
            />
          </Field>
          <Field label="Status">
            <Select value={form.status} onChange={(e) => set("status", e.target.value)}>
              {STATUS_EDITAVEIS.map((s) => (
                <option key={s} value={s}>
                  {rotuloStatus(s)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Data de entrega">
            <Input
              type="date"
              value={form.data_entrega}
              onChange={(e) => set("data_entrega", e.target.value)}
            />
          </Field>
          <Field label="Vencimento">
            <Input type="date" value={form.vencimento} onChange={(e) => set("vencimento", e.target.value)} />
          </Field>
          <Field label="Forma de pagamento">
            <Select value={form.forma_pagamento} onChange={(e) => set("forma_pagamento", e.target.value)}>
              <option value="">— a definir —</option>
              {FORMAS_PAGAMENTO.map((f) => (
                <option key={f} value={f}>
                  {LABEL_FORMA_PAGAMENTO[f]}
                </option>
              ))}
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Observações">
              <Textarea value={form.observacoes} onChange={(e) => set("observacoes", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Button
              className="w-full"
              onClick={salvar}
              disabled={!form.cliente_id}
              loading={criar.isPending || editar.isPending}
            >
              Salvar
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── Baixa ── */}
      <Modal open={baixa !== null} onClose={() => setBaixa(null)} title="Registrar recebimento">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {baixa?.cliente_nome} — {fmtMoeda(baixa?.valor)}
          </p>
          <Field label="Pago em">
            <Input
              type="date"
              value={formBaixa.pago_em}
              onChange={(e) => setFormBaixa((f) => ({ ...f, pago_em: e.target.value }))}
            />
          </Field>
          <Field label="Forma de pagamento">
            <Select
              value={formBaixa.forma_pagamento}
              onChange={(e) => setFormBaixa((f) => ({ ...f, forma_pagamento: e.target.value }))}
            >
              {FORMAS_PAGAMENTO.map((f) => (
                <option key={f} value={f}>
                  {LABEL_FORMA_PAGAMENTO[f]}
                </option>
              ))}
            </Select>
          </Field>
          <Button className="w-full" onClick={confirmarBaixa} loading={darBaixa.isPending}>
            Confirmar recebimento
          </Button>
        </div>
      </Modal>
    </div>
  );
}
