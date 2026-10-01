/**
 * ProprietariosSection — imóveis a person OWNS (CONTRACT §4.2): "Imóveis que
 * possui" on the comprador page, "Imóveis à venda" on the vendedor page.
 *
 * Manual rows can be added (live código search) and removed; rows derived from
 * a matrícula/negociação are read-only — the server answers 409
 * `PROPRIEDADE_DERIVADA` and the button is not offered for them.
 */
import { useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usePropriedadeMutations, usePropriedades } from "@/hooks/usePropriedades";
import type { ImovelResumo } from "@/types/interesses";

import { AdicionarInteresseDialog } from "./AdicionarInteresseDialog";
import { ImovelLinhaInfo } from "./ImovelLinhaInfo";

const ORIGEM_LABEL: Record<string, string> = {
  manual: "Manual",
  matricula: "Matrícula",
  atendimento: "Atendimento",
};

function mensagemDe(err: unknown, fallback: string) {
  return err instanceof Error && err.message ? err.message : fallback;
}

export interface ProprietariosSectionProps {
  clienteId: string;
  titulo: string;
}

export function ProprietariosSection({ clienteId, titulo }: ProprietariosSectionProps) {
  const propriedades = usePropriedades(clienteId);
  const { add, remove } = usePropriedadeMutations(clienteId);
  const [adicionando, setAdicionando] = useState(false);

  const items = propriedades.data?.items ?? [];
  const showSkeleton = propriedades.isPending && !propriedades.data;
  const isRefreshing = propriedades.isFetching && !!propriedades.data;

  function adicionar(imovel: ImovelResumo) {
    add.mutate(imovel.codigo, {
      onSuccess: () => {
        toast.success(`${imovel.codigo} registrado como propriedade.`);
        setAdicionando(false);
      },
      onError: (err) => toast.error(mensagemDe(err, "Não foi possível registrar a propriedade.")),
    });
  }

  return (
    <section data-testid="propriedades-section" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold">{titulo}</h3>
          {isRefreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="propriedades-refreshing"
            />
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setAdicionando(true)}
          data-testid="propriedade-adicionar"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Adicionar imóvel
        </Button>
      </div>

      {showSkeleton ? (
        <div className="space-y-2" data-testid="propriedades-loading">
          <div className="h-16 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : propriedades.isError && !propriedades.data ? (
        <p className="text-sm text-destructive" data-testid="propriedades-erro">
          Não foi possível carregar os imóveis.
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="propriedades-vazio">
          Nenhum imóvel registrado para esta pessoa.
        </p>
      ) : (
        <ul className="divide-y rounded-lg border" data-testid="propriedades-lista">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-3 px-3 py-2"
              data-testid={`propriedade-${item.codigo}`}
            >
              <ImovelLinhaInfo
                imovel={item.imovel}
                extra={
                  <Badge variant="secondary" className="mt-1 text-[10px]">
                    {ORIGEM_LABEL[item.origem] ?? item.origem}
                  </Badge>
                }
              />
              {item.origem === "manual" && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() =>
                    remove.mutate(item.id, {
                      onError: (err) =>
                        toast.error(mensagemDe(err, "Não foi possível remover a propriedade.")),
                    })
                  }
                  aria-label={`Remover ${item.codigo} das propriedades`}
                  data-testid={`propriedade-remover-${item.codigo}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <AdicionarInteresseDialog
        open={adicionando}
        onOpenChange={setAdicionando}
        onSelecionar={adicionar}
        jaNaLista={items.map((i) => i.codigo)}
        titulo="Adicionar imóvel"
        descricao="Digite o código do imóvel que esta pessoa possui. Clique para registrar."
      />
    </section>
  );
}
