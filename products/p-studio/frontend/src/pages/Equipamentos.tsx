import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { useApiMutation, useEquipamentos } from "@/hooks/useApi";
import {
  Badge,
  BotaoExcluir,
  Button,
  Checkbox,
  EmptyState,
  ErroBox,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  TBody,
  THead,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { CATEGORIAS_EQUIPAMENTO, LABEL_CATEGORIA_EQUIPAMENTO } from "@/lib/status";
import { fmtMoeda } from "@/lib/utils";
import type { Equipamento } from "@/types";

const FORM_VAZIO = {
  nome: "",
  marca: "",
  modelo: "",
  numero_serie: "",
  categoria: "camera",
  valor: "0",
  quantidade: "1",
  observacoes: "",
};

export default function Equipamentos() {
  const [incluirInativos, setIncluirInativos] = useState(false);
  const { data: equipamentos, isPending, error } = useEquipamentos(incluirInativos);

  const [modal, setModal] = useState<"novo" | "editar" | null>(null);
  const [selecionado, setSelecionado] = useState<Equipamento | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const criar = useApiMutation(
    ["equipamentos"],
    (body: any) => api.post("/api/equipamentos", body),
    "Equipamento cadastrado"
  );
  // O protótipo nunca teve edição de equipamento — a tabela aceitava UPDATE, a
  // tela não emitia. Aqui existe.
  const editar = useApiMutation(
    ["equipamentos", "captacoes"],
    ({ id, ...body }: any) => api.patch(`/api/equipamentos/${id}`, body),
    "Equipamento atualizado"
  );
  const excluir = useApiMutation(
    ["equipamentos"],
    (id: string) => api.del(`/api/equipamentos/${id}`),
    "Equipamento removido"
  );

  const abrirNovo = () => {
    setForm(FORM_VAZIO);
    setSelecionado(null);
    setModal("novo");
  };

  const abrirEditar = (item: Equipamento) => {
    setSelecionado(item);
    setForm({
      nome: item.nome,
      marca: item.marca ?? "",
      modelo: item.modelo ?? "",
      numero_serie: item.numero_serie ?? "",
      categoria: (item.categoria as string) ?? "outro",
      valor: String(item.valor ?? 0),
      quantidade: String(item.quantidade ?? 1),
      observacoes: item.observacoes ?? "",
    });
    setModal("editar");
  };

  const salvar = async () => {
    const body = {
      nome: form.nome,
      marca: form.marca || null,
      modelo: form.modelo || null,
      numero_serie: form.numero_serie || null,
      categoria: form.categoria || null,
      valor: Number(form.valor) || 0,
      quantidade: Number(form.quantidade) || 1,
      observacoes: form.observacoes || null,
    };
    if (modal === "novo") await criar.mutateAsync(body);
    else if (selecionado) await editar.mutateAsync({ id: selecionado.id, ...body });
    setModal(null);
  };

  const totalPatrimonio = (equipamentos ?? []).reduce(
    (s, e) => s + (e.valor ?? 0) * (e.quantidade ?? 1),
    0
  );

  if (isPending && !equipamentos) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  return (
    <div>
      <PageHeader
        title="Equipamentos"
        description={`${equipamentos?.length ?? 0} item(ns) — patrimônio de ${fmtMoeda(totalPatrimonio)}.`}
        action={
          <div className="flex items-center gap-3">
            <Checkbox
              checked={incluirInativos}
              onChange={setIncluirInativos}
              label={<span className="text-xs text-muted-foreground">Mostrar inativos</span>}
            />
            <Button onClick={abrirNovo}>
              <Plus className="h-4 w-4" /> Novo equipamento
            </Button>
          </div>
        }
      />

      {(equipamentos ?? []).length === 0 ? (
        <EmptyState>Nenhum equipamento cadastrado.</EmptyState>
      ) : (
        <Table>
          <THead>
            <tr>
              <Th>Equipamento</Th>
              <Th>Categoria</Th>
              <Th>Nº de série</Th>
              <Th>Qtd.</Th>
              <Th>Valor</Th>
              <Th>Status</Th>
              <Th />
            </tr>
          </THead>
          <TBody>
            {(equipamentos ?? []).map((item) => (
              <tr key={item.id} className="hover:bg-muted/30">
                <Td className="font-medium">
                  {item.nome}
                  <div className="text-xs font-normal text-muted-foreground">
                    {[item.marca, item.modelo].filter(Boolean).join(" ") || "—"}
                  </div>
                </Td>
                <Td className="text-muted-foreground">
                  {LABEL_CATEGORIA_EQUIPAMENTO[item.categoria as string] ?? item.categoria ?? "—"}
                </Td>
                <Td className="text-muted-foreground">{item.numero_serie ?? "—"}</Td>
                <Td>{item.quantidade}</Td>
                <Td>{fmtMoeda(item.valor)}</Td>
                <Td>
                  <button
                    onClick={() => editar.mutate({ id: item.id, ativo: !item.ativo })}
                    title="Alternar disponibilidade"
                  >
                    <Badge
                      className={
                        item.ativo
                          ? "border-status-delivered/30 bg-status-delivered/15 text-status-delivered"
                          : undefined
                      }
                    >
                      {item.ativo ? "disponível" : "inativo"}
                    </Badge>
                  </button>
                </Td>
                <Td>
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="icon" title="Editar" onClick={() => abrirEditar(item)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <BotaoExcluir
                      confirmando={confirmando === item.id}
                      onPedirConfirmacao={() => setConfirmando(item.id)}
                      onConfirmar={() => {
                        excluir.mutate(item.id);
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

      <Modal
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === "novo" ? "Novo equipamento" : `Editar ${selecionado?.nome ?? ""}`}
        wide
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nome *">
            <Input value={form.nome} onChange={(e) => set("nome", e.target.value)} />
          </Field>
          <Field label="Categoria">
            <Select value={form.categoria} onChange={(e) => set("categoria", e.target.value)}>
              {CATEGORIAS_EQUIPAMENTO.map((c) => (
                <option key={c} value={c}>
                  {LABEL_CATEGORIA_EQUIPAMENTO[c]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Marca">
            <Input value={form.marca} onChange={(e) => set("marca", e.target.value)} />
          </Field>
          <Field label="Modelo">
            <Input value={form.modelo} onChange={(e) => set("modelo", e.target.value)} />
          </Field>
          <Field label="Número de série">
            <Input value={form.numero_serie} onChange={(e) => set("numero_serie", e.target.value)} />
          </Field>
          <Field label="Quantidade">
            <Input
              type="number"
              min={1}
              value={form.quantidade}
              onChange={(e) => set("quantidade", e.target.value)}
            />
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
