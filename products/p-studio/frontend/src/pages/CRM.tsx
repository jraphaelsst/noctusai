import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { api } from "@/lib/api";
import {
  useApiMutation,
  useClientes,
  useEtapasNegocio,
  useImoveis,
  useNegocios,
  useServicos,
} from "@/hooks/useApi";
import { Kanban } from "@/components/Kanban";
import {
  BotaoExcluir,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErroBox,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
  Textarea,
} from "@/components/ui";
import { FORMAS_PAGAMENTO, LABEL_FORMA_PAGAMENTO, TOM_NEGOCIO } from "@/lib/status";
import { fmtDataCurta, fmtMoeda } from "@/lib/utils";
import type { Negocio } from "@/types";

const FORM_VAZIO = {
  cliente_id: "",
  imovel_id: "",
  titulo: "",
  corretor: "",
  valor: "",
  prazo_entrega: "",
  forma_pagamento: "",
  observacoes: "",
  servico_ids: [] as string[],
};

export default function CRM() {
  const { data: negocios, isPending, error } = useNegocios();
  const { data: etapas } = useEtapasNegocio();
  const { data: clientes } = useClientes();
  const { data: imoveis } = useImoveis();
  const { data: servicos } = useServicos();

  const [modal, setModal] = useState<"novo" | "editar" | null>(null);
  const [selecionado, setSelecionado] = useState<Negocio | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const invalida = ["negocios", "producoes", "financeiro", "dashboard", "captacoes"];

  const criar = useApiMutation(invalida, (body: any) => api.post("/api/negocios", body), "Negócio criado");
  const editar = useApiMutation(
    invalida,
    ({ id, ...body }: any) => api.patch(`/api/negocios/${id}`, body),
    "Negócio atualizado"
  );
  const moverEtapa = useApiMutation(invalida, ({ id, etapa }: any) =>
    api.patch(`/api/negocios/${id}/etapa`, { etapa })
  );
  const excluir = useApiMutation(invalida, (id: string) => api.del(`/api/negocios/${id}`), "Negócio excluído");

  /** Soma dos serviços marcados — sugestão de valor quando o campo fica vazio. */
  const somaServicos = useMemo(
    () =>
      (servicos ?? [])
        .filter((s) => form.servico_ids.includes(s.id))
        .reduce((total, s) => total + (s.preco ?? 0), 0),
    [servicos, form.servico_ids]
  );

  const abrirNovo = () => {
    setForm(FORM_VAZIO);
    setSelecionado(null);
    setModal("novo");
  };

  const abrirEditar = (negocio: Negocio) => {
    setSelecionado(negocio);
    setForm({
      cliente_id: negocio.cliente_id,
      imovel_id: negocio.imovel_id ?? "",
      titulo: negocio.titulo ?? "",
      corretor: negocio.corretor ?? "",
      valor: String(negocio.valor ?? ""),
      prazo_entrega: negocio.prazo_entrega ?? "",
      forma_pagamento: (negocio.forma_pagamento as string) ?? "",
      observacoes: negocio.observacoes ?? "",
      servico_ids: negocio.servicos.map((s) => s.servico_id),
    });
    setModal("editar");
  };

  const salvar = async () => {
    const body: any = {
      cliente_id: form.cliente_id,
      imovel_id: form.imovel_id || null,
      titulo: form.titulo || null,
      corretor: form.corretor || null,
      // Valor vazio → o backend soma os serviços selecionados.
      valor: form.valor === "" ? null : Number(form.valor),
      prazo_entrega: form.prazo_entrega || null,
      forma_pagamento: form.forma_pagamento || null,
      observacoes: form.observacoes || null,
      servico_ids: form.servico_ids,
    };
    if (modal === "novo") await criar.mutateAsync(body);
    else if (selecionado) await editar.mutateAsync({ id: selecionado.id, ...body });
    setModal(null);
  };

  const totalGeral = (negocios ?? []).reduce((s, n) => s + (n.valor ?? 0), 0);

  if (isPending && !negocios) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  return (
    <div>
      <PageHeader
        title="CRM comercial"
        description={`Pipeline de vendas — do lead ao arquivamento. ${negocios?.length ?? 0} negócio(s), ${fmtMoeda(totalGeral)} em jogo.`}
        action={
          <Button onClick={abrirNovo} disabled={!clientes?.length}>
            <Plus className="h-4 w-4" /> Novo lead
          </Button>
        }
      />

      {!clientes?.length && (
        <div className="mb-4">
          <EmptyState>Cadastre um cliente antes de abrir um negócio.</EmptyState>
        </div>
      )}

      <Kanban
        colunas={etapas ?? []}
        itens={negocios ?? []}
        etapaDoItem={(n) => n.etapa as string}
        tomDaEtapa={(e) => TOM_NEGOCIO[e] ?? "lead"}
        totalDaColuna={(itens) => fmtMoeda(itens.reduce((s, n) => s + (n.valor ?? 0), 0))}
        onMover={(negocio, etapa) => moverEtapa.mutate({ id: negocio.id, etapa })}
        renderCard={(negocio) => (
          <Card className="p-3.5" onClick={() => abrirEditar(negocio)}>
            <div className="text-sm font-medium">
              {negocio.titulo || negocio.cliente_nome || "Negócio"}
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">{negocio.cliente_nome ?? "—"}</div>
            {negocio.imovel_endereco && (
              <div className="mt-2 truncate text-xs text-muted-foreground">{negocio.imovel_endereco}</div>
            )}
            <div className="mt-2 flex flex-wrap gap-1">
              {negocio.servicos.map((s) => (
                <span
                  key={s.id}
                  className="rounded bg-accent px-1.5 py-0.5 text-[10px] text-accent-foreground"
                >
                  {s.nome}
                </span>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
              <span className="text-xs text-muted-foreground">
                {negocio.prazo_entrega ? fmtDataCurta(negocio.prazo_entrega) : "sem prazo"}
              </span>
              <span className="text-sm font-medium text-primary">{fmtMoeda(negocio.valor)}</span>
            </div>
          </Card>
        )}
      />

      <Modal
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === "novo" ? "Novo negócio" : "Editar negócio"}
        wide
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Cliente *">
            <Select value={form.cliente_id} onChange={(e) => set("cliente_id", e.target.value)}>
              <option value="">— selecione —</option>
              {(clientes ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                  {c.empresa ? ` — ${c.empresa}` : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Imóvel">
            <Select value={form.imovel_id} onChange={(e) => set("imovel_id", e.target.value)}>
              <option value="">— sem imóvel —</option>
              {(imoveis ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.codigo} — {i.endereco}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Título">
            <Input
              value={form.titulo}
              placeholder="Ex.: Ensaio Rua Oscar Freire"
              onChange={(e) => set("titulo", e.target.value)}
            />
          </Field>
          <Field label="Corretor">
            <Input value={form.corretor} onChange={(e) => set("corretor", e.target.value)} />
          </Field>

          <div className="sm:col-span-2">
            <Field label="Serviços">
              <div className="grid gap-1.5 rounded-md border border-border p-3 sm:grid-cols-2">
                {(servicos ?? []).map((s) => (
                  <Checkbox
                    key={s.id}
                    checked={form.servico_ids.includes(s.id)}
                    onChange={(marcado) =>
                      set(
                        "servico_ids",
                        marcado
                          ? [...form.servico_ids, s.id]
                          : form.servico_ids.filter((id) => id !== s.id)
                      )
                    }
                    label={
                      <span>
                        {s.nome}{" "}
                        <span className="text-xs text-muted-foreground">
                          {fmtMoeda(s.preco)} · {s.prazo_dias}d
                        </span>
                      </span>
                    }
                  />
                ))}
                {!servicos?.length && (
                  <p className="text-xs text-muted-foreground">Nenhum serviço no catálogo.</p>
                )}
              </div>
            </Field>
          </div>

          <Field label={`Valor (R$) — em branco soma os serviços: ${fmtMoeda(somaServicos)}`}>
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.valor}
              onChange={(e) => set("valor", e.target.value)}
            />
          </Field>
          <Field label="Prazo de entrega">
            <Input
              type="date"
              value={form.prazo_entrega}
              onChange={(e) => set("prazo_entrega", e.target.value)}
            />
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
          {selecionado && (
            <div className="flex items-end">
              <StatusBadge tom={TOM_NEGOCIO[selecionado.etapa as string] ?? "lead"}>
                {(etapas ?? []).find((e) => e.id === selecionado.etapa)?.label ?? selecionado.etapa}
              </StatusBadge>
            </div>
          )}
          <div className="sm:col-span-2">
            <Field label="Observações">
              <Textarea value={form.observacoes} onChange={(e) => set("observacoes", e.target.value)} />
            </Field>
          </div>

          <div className="flex gap-2 sm:col-span-2">
            <Button
              className="flex-1"
              onClick={salvar}
              disabled={!form.cliente_id}
              loading={criar.isPending || editar.isPending}
            >
              Salvar
            </Button>
            {selecionado && (
              <BotaoExcluir
                confirmando={confirmando === selecionado.id}
                onPedirConfirmacao={() => setConfirmando(selecionado.id)}
                onConfirmar={() => {
                  excluir.mutate(selecionado.id);
                  setConfirmando(null);
                  setModal(null);
                }}
              />
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}
