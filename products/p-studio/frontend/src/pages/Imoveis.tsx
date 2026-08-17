import { useMemo, useState } from "react";
import { Bath, BedDouble, Car, MapPin, Pencil, Plus, Ruler } from "lucide-react";
import { api } from "@/lib/api";
import { useApiMutation, useClientes, useImoveis } from "@/hooks/useApi";
import {
  Badge,
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
  Textarea,
} from "@/components/ui";
import {
  LABEL_PADRAO_IMOVEL,
  LABEL_TIPO_IMOVEL,
  PADROES_IMOVEL,
  TIPOS_IMOVEL,
} from "@/lib/status";
import { fmtMoeda } from "@/lib/utils";
import type { Imovel } from "@/types";

const FORM_VAZIO = {
  cliente_id: "",
  codigo: "",
  endereco: "",
  condominio: "",
  cidade: "",
  estado: "",
  tipo: "apartamento",
  padrao: "medio",
  area: "",
  dormitorios: "0",
  banheiros: "0",
  vagas: "0",
  valor: "",
  maps_url: "",
  observacoes: "",
};

export default function Imoveis() {
  const { data: imoveis, isLoading, error } = useImoveis();
  const { data: clientes } = useClientes();

  const [busca, setBusca] = useState("");
  const [filtroTipo, setFiltroTipo] = useState("");
  const [modal, setModal] = useState<"novo" | "editar" | null>(null);
  const [selecionado, setSelecionado] = useState<Imovel | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const nomeCliente = useMemo(
    () => Object.fromEntries((clientes ?? []).map((c) => [c.id, c.nome])),
    [clientes]
  );

  const criar = useApiMutation(["imoveis", "dashboard"], (body: any) => api.post("/api/imoveis", body), "Imóvel cadastrado");
  const editar = useApiMutation(
    ["imoveis", "negocios", "captacoes"],
    ({ id, ...body }: any) => api.patch(`/api/imoveis/${id}`, body),
    "Imóvel atualizado"
  );
  const excluir = useApiMutation(["imoveis"], (id: string) => api.del(`/api/imoveis/${id}`), "Imóvel removido");

  const abrirNovo = () => {
    setForm(FORM_VAZIO);
    setSelecionado(null);
    setModal("novo");
  };

  const abrirEditar = (imovel: Imovel) => {
    setSelecionado(imovel);
    setForm({
      cliente_id: imovel.cliente_id ?? "",
      codigo: imovel.codigo ?? "",
      endereco: imovel.endereco,
      condominio: imovel.condominio ?? "",
      cidade: imovel.cidade ?? "",
      estado: imovel.estado ?? "",
      tipo: (imovel.tipo as string) ?? "apartamento",
      padrao: (imovel.padrao as string) ?? "medio",
      area: imovel.area != null ? String(imovel.area) : "",
      dormitorios: String(imovel.dormitorios ?? 0),
      banheiros: String(imovel.banheiros ?? 0),
      vagas: String(imovel.vagas ?? 0),
      valor: imovel.valor != null ? String(imovel.valor) : "",
      maps_url: imovel.maps_url ?? "",
      observacoes: imovel.observacoes ?? "",
    });
    setModal("editar");
  };

  const salvar = async () => {
    const body: any = {
      cliente_id: form.cliente_id || null,
      endereco: form.endereco,
      condominio: form.condominio || null,
      cidade: form.cidade || null,
      estado: form.estado || null,
      tipo: form.tipo,
      padrao: form.padrao,
      area: form.area ? Number(form.area) : null,
      dormitorios: Number(form.dormitorios) || 0,
      banheiros: Number(form.banheiros) || 0,
      vagas: Number(form.vagas) || 0,
      valor: form.valor ? Number(form.valor) : null,
      maps_url: form.maps_url || null,
      observacoes: form.observacoes || null,
    };
    // Código em branco: o backend gera. Só mando quando o usuário digitou.
    if (form.codigo) body.codigo = form.codigo;

    if (modal === "novo") await criar.mutateAsync(body);
    else if (selecionado) await editar.mutateAsync({ id: selecionado.id, ...body });
    setModal(null);
  };

  const filtrados = (imoveis ?? []).filter((i) => {
    if (filtroTipo && i.tipo !== filtroTipo) return false;
    if (!busca) return true;
    const alvo = `${i.codigo} ${i.endereco} ${i.condominio ?? ""} ${i.cidade ?? ""}`.toLowerCase();
    return alvo.includes(busca.toLowerCase());
  });

  if (isLoading) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  return (
    <div>
      <PageHeader
        title="Cadastro de imóveis"
        description="Portfólio de propriedades captadas."
        action={
          <Button onClick={abrirNovo}>
            <Plus className="h-4 w-4" /> Novo imóvel
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          className="max-w-xs"
          placeholder="Buscar por código, endereço ou cidade…"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <Select className="max-w-[12rem]" value={filtroTipo} onChange={(e) => setFiltroTipo(e.target.value)}>
          <option value="">Todos os tipos</option>
          {TIPOS_IMOVEL.map((t) => (
            <option key={t} value={t}>
              {LABEL_TIPO_IMOVEL[t]}
            </option>
          ))}
        </Select>
      </div>

      {filtrados.length === 0 ? (
        <EmptyState>Nenhum imóvel encontrado.</EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtrados.map((imovel) => (
            <Card key={imovel.id}>
              <div className="mb-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs text-muted-foreground">{imovel.codigo}</div>
                  <div className="mt-0.5 font-display text-lg">
                    {LABEL_TIPO_IMOVEL[imovel.tipo as string] ?? imovel.tipo}
                  </div>
                  <div className="truncate text-sm text-muted-foreground">
                    {imovel.endereco}
                    {imovel.cidade ? `, ${imovel.cidade}` : ""}
                  </div>
                </div>
                <Badge className="border-primary/20 bg-primary/10 text-primary">
                  {LABEL_PADRAO_IMOVEL[imovel.padrao as string] ?? imovel.padrao}
                </Badge>
              </div>

              <div className="grid grid-cols-4 gap-2 border-y border-border py-3 text-xs text-muted-foreground">
                <Ficha icone={<Ruler className="h-3.5 w-3.5" />} valor={imovel.area ? `${imovel.area}m²` : "—"} />
                <Ficha icone={<BedDouble className="h-3.5 w-3.5" />} valor={String(imovel.dormitorios)} />
                <Ficha icone={<Bath className="h-3.5 w-3.5" />} valor={String(imovel.banheiros)} />
                <Ficha icone={<Car className="h-3.5 w-3.5" />} valor={String(imovel.vagas)} />
              </div>

              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="truncate text-xs text-muted-foreground">
                  {imovel.cliente_id ? nomeCliente[imovel.cliente_id] ?? "—" : "Sem cliente"}
                </span>
                <span className="font-display text-lg text-primary">
                  {imovel.valor != null ? fmtMoeda(imovel.valor) : "—"}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
                {imovel.maps_url ? (
                  <a
                    href={imovel.maps_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                  >
                    <MapPin className="h-3.5 w-3.5" /> Ver no mapa
                  </a>
                ) : (
                  <span />
                )}
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" title="Editar" onClick={() => abrirEditar(imovel)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <BotaoExcluir
                    confirmando={confirmando === imovel.id}
                    onPedirConfirmacao={() => setConfirmando(imovel.id)}
                    onConfirmar={() => {
                      excluir.mutate(imovel.id);
                      setConfirmando(null);
                    }}
                  />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === "novo" ? "Novo imóvel" : `Editar ${selecionado?.codigo ?? ""}`}
        wide
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Endereço *">
              <Input value={form.endereco} onChange={(e) => set("endereco", e.target.value)} />
            </Field>
          </div>
          <Field label="Código (em branco = gerado)">
            <Input value={form.codigo} onChange={(e) => set("codigo", e.target.value)} />
          </Field>
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
          <Field label="Condomínio">
            <Input value={form.condominio} onChange={(e) => set("condominio", e.target.value)} />
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
          <Field label="Tipo">
            <Select value={form.tipo} onChange={(e) => set("tipo", e.target.value)}>
              {TIPOS_IMOVEL.map((t) => (
                <option key={t} value={t}>
                  {LABEL_TIPO_IMOVEL[t]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Padrão">
            <Select value={form.padrao} onChange={(e) => set("padrao", e.target.value)}>
              {PADROES_IMOVEL.map((p) => (
                <option key={p} value={p}>
                  {LABEL_PADRAO_IMOVEL[p]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Área (m²)">
            <Input type="number" min={0} value={form.area} onChange={(e) => set("area", e.target.value)} />
          </Field>
          <Field label="Dormitórios">
            <Input
              type="number"
              min={0}
              value={form.dormitorios}
              onChange={(e) => set("dormitorios", e.target.value)}
            />
          </Field>
          <Field label="Banheiros">
            <Input
              type="number"
              min={0}
              value={form.banheiros}
              onChange={(e) => set("banheiros", e.target.value)}
            />
          </Field>
          <Field label="Vagas">
            <Input type="number" min={0} value={form.vagas} onChange={(e) => set("vagas", e.target.value)} />
          </Field>
          <Field label="Valor (R$)">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.valor}
              onChange={(e) => set("valor", e.target.value)}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Link do Google Maps">
              <Input value={form.maps_url} onChange={(e) => set("maps_url", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Observações">
              <Textarea value={form.observacoes} onChange={(e) => set("observacoes", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Button
              className="w-full"
              onClick={salvar}
              disabled={!form.endereco}
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

function Ficha({ icone, valor }: { icone: React.ReactNode; valor: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      {icone}
      {valor}
    </div>
  );
}
