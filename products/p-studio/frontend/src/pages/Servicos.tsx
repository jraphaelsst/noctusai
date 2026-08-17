import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { useApiMutation, useServicos } from "@/hooks/useApi";
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
import { CATEGORIAS_SERVICO } from "@/lib/status";
import { fmtMoeda } from "@/lib/utils";
import type { Servico } from "@/types";

const FORM_VAZIO = { nome: "", categoria: "Fotografia", preco: "0", prazo_dias: "3", descricao: "" };

export default function Servicos() {
  const [incluirInativos, setIncluirInativos] = useState(false);
  const { data: servicos, isLoading, error } = useServicos(incluirInativos);

  const [modal, setModal] = useState<"novo" | "editar" | null>(null);
  const [selecionado, setSelecionado] = useState<Servico | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [confirmando, setConfirmando] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const criar = useApiMutation(["servicos"], (body: any) => api.post("/api/servicos", body), "Serviço cadastrado");
  const editar = useApiMutation(
    ["servicos", "negocios"],
    ({ id, ...body }: any) => api.patch(`/api/servicos/${id}`, body),
    "Serviço atualizado"
  );
  const excluir = useApiMutation(["servicos"], (id: string) => api.del(`/api/servicos/${id}`), "Serviço removido");

  const abrirNovo = () => {
    setForm(FORM_VAZIO);
    setSelecionado(null);
    setModal("novo");
  };

  const abrirEditar = (servico: Servico) => {
    setSelecionado(servico);
    setForm({
      nome: servico.nome,
      categoria: servico.categoria ?? "Outro",
      preco: String(servico.preco ?? 0),
      prazo_dias: String(servico.prazo_dias ?? 3),
      descricao: servico.descricao ?? "",
    });
    setModal("editar");
  };

  const salvar = async () => {
    const body = {
      nome: form.nome,
      categoria: form.categoria || null,
      preco: Number(form.preco) || 0,
      prazo_dias: Number(form.prazo_dias) || 0,
      descricao: form.descricao || null,
    };
    if (modal === "novo") await criar.mutateAsync(body);
    else if (selecionado) await editar.mutateAsync({ id: selecionado.id, ...body });
    setModal(null);
  };

  const alternarAtivo = (servico: Servico) =>
    editar.mutate({ id: servico.id, ativo: !servico.ativo });

  if (isLoading) return <Spinner />;
  if (error) return <ErroBox erro={error} />;

  return (
    <div>
      <PageHeader
        title="Serviços contratados"
        description="Catálogo do estúdio — preço e prazo de entrega de cada item."
        action={
          <div className="flex items-center gap-3">
            <Checkbox
              checked={incluirInativos}
              onChange={setIncluirInativos}
              label={<span className="text-xs text-muted-foreground">Mostrar inativos</span>}
            />
            <Button onClick={abrirNovo}>
              <Plus className="h-4 w-4" /> Novo serviço
            </Button>
          </div>
        }
      />

      {(servicos ?? []).length === 0 ? (
        <EmptyState>Nenhum serviço no catálogo.</EmptyState>
      ) : (
        <Table>
          <THead>
            <tr>
              <Th>Serviço</Th>
              <Th>Categoria</Th>
              <Th>Preço</Th>
              <Th>Prazo</Th>
              <Th>Status</Th>
              <Th />
            </tr>
          </THead>
          <TBody>
            {(servicos ?? []).map((servico) => (
              <tr key={servico.id} className="hover:bg-muted/30">
                <Td className="font-medium">
                  {servico.nome}
                  {servico.descricao && (
                    <div className="text-xs font-normal text-muted-foreground">{servico.descricao}</div>
                  )}
                </Td>
                <Td className="text-muted-foreground">{servico.categoria ?? "—"}</Td>
                <Td>{fmtMoeda(servico.preco)}</Td>
                <Td className="text-muted-foreground">{servico.prazo_dias} dia(s)</Td>
                <Td>
                  <button onClick={() => alternarAtivo(servico)} title="Alternar disponibilidade">
                    <Badge
                      className={
                        servico.ativo
                          ? "border-status-delivered/30 bg-status-delivered/15 text-status-delivered"
                          : undefined
                      }
                    >
                      {servico.ativo ? "ativo" : "inativo"}
                    </Badge>
                  </button>
                </Td>
                <Td>
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="icon" title="Editar" onClick={() => abrirEditar(servico)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <BotaoExcluir
                      confirmando={confirmando === servico.id}
                      onPedirConfirmacao={() => setConfirmando(servico.id)}
                      onConfirmar={() => {
                        excluir.mutate(servico.id);
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
        title={modal === "novo" ? "Novo serviço" : `Editar ${selecionado?.nome ?? ""}`}
      >
        <div className="space-y-3">
          <Field label="Nome *">
            <Input value={form.nome} onChange={(e) => set("nome", e.target.value)} />
          </Field>
          <Field label="Categoria">
            <Select value={form.categoria} onChange={(e) => set("categoria", e.target.value)}>
              {CATEGORIAS_SERVICO.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Preço (R$)">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={form.preco}
                onChange={(e) => set("preco", e.target.value)}
              />
            </Field>
            <Field label="Prazo (dias)">
              <Input
                type="number"
                min={0}
                value={form.prazo_dias}
                onChange={(e) => set("prazo_dias", e.target.value)}
              />
            </Field>
          </div>
          <Field label="Descrição">
            <Textarea value={form.descricao} onChange={(e) => set("descricao", e.target.value)} />
          </Field>
          <Button
            className="w-full"
            onClick={salvar}
            disabled={!form.nome}
            loading={criar.isPending || editar.isPending}
          >
            Salvar
          </Button>
        </div>
      </Modal>
    </div>
  );
}
