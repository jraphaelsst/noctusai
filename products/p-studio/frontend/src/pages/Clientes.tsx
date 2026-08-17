import { useMemo, useState } from "react";
import { Building2, Camera, Pencil, Plus, Repeat, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { useApiMutation, useClientes, useClientesMetricas } from "@/hooks/useApi";
import {
  Badge,
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
  Spinner,
  Textarea,
} from "@/components/ui";
import { fmtData, fmtMoeda } from "@/lib/utils";
import type { Cliente } from "@/types";

const FORM_VAZIO = {
  nome: "",
  empresa: "",
  corretor: "",
  email: "",
  telefone: "",
  cidade: "",
  estado: "",
  observacoes: "",
};

export default function Clientes() {
  const [incluirInativos, setIncluirInativos] = useState(false);
  const { data: clientes, isLoading, error } = useClientes(incluirInativos);
  const { data: metricas } = useClientesMetricas();

  const [modal, setModal] = useState<"novo" | "editar" | null>(null);
  const [selecionado, setSelecionado] = useState<Cliente | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const porCliente = useMemo(
    () => Object.fromEntries((metricas ?? []).map((m) => [m.cliente_id, m])),
    [metricas]
  );

  const criar = useApiMutation(
    ["clientes", "clientes-metricas", "dashboard"],
    (body: any) => api.post("/api/clientes", body),
    "Cliente cadastrado"
  );
  const editar = useApiMutation(
    ["clientes", "clientes-metricas", "negocios", "dashboard"],
    ({ id, ...body }: any) => api.patch(`/api/clientes/${id}`, body),
    "Cliente atualizado"
  );
  const excluir = useApiMutation(
    ["clientes", "clientes-metricas", "dashboard"],
    (id: string) => api.del(`/api/clientes/${id}`),
    "Cliente removido"
  );

  const abrirNovo = () => {
    setForm(FORM_VAZIO);
    setSelecionado(null);
    setModal("novo");
  };

  const abrirEditar = (cliente: Cliente) => {
    setSelecionado(cliente);
    setForm({
      nome: cliente.nome,
      empresa: cliente.empresa ?? "",
      corretor: cliente.corretor ?? "",
      email: cliente.email ?? "",
      telefone: cliente.telefone ?? "",
      cidade: cliente.cidade ?? "",
      estado: cliente.estado ?? "",
      observacoes: cliente.observacoes ?? "",
    });
    setModal("editar");
  };

  const salvar = async () => {
    const body = {
      nome: form.nome,
      empresa: form.empresa || null,
      corretor: form.corretor || null,
      email: form.email || null,
      telefone: form.telefone || null,
      cidade: form.cidade || null,
      estado: form.estado || null,
      observacoes: form.observacoes || null,
    };
    if (modal === "novo") await criar.mutateAsync(body);
    else if (selecionado) await editar.mutateAsync({ id: selecionado.id, ...body });
    setModal(null);
  };

  if (isLoading) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  return (
    <div>
      <PageHeader
        title="Gestão de clientes"
        description="Imobiliárias, corretores e incorporadoras — com as métricas calculadas de verdade."
        action={
          <div className="flex items-center gap-3">
            <Checkbox
              checked={incluirInativos}
              onChange={setIncluirInativos}
              label={<span className="text-xs text-muted-foreground">Mostrar inativos</span>}
            />
            <Button onClick={abrirNovo}>
              <Plus className="h-4 w-4" /> Novo cliente
            </Button>
          </div>
        }
      />

      {(clientes ?? []).length === 0 ? (
        <EmptyState>Nenhum cliente cadastrado. Clique em “Novo cliente” para começar.</EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(clientes ?? []).map((cliente) => {
            const m = porCliente[cliente.id];
            return (
              <Card key={cliente.id} className="flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-display text-lg">{cliente.nome}</div>
                    <div className="truncate text-sm text-muted-foreground">
                      {cliente.empresa ?? "—"}
                    </div>
                    {cliente.corretor && (
                      <div className="mt-0.5 truncate text-xs text-muted-foreground">
                        Corretor: {cliente.corretor}
                      </div>
                    )}
                  </div>
                  {!cliente.ativo && <Badge>inativo</Badge>}
                </div>

                <div className="space-y-0.5 text-xs text-muted-foreground">
                  {cliente.email && <div className="truncate">{cliente.email}</div>}
                  {cliente.telefone && <div>{cliente.telefone}</div>}
                  {(cliente.cidade || cliente.estado) && (
                    <div>
                      {[cliente.cidade, cliente.estado].filter(Boolean).join(" / ")}
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2 border-y border-border py-3 text-xs">
                  <Metrica
                    icone={<TrendingUp className="h-3.5 w-3.5" />}
                    rotulo="Faturamento"
                    valor={fmtMoeda(m?.faturamento_total ?? 0)}
                  />
                  <Metrica
                    icone={<Repeat className="h-3.5 w-3.5" />}
                    rotulo="Ticket médio"
                    valor={fmtMoeda(m?.ticket_medio ?? 0)}
                  />
                  <Metrica
                    icone={<Camera className="h-3.5 w-3.5" />}
                    rotulo="Serviços"
                    valor={String(m?.total_servicos ?? 0)}
                  />
                  <Metrica
                    icone={<Building2 className="h-3.5 w-3.5" />}
                    rotulo="Imóveis"
                    valor={String(m?.total_imoveis ?? 0)}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    Último serviço: {fmtData(m?.ultimo_servico)}
                  </span>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" title="Editar" onClick={() => abrirEditar(cliente)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <BotaoExcluir
                      confirmando={confirmando === cliente.id}
                      onPedirConfirmacao={() => setConfirmando(cliente.id)}
                      onConfirmar={() => {
                        excluir.mutate(cliente.id);
                        setConfirmando(null);
                      }}
                    />
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === "novo" ? "Novo cliente" : `Editar ${selecionado?.nome ?? ""}`}
        wide
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nome *">
            <Input value={form.nome} onChange={(e) => set("nome", e.target.value)} />
          </Field>
          <Field label="Empresa / imobiliária">
            <Input value={form.empresa} onChange={(e) => set("empresa", e.target.value)} />
          </Field>
          <Field label="Corretor de contato">
            <Input value={form.corretor} onChange={(e) => set("corretor", e.target.value)} />
          </Field>
          <Field label="Email">
            <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label="Telefone">
            <Input value={form.telefone} onChange={(e) => set("telefone", e.target.value)} />
          </Field>
          <Field label="Cidade">
            <Input value={form.cidade} onChange={(e) => set("cidade", e.target.value)} />
          </Field>
          <Field label="Estado">
            <Input
              value={form.estado}
              maxLength={2}
              placeholder="SP"
              onChange={(e) => set("estado", e.target.value.toUpperCase())}
            />
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
              disabled={!form.nome}
              loading={criar.isPending || editar.isPending}
            >
              Salvar
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function Metrica({ icone, rotulo, valor }: { icone: React.ReactNode; rotulo: string; valor: string }) {
  return (
    <div>
      <div className="flex items-center gap-1 text-muted-foreground">
        {icone}
        <span className="text-[11px] uppercase tracking-wider">{rotulo}</span>
      </div>
      <div className="mt-0.5 font-medium text-foreground">{valor}</div>
    </div>
  );
}
