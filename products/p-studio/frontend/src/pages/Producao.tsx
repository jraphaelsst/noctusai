import { useState } from "react";
import { MessageSquarePlus, Plus } from "lucide-react";
import { api } from "@/lib/api";
import {
  useApiMutation,
  useCaptacoes,
  useClientes,
  useEtapasProducao,
  useNegocios,
  useProducoes,
} from "@/hooks/useApi";
import { Kanban } from "@/components/Kanban";
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
  StatusBadge,
  Textarea,
} from "@/components/ui";
import { TOM_PRODUCAO } from "@/lib/status";
import { fmtData, fmtDataCurta } from "@/lib/utils";
import type { Producao } from "@/types";

const FORM_VAZIO = {
  negocio_id: "",
  captacao_id: "",
  cliente_id: "",
  responsavel: "",
  prazo_entrega: "",
  observacoes: "",
};

export default function ProducaoPage() {
  const { data: producoes, isLoading, error } = useProducoes();
  const { data: etapas } = useEtapasProducao();
  const { data: clientes } = useClientes();
  const { data: negocios } = useNegocios();
  const { data: captacoes } = useCaptacoes();

  const [modalNova, setModalNova] = useState(false);
  const [detalhe, setDetalhe] = useState<Producao | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [comentario, setComentario] = useState("");
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const invalida = ["producoes", "dashboard", "negocios", "financeiro"];

  const criar = useApiMutation(invalida, (body: any) => api.post("/api/producoes", body), "Produção aberta");
  const editar = useApiMutation(invalida, ({ id, ...body }: any) =>
    api.patch(`/api/producoes/${id}`, body)
  );
  const moverEtapa = useApiMutation(invalida, ({ id, ...body }: any) =>
    api.patch(`/api/producoes/${id}/etapa`, body)
  );
  const comentar = useApiMutation(
    invalida,
    ({ id, ...body }: any) => api.post(`/api/producoes/${id}/eventos`, body),
    "Comentário registrado"
  );
  const excluir = useApiMutation(invalida, (id: string) => api.del(`/api/producoes/${id}`), "Produção excluída");

  // O detalhe aberto precisa refletir a lista recarregada (eventos novos).
  const detalheAtual = detalhe ? (producoes ?? []).find((p) => p.id === detalhe.id) ?? detalhe : null;

  const salvarNova = async () => {
    await criar.mutateAsync({
      negocio_id: form.negocio_id || null,
      captacao_id: form.captacao_id || null,
      cliente_id: form.cliente_id || null,
      responsavel: form.responsavel || null,
      prazo_entrega: form.prazo_entrega || null,
      observacoes: form.observacoes || null,
    });
    setForm(FORM_VAZIO);
    setModalNova(false);
  };

  const enviarComentario = async () => {
    if (!detalheAtual || !comentario.trim()) return;
    await comentar.mutateAsync({ id: detalheAtual.id, comentario: comentario.trim() });
    setComentario("");
  };

  if (isLoading) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  const rotuloEtapa = (id: string) => (etapas ?? []).find((e) => e.id === id)?.label ?? id;

  return (
    <div>
      <PageHeader
        title="Pipeline de produção"
        description="Do agendamento à entrega — arraste o cartão para avançar a etapa."
        action={
          <Button onClick={() => setModalNova(true)}>
            <Plus className="h-4 w-4" /> Nova produção
          </Button>
        }
      />

      {(producoes ?? []).length === 0 && (
        <div className="mb-4">
          <EmptyState>
            Nenhuma produção aberta. O caminho normal é o CRM abrir sozinho quando o negócio entra em
            “Produção”; use “Nova produção” para o trabalho que não passou pelo funil.
          </EmptyState>
        </div>
      )}

      <Kanban
        colunas={etapas ?? []}
        itens={producoes ?? []}
        etapaDoItem={(p) => p.etapa as string}
        tomDaEtapa={(e) => TOM_PRODUCAO[e] ?? "scheduled"}
        largura="w-64"
        onMover={(producao, etapa) => moverEtapa.mutate({ id: producao.id, etapa })}
        renderCard={(producao) => (
          <Card className="p-3.5" onClick={() => setDetalhe(producao)}>
            <div className="text-sm font-medium">{producao.cliente_nome ?? "Sem cliente"}</div>
            {producao.endereco && (
              <div className="mt-0.5 truncate text-xs text-muted-foreground">{producao.endereco}</div>
            )}
            <div className="mt-3 flex items-center justify-between border-t border-border pt-2 text-xs text-muted-foreground">
              <span className="truncate">{producao.responsavel ?? "a definir"}</span>
              <span>{producao.prazo_entrega ? fmtDataCurta(producao.prazo_entrega) : "—"}</span>
            </div>
          </Card>
        )}
      />

      {/* ── Nova produção ── */}
      <Modal open={modalNova} onClose={() => setModalNova(false)} title="Nova produção" wide>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Cliente">
            <Select value={form.cliente_id} onChange={(e) => set("cliente_id", e.target.value)}>
              <option value="">— sem cliente —</option>
              {(clientes ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Negócio">
            <Select value={form.negocio_id} onChange={(e) => set("negocio_id", e.target.value)}>
              <option value="">— avulsa —</option>
              {(negocios ?? []).map((n) => (
                <option key={n.id} value={n.id}>
                  {n.titulo || n.cliente_nome || n.id.slice(0, 8)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Captação">
            <Select value={form.captacao_id} onChange={(e) => set("captacao_id", e.target.value)}>
              <option value="">— sem captação —</option>
              {(captacoes ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {fmtData(c.data)} — {c.endereco}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Responsável">
            <Input
              value={form.responsavel}
              placeholder="Ex.: Bruna Editora"
              onChange={(e) => set("responsavel", e.target.value)}
            />
          </Field>
          <Field label="Prazo de entrega">
            <Input
              type="date"
              value={form.prazo_entrega}
              onChange={(e) => set("prazo_entrega", e.target.value)}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Observações">
              <Textarea value={form.observacoes} onChange={(e) => set("observacoes", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Button className="w-full" onClick={salvarNova} loading={criar.isPending}>
              Abrir produção
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── Detalhe + histórico ── */}
      <Modal
        open={detalheAtual !== null}
        onClose={() => setDetalhe(null)}
        title={detalheAtual?.cliente_nome ?? "Produção"}
        wide
      >
        {detalheAtual && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tom={TOM_PRODUCAO[detalheAtual.etapa as string] ?? "scheduled"}>
                {rotuloEtapa(detalheAtual.etapa as string)}
              </StatusBadge>
              {detalheAtual.endereco && (
                <span className="text-sm text-muted-foreground">{detalheAtual.endereco}</span>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Etapa">
                <Select
                  value={detalheAtual.etapa as string}
                  onChange={(e) => moverEtapa.mutate({ id: detalheAtual.id, etapa: e.target.value })}
                >
                  {(etapas ?? []).map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Responsável">
                <Input
                  defaultValue={detalheAtual.responsavel ?? ""}
                  onBlur={(e) =>
                    e.target.value !== (detalheAtual.responsavel ?? "") &&
                    editar.mutate({ id: detalheAtual.id, responsavel: e.target.value || null })
                  }
                />
              </Field>
              <Field label="Prazo de entrega">
                <Input
                  type="date"
                  defaultValue={detalheAtual.prazo_entrega ?? ""}
                  onBlur={(e) =>
                    e.target.value !== (detalheAtual.prazo_entrega ?? "") &&
                    editar.mutate({ id: detalheAtual.id, prazo_entrega: e.target.value || null })
                  }
                />
              </Field>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium">Histórico</h3>
              <div className="max-h-64 space-y-2 overflow-y-auto rounded-md border border-border p-3">
                {detalheAtual.eventos.length === 0 && (
                  <p className="text-xs text-muted-foreground">Nenhum evento ainda.</p>
                )}
                {detalheAtual.eventos.map((evento) => (
                  <div key={evento.id} className="border-b border-border pb-2 last:border-0 last:pb-0">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <StatusBadge tom={TOM_PRODUCAO[evento.etapa] ?? "scheduled"}>
                        {rotuloEtapa(evento.etapa)}
                      </StatusBadge>
                      <span>{new Date(evento.created_at).toLocaleString("pt-BR")}</span>
                      {evento.responsavel && <span>· {evento.responsavel}</span>}
                    </div>
                    {evento.comentario && <p className="mt-1 text-sm">{evento.comentario}</p>}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <Input
                value={comentario}
                placeholder="Comentar nesta produção…"
                onChange={(e) => setComentario(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && enviarComentario()}
              />
              <Button onClick={enviarComentario} loading={comentar.isPending} disabled={!comentario.trim()}>
                <MessageSquarePlus className="h-4 w-4" /> Comentar
              </Button>
            </div>

            <div className="flex justify-end border-t border-border pt-3">
              <BotaoExcluir
                confirmando={confirmando === detalheAtual.id}
                onPedirConfirmacao={() => setConfirmando(detalheAtual.id)}
                onConfirmar={() => {
                  excluir.mutate(detalheAtual.id);
                  setConfirmando(null);
                  setDetalhe(null);
                }}
                titulo="Excluir produção"
              />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
