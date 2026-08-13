import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Clock, MapPin, Package, Plus, User } from "lucide-react";
import { api } from "@/lib/api";
import {
  useApiMutation,
  useCaptacoes,
  useClientes,
  useEquipamentos,
  useImoveis,
  useNegocios,
} from "@/hooks/useApi";
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
import {
  LABEL_CATEGORIA_EQUIPAMENTO,
  LABEL_STATUS_CAPTACAO,
  TOM_CAPTACAO,
} from "@/lib/status";
import {
  fimMes,
  fmtDataExtenso,
  fmtHora,
  fmtHoraFim,
  hojeISO,
  inicioMes,
  inicioSemana,
  somaDias,
} from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { Captacao } from "@/types";

type Visao = "dia" | "semana" | "mes";

const FORM_VAZIO = {
  cliente_id: "",
  imovel_id: "",
  negocio_id: "",
  data: hojeISO(),
  hora: "09:00",
  duracao_minutos: "120",
  endereco: "",
  maps_url: "",
  responsavel: "",
  observacoes: "",
  equipamento_ids: [] as string[],
};

/** Intervalo [inicio, fim] da visão corrente. */
function periodo(visao: Visao, ancora: string): [string, string] {
  if (visao === "dia") return [ancora, ancora];
  if (visao === "semana") {
    const inicio = inicioSemana(ancora);
    return [inicio, somaDias(inicio, 6)];
  }
  return [inicioMes(ancora), fimMes(ancora)];
}

export default function Agenda() {
  const [visao, setVisao] = useState<Visao>("semana");
  const [ancora, setAncora] = useState(hojeISO());
  const [inicio, fim] = periodo(visao, ancora);

  const { data: captacoes, isLoading, error } = useCaptacoes(inicio, fim);
  const { data: clientes } = useClientes();
  const { data: imoveis } = useImoveis();
  const { data: negocios } = useNegocios();
  const { data: equipamentos } = useEquipamentos();

  const [modal, setModal] = useState<"nova" | "editar" | null>(null);
  const [selecionada, setSelecionada] = useState<Captacao | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const invalida = ["captacoes", "producoes", "dashboard"];

  const criar = useApiMutation(invalida, (body: any) => api.post("/api/captacoes", body), "Captação agendada");
  const editar = useApiMutation(
    invalida,
    ({ id, ...body }: any) => api.patch(`/api/captacoes/${id}`, body),
    "Captação atualizada"
  );
  const marcarItem = useApiMutation(["captacoes"], ({ itemId, conferido }: any) =>
    api.patch(`/api/captacoes/checklist/${itemId}`, { conferido })
  );
  const excluir = useApiMutation(invalida, (id: string) => api.del(`/api/captacoes/${id}`), "Captação excluída");

  const selecionadaAtual = selecionada
    ? (captacoes ?? []).find((c) => c.id === selecionada.id) ?? selecionada
    : null;

  /** Captações agrupadas por dia, ordenadas por hora. */
  const porDia = useMemo(() => {
    const mapa: Record<string, Captacao[]> = {};
    for (const c of captacoes ?? []) (mapa[c.data] ||= []).push(c);
    for (const dia of Object.keys(mapa)) mapa[dia].sort((a, b) => a.hora.localeCompare(b.hora));
    return mapa;
  }, [captacoes]);

  const dias = useMemo(() => {
    const lista: string[] = [];
    let cursor = inicio;
    while (cursor <= fim) {
      lista.push(cursor);
      cursor = somaDias(cursor, 1);
    }
    return lista;
  }, [inicio, fim]);

  const navegar = (passo: number) => {
    if (visao === "dia") setAncora(somaDias(ancora, passo));
    else if (visao === "semana") setAncora(somaDias(ancora, passo * 7));
    else {
      const [y, m] = ancora.slice(0, 7).split("-").map(Number);
      const d = new Date(y, m - 1 + passo, 1);
      setAncora(d.toLocaleDateString("sv-SE"));
    }
  };

  const abrirNova = (data?: string) => {
    setForm({ ...FORM_VAZIO, data: data ?? ancora });
    setSelecionada(null);
    setModal("nova");
  };

  const abrirEditar = (captacao: Captacao) => {
    setSelecionada(captacao);
    setForm({
      cliente_id: captacao.cliente_id ?? "",
      imovel_id: captacao.imovel_id ?? "",
      negocio_id: captacao.negocio_id ?? "",
      data: captacao.data,
      hora: fmtHora(captacao.hora),
      duracao_minutos: String(captacao.duracao_minutos ?? 120),
      endereco: captacao.endereco,
      maps_url: captacao.maps_url ?? "",
      responsavel: captacao.responsavel ?? "",
      observacoes: captacao.observacoes ?? "",
      equipamento_ids: captacao.equipamentos.map((e) => e.equipamento_id),
    });
    setModal("editar");
  };

  const salvar = async () => {
    const body = {
      cliente_id: form.cliente_id || null,
      imovel_id: form.imovel_id || null,
      negocio_id: form.negocio_id || null,
      data: form.data,
      hora: `${form.hora}:00`,
      duracao_minutos: Number(form.duracao_minutos) || 120,
      endereco: form.endereco,
      maps_url: form.maps_url || null,
      responsavel: form.responsavel || null,
      observacoes: form.observacoes || null,
      equipamento_ids: form.equipamento_ids,
    };
    if (modal === "nova") await criar.mutateAsync(body);
    else if (selecionada) await editar.mutateAsync({ id: selecionada.id, ...body });
    setModal(null);
  };

  /** Preenche o endereço automaticamente ao escolher um imóvel. */
  const escolherImovel = (id: string) => {
    set("imovel_id", id);
    const imovel = (imoveis ?? []).find((i) => i.id === id);
    if (imovel) {
      set("endereco", imovel.endereco);
      if (imovel.maps_url) set("maps_url", imovel.maps_url);
      if (imovel.cliente_id) set("cliente_id", imovel.cliente_id);
    }
  };

  if (isLoading) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  return (
    <div>
      <PageHeader
        title="Agenda operacional"
        description="Captações agendadas com checklist de equipamentos — tudo persistido no backend."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex overflow-hidden rounded-md border border-border">
              {(["dia", "semana", "mes"] as Visao[]).map((v) => (
                <button
                  key={v}
                  onClick={() => setVisao(v)}
                  className={cn(
                    "px-3 py-1.5 text-sm capitalize",
                    visao === v ? "bg-primary text-primary-foreground" : "hover:bg-accent"
                  )}
                >
                  {v === "dia" ? "Dia" : v === "semana" ? "Semana" : "Mês"}
                </button>
              ))}
            </div>
            <Button variant="outline" size="icon" onClick={() => navegar(-1)} aria-label="Anterior">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setAncora(hojeISO())}>
              Hoje
            </Button>
            <Button variant="outline" size="icon" onClick={() => navegar(1)} aria-label="Próximo">
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button onClick={() => abrirNova()}>
              <Plus className="h-4 w-4" /> Nova captação
            </Button>
          </div>
        }
      />

      {(captacoes ?? []).length === 0 ? (
        <EmptyState>Nenhuma captação neste período.</EmptyState>
      ) : visao === "mes" ? (
        <GradeMes dias={dias} porDia={porDia} onAbrir={abrirEditar} onNova={abrirNova} />
      ) : (
        <div className="space-y-4">
          {dias
            .filter((d) => visao === "dia" || (porDia[d] ?? []).length > 0)
            .map((dia) => (
              <div key={dia}>
                <h2 className="mb-2 text-sm font-medium capitalize text-muted-foreground">
                  {fmtDataExtenso(dia)}
                </h2>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {(porDia[dia] ?? []).map((c) => (
                    <CardCaptacao key={c.id} captacao={c} onClick={() => abrirEditar(c)} />
                  ))}
                  {(porDia[dia] ?? []).length === 0 && (
                    <p className="text-sm text-muted-foreground">Nada agendado.</p>
                  )}
                </div>
              </div>
            ))}
        </div>
      )}

      <Modal
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === "nova" ? "Nova captação" : "Editar captação"}
        wide
      >
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
          <Field label="Imóvel (preenche o endereço)">
            <Select value={form.imovel_id} onChange={(e) => escolherImovel(e.target.value)}>
              <option value="">— sem imóvel —</option>
              {(imoveis ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.codigo} — {i.endereco}
                </option>
              ))}
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Endereço *">
              <Input value={form.endereco} onChange={(e) => set("endereco", e.target.value)} />
            </Field>
          </div>
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
          <Field label="Responsável">
            <Input
              value={form.responsavel}
              placeholder="Ex.: Pedro Fotógrafo"
              onChange={(e) => set("responsavel", e.target.value)}
            />
          </Field>
          <Field label="Data *">
            <Input type="date" value={form.data} onChange={(e) => set("data", e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Hora">
              <Input type="time" value={form.hora} onChange={(e) => set("hora", e.target.value)} />
            </Field>
            <Field label="Duração (min)">
              <Input
                type="number"
                min={15}
                step={15}
                value={form.duracao_minutos}
                onChange={(e) => set("duracao_minutos", e.target.value)}
              />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Link do Google Maps">
              <Input value={form.maps_url} onChange={(e) => set("maps_url", e.target.value)} />
            </Field>
          </div>

          <div className="sm:col-span-2">
            <Field label="Checklist de equipamentos">
              <div className="grid gap-1.5 rounded-md border border-border p-3 sm:grid-cols-2">
                {(equipamentos ?? []).map((eq) => (
                  <Checkbox
                    key={eq.id}
                    checked={form.equipamento_ids.includes(eq.id)}
                    onChange={(marcado) =>
                      set(
                        "equipamento_ids",
                        marcado
                          ? [...form.equipamento_ids, eq.id]
                          : form.equipamento_ids.filter((id) => id !== eq.id)
                      )
                    }
                    label={
                      <span>
                        {eq.nome}{" "}
                        <span className="text-xs text-muted-foreground">
                          {LABEL_CATEGORIA_EQUIPAMENTO[eq.categoria as string] ?? eq.categoria ?? ""}
                        </span>
                      </span>
                    }
                  />
                ))}
                {!equipamentos?.length && (
                  <p className="text-xs text-muted-foreground">Nenhum equipamento cadastrado.</p>
                )}
              </div>
            </Field>
          </div>

          <div className="sm:col-span-2">
            <Field label="Observações">
              <Textarea value={form.observacoes} onChange={(e) => set("observacoes", e.target.value)} />
            </Field>
          </div>

          {/* Conferência do checklist — só faz sentido numa captação já salva. */}
          {selecionadaAtual && selecionadaAtual.equipamentos.length > 0 && (
            <div className="sm:col-span-2">
              <Field label="Conferência antes de sair do estúdio">
                <div className="grid gap-1.5 rounded-md border border-border p-3 sm:grid-cols-2">
                  {selecionadaAtual.equipamentos.map((item) => (
                    <Checkbox
                      key={item.id}
                      checked={item.conferido}
                      onChange={(conferido) => marcarItem.mutate({ itemId: item.id, conferido })}
                      label={<span className="text-sm">{item.nome ?? "Equipamento"}</span>}
                    />
                  ))}
                </div>
              </Field>
            </div>
          )}

          {selecionadaAtual && (
            <Field label="Status">
              <Select
                value={selecionadaAtual.status as string}
                onChange={(e) => editar.mutate({ id: selecionadaAtual.id, status: e.target.value })}
              >
                {Object.entries(LABEL_STATUS_CAPTACAO).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
          )}

          <div className="flex items-end gap-2 sm:col-span-2">
            <Button
              className="flex-1"
              onClick={salvar}
              disabled={!form.endereco || !form.data}
              loading={criar.isPending || editar.isPending}
            >
              Salvar
            </Button>
            {selecionadaAtual && (
              <BotaoExcluir
                confirmando={confirmando === selecionadaAtual.id}
                onPedirConfirmacao={() => setConfirmando(selecionadaAtual.id)}
                onConfirmar={() => {
                  excluir.mutate(selecionadaAtual.id);
                  setConfirmando(null);
                  setModal(null);
                }}
                titulo="Excluir captação"
              />
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}

function CardCaptacao({ captacao, onClick }: { captacao: Captacao; onClick: () => void }) {
  const conferidos = captacao.equipamentos.filter((e) => e.conferido).length;
  return (
    <Card onClick={onClick}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium">{captacao.cliente_nome ?? "Sem cliente"}</div>
          <div className="mt-0.5 flex items-center gap-1 truncate text-xs text-muted-foreground">
            <MapPin className="h-3.5 w-3.5 shrink-0" />
            {captacao.endereco}
          </div>
        </div>
        <StatusBadge tom={TOM_CAPTACAO[captacao.status as string] ?? "scheduled"}>
          {LABEL_STATUS_CAPTACAO[captacao.status as string] ?? captacao.status}
        </StatusBadge>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-border pt-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <Clock className="h-3.5 w-3.5" />
          {fmtHora(captacao.hora)}–{fmtHoraFim(captacao.hora, captacao.duracao_minutos)}
        </span>
        <span className="flex items-center gap-1">
          <User className="h-3.5 w-3.5" />
          {captacao.responsavel ?? "a definir"}
        </span>
        {captacao.equipamentos.length > 0 && (
          <span className="flex items-center gap-1">
            <Package className="h-3.5 w-3.5" />
            {conferidos}/{captacao.equipamentos.length}
          </span>
        )}
      </div>
    </Card>
  );
}

function GradeMes({
  dias,
  porDia,
  onAbrir,
  onNova,
}: {
  dias: string[];
  porDia: Record<string, Captacao[]>;
  onAbrir: (c: Captacao) => void;
  onNova: (data: string) => void;
}) {
  const primeiro = dias[0];
  const [y, m, d] = primeiro.slice(0, 10).split("-").map(Number);
  const offset = new Date(y, m - 1, d).getDay();

  return (
    <Card className="p-2">
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] uppercase tracking-wider text-muted-foreground">
        {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((dia) => (
          <div key={dia} className="py-1">
            {dia}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: offset }).map((_, i) => (
          <div key={`vazio-${i}`} />
        ))}
        {dias.map((dia) => (
          <div
            key={dia}
            className="min-h-24 rounded-md border border-border p-1.5 text-left transition-colors hover:border-primary/40"
          >
            <button
              onClick={() => onNova(dia)}
              className="mb-1 text-xs text-muted-foreground hover:text-primary"
            >
              {Number(dia.slice(8, 10))}
            </button>
            <div className="space-y-1">
              {(porDia[dia] ?? []).map((c) => (
                <button
                  key={c.id}
                  onClick={() => onAbrir(c)}
                  className="block w-full truncate rounded bg-primary/10 px-1.5 py-0.5 text-left text-[11px] text-primary"
                >
                  {fmtHora(c.hora)} {c.cliente_nome ?? c.endereco}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
