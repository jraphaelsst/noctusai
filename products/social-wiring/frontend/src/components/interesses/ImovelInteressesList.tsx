/**
 * ImovelInteressesList — a cliente's interest list, and the entry to the
 * roteiro flow (CONTRACT §3.5 / §6). Mounted on the person page AND on the
 * card's Roteiros tab (via `RoteirosSection`).
 *
 * Flow: tick the rows to visit that day → "Gerar roteiro" (disabled with none
 * ticked) → ordering dialog (drag-and-drop + required `data_visita`) →
 * "Confirmar ordem do roteiro" → `POST …/roteiros` with the códigos in the
 * dialog's final order → the PDF is fetched right away.
 *
 * Rows: first photo, código, endereço + complemento, valor R$, origem; a
 * checkbox on every row; remove-interesse action. "Adicionar interesse" opens
 * the live typeahead popup.
 *
 * Loading (lying-loading-state.md): `showSkeleton = isPending && !data`;
 * `isRefreshing = isFetching && !!data` is an indicator only — rows never
 * unmount on a refetch.
 */
import { useMemo, useState } from "react";
import { Loader2, Plus, Route, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { CriarRoteiroDialog } from "@/components/card/CriarRoteiroDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { baixarRoteiroPdf, useCriarRoteiro } from "@/hooks/useRoteiros";
import { useInteresseMutations, useInteresses } from "@/hooks/useInteresses";
import { usePessoaResumo } from "@/hooks/usePessoa";
import { avisarFunilRecusado } from "@/lib/funilAviso";
import type { Roteiro, RoteiroCreateBody } from "@/types/cardHub";
import type { InteresseItem, ImovelResumo } from "@/types/interesses";

import { AdicionarInteresseDialog } from "./AdicionarInteresseDialog";
import { ImovelLinhaInfo } from "./ImovelLinhaInfo";

const ORIGEM_LABEL: Record<string, string> = {
  lead: "Lead",
  manual: "Manual",
  campanha: "Campanha",
  roteiro: "Roteiro",
  permuta: "Permuta",
};

function mensagemDe(err: unknown, fallback: string) {
  return err instanceof Error && err.message ? err.message : fallback;
}

export interface ImovelInteressesListProps {
  clienteId: string;
  atendimentoId?: string | null;
}

export function ImovelInteressesList({ clienteId, atendimentoId }: ImovelInteressesListProps) {
  const interesses = useInteresses(clienteId);
  const { add, remove } = useInteresseMutations(clienteId);
  const { criar, isPending: criando } = useCriarRoteiro(clienteId);
  // Only needed to offer an atendimento choice when none was passed and the
  // person has several open ones (otherwise the server answers 409).
  const pessoa = usePessoaResumo(atendimentoId ? undefined : clienteId);

  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [adicionando, setAdicionando] = useState(false);
  const [ordenando, setOrdenando] = useState(false);
  const [gerandoPdf, setGerandoPdf] = useState(false);

  const items = useMemo(() => interesses.data?.items ?? [], [interesses.data]);
  const showSkeleton = interesses.isPending && !interesses.data;
  const isRefreshing = interesses.isFetching && !!interesses.data;

  // Ticks that no longer match a live row (removed / refetched away) must not
  // survive into the roteiro: derive the effective selection from `items`.
  const selecionados = useMemo(
    () => items.filter((i) => marcados.has(i.id)),
    [items, marcados],
  );

  const atendimentoOpcoes = useMemo(() => {
    if (atendimentoId) return undefined;
    const abertos = (pessoa.data?.atendimentos ?? []).filter((a) => !a.arquivado);
    return abertos.length > 1
      ? abertos.map((a) => ({ id: a.id, titulo: a.titulo ?? `Atendimento ${a.id.slice(0, 8)}` }))
      : undefined;
  }, [atendimentoId, pessoa.data]);

  function alternar(id: string, marcado: boolean) {
    setMarcados((atual) => {
      const novo = new Set(atual);
      if (marcado) novo.add(id);
      else novo.delete(id);
      return novo;
    });
  }

  function adicionar(imovel: ImovelResumo) {
    add.mutate(
      { codigo: imovel.codigo, origem: "manual" },
      {
        onSuccess: () => {
          toast.success(`Interesse em ${imovel.codigo} adicionado.`);
          setAdicionando(false);
        },
        onError: (err) => toast.error(mensagemDe(err, "Não foi possível adicionar o interesse.")),
      },
    );
  }

  function remover(item: InteresseItem) {
    remove.mutate(item.id, {
      onSuccess: () => alternar(item.id, false),
      onError: (err) => toast.error(mensagemDe(err, "Não foi possível remover o interesse.")),
    });
  }

  async function confirmarRoteiro(body: RoteiroCreateBody) {
    const comAtendimento: RoteiroCreateBody =
      atendimentoId && !body.atendimento_id ? { ...body, atendimento_id: atendimentoId } : body;
    let roteiroId: string;
    let funil: Roteiro["funil"];
    try {
      const criado = await criar(comAtendimento);
      roteiroId = criado.id;
      funil = criado.funil;
    } catch (err) {
      toast.error(mensagemDe(err, "Não foi possível criar o roteiro."));
      return;
    }
    setOrdenando(false);
    setMarcados(new Set());
    toast.success("Roteiro criado.");
    avisarFunilRecusado(funil);
    setGerandoPdf(true);
    try {
      await baixarRoteiroPdf(clienteId, roteiroId);
    } catch (err) {
      // The roteiro EXISTS — say so; it can be printed from the Roteiros tab.
      toast.error(mensagemDe(err, "O roteiro foi criado, mas o PDF não pôde ser gerado."));
    } finally {
      setGerandoPdf(false);
    }
  }

  return (
    <section data-testid="interesses-section" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold">Interesses</h3>
          {isRefreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="interesses-refreshing"
            />
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setAdicionando(true)}
            data-testid="interesse-adicionar"
          >
            <Plus className="mr-1.5 h-4 w-4" />
            Adicionar interesse
          </Button>
          <Button
            size="sm"
            onClick={() => setOrdenando(true)}
            disabled={selecionados.length < 1 || criando || gerandoPdf}
            data-testid="roteiro-gerar"
          >
            {criando || gerandoPdf ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Route className="mr-1.5 h-4 w-4" />
            )}
            Gerar roteiro{selecionados.length > 0 ? ` (${selecionados.length})` : ""}
          </Button>
        </div>
      </div>

      {showSkeleton ? (
        <div className="space-y-2" data-testid="interesses-loading">
          <div className="h-16 animate-pulse rounded-lg bg-muted" />
          <div className="h-16 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : interesses.isError && !interesses.data ? (
        <p className="text-sm text-destructive" data-testid="interesses-erro">
          Não foi possível carregar os interesses.
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="interesses-vazio">
          Nenhum interesse registrado. Use “Adicionar interesse” para incluir um imóvel.
        </p>
      ) : (
        <ul className="divide-y rounded-lg border" data-testid="interesses-lista">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-3 px-3 py-2"
              data-testid={`interesse-${item.codigo}`}
            >
              <Checkbox
                checked={marcados.has(item.id)}
                onCheckedChange={(v) => alternar(item.id, v === true)}
                aria-label={`Selecionar ${item.codigo} para o roteiro`}
                data-testid={`interesse-check-${item.codigo}`}
              />
              <ImovelLinhaInfo
                imovel={item.imovel}
                extra={
                  <Badge variant="secondary" className="mt-1 text-[10px]" data-testid="interesse-origem">
                    {ORIGEM_LABEL[item.origem] ?? item.origem}
                  </Badge>
                }
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => remover(item)}
                disabled={remove.isPending && remove.variables === item.id}
                aria-label={`Remover interesse em ${item.codigo}`}
                data-testid={`interesse-remover-${item.codigo}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <AdicionarInteresseDialog
        open={adicionando}
        onOpenChange={setAdicionando}
        onSelecionar={adicionar}
        jaNaLista={items.map((i) => i.codigo)}
      />

      {ordenando && (
        <CriarRoteiroDialog
          open
          onOpenChange={setOrdenando}
          // Fresh mount per open ⇒ `inicial` is read once, in the order the
          // rows appear in the list.
          inicial={selecionados.map((s) => s.imovel)}
          atendimentoOpcoes={atendimentoOpcoes}
          saving={criando}
          onCriar={(body) => void confirmarRoteiro(body)}
        />
      )}
    </section>
  );
}
