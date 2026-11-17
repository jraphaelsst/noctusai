/**
 * Estrutura picker (contract §11.3 "Surface pickers"): multi-select over the platform library — search, profile
 * filter ("Perfil…"), max 3, all of one formato. ONE component for the headline forms (Me/Público, Viral, the viral
 * wizard), Roteiro Avançado and the Esteira card dialogs (which host those forms). The chat's `MencaoPicker` is the
 * fifth surface and has its own `@estrutura` tab.
 *
 * Controlled: the parent owns `value` and sends `estrutura_ids` (`idsDaSelecao`). The list is `useEstruturas`
 * (FE-1); loading is `showSkeleton` / `isRefreshing`, never `isLoading`; a failed read says so and offers a retry.
 */
import { useId, useState } from "react";
import { X } from "lucide-react";

import { ROTULO_FORMATO } from "@/components/geracao/biblioteca/estruturas/rotulos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useEstruturas } from "@/hooks/geracao/useEstruturas";
import { usePerfisMonitorados } from "@/hooks/geracao/useBiblioteca";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { cn } from "@/lib/utils";
import {
  ESTRUTURAS_MAX,
  alternarEstrutura,
  formatoDaSelecao,
  motivoDeBloqueio,
  paraEscolhida,
  type EstruturaEscolhida,
} from "./selecao";

interface Props {
  marcaId: string | null;
  value: EstruturaEscolhida[];
  onChange: (next: EstruturaEscolhida[]) => void;
  disabled?: boolean;
  /** Selection cap (default 3; the viral wizard takes exactly one). */
  max?: number;
  className?: string;
}

const MOTIVO = (max: number): Record<"limite" | "formato", string> => ({
  limite: max === 1 ? "Escolha apenas uma estrutura." : `Máximo de ${max} estruturas.`,
  formato: "Formato diferente das já escolhidas.",
});

export function EstruturaPicker({ marcaId, value, onChange, disabled, max = ESTRUTURAS_MAX, className }: Props) {
  const uid = useId();
  const [busca, setBusca] = useState("");
  const [perfilId, setPerfilId] = useState("");
  // The library can hold hundreds of profiles and the list endpoint caps at 50: the profile select is searchable.
  const [buscaPerfil, setBuscaPerfil] = useState("");
  const buscaPerfilDeb = useDebouncedValue(buscaPerfil, 300);
  const buscaDeb = useDebouncedValue(busca, 300);
  const formato = formatoDaSelecao(value);

  const perfisQ = usePerfisMonitorados(buscaPerfilDeb);
  const perfis = perfisQ.data ?? [];
  const lista = useEstruturas({
    marcaId,
    q: buscaDeb,
    perfilId: perfilId || undefined,
    // Once one is picked, only its formato is on offer (DC7); the server enforces the same rule.
    formatos: formato ? [formato] : undefined,
    limit: 12,
  });
  const itens = lista.data?.items ?? [];

  return (
    <fieldset className={cn("space-y-3 rounded-md border p-3", className)} disabled={disabled} data-testid="estrutura-picker">
      <legend className="px-1 text-sm font-medium">Estruturas da biblioteca (opcional)</legend>
      <p className="text-xs text-muted-foreground">
        {max === 1 ? "Escolha uma estrutura." : `Escolha até ${max} estruturas, todas do mesmo formato.`} Sem escolha, a IA seleciona entre os perfis da sua marca.
      </p>

      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Estruturas escolhidas">
          {value.map((e, i) => (
            <li key={e.id}>
              <Badge variant="secondary" className="gap-1 pr-1">
                {i === 0 && value.length > 1 ? "Principal · " : ""}#{e.codigo} @{e.perfil.handle}
                <button
                  type="button"
                  aria-label={`Remover estrutura #${e.codigo}`}
                  className="rounded-full p-0.5 hover:bg-background/60"
                  onClick={() => onChange(value.filter((x) => x.id !== e.id))}
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </Badge>
            </li>
          ))}
          {formato && <li className="self-center text-xs text-muted-foreground">Formato: {ROTULO_FORMATO[formato]}</li>}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <Input
          aria-label="Buscar estruturas"
          placeholder="Buscar fórmula ou bloco…"
          className="min-w-48 flex-1"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <Input
          aria-label="Buscar perfil"
          placeholder="Buscar perfil…"
          className="w-40"
          value={buscaPerfil}
          onChange={(e) => setBuscaPerfil(e.target.value)}
        />
        <select
          aria-label="Perfil"
          value={perfilId}
          onChange={(e) => setPerfilId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Perfil…</option>
          {perfis.map((p) => (
            <option key={p.id} value={p.id}>
              @{p.handle}
            </option>
          ))}
        </select>
      </div>

      <div aria-busy={lista.isRefreshing} className={cn("max-h-56 overflow-y-auto", lista.isRefreshing && "opacity-70")}>
        {lista.showSkeleton ? (
          <div className="space-y-2" data-testid="estruturas-skeleton">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : lista.isError && !lista.data ? (
          <p role="alert" className="text-sm text-destructive">
            Não foi possível carregar as estruturas.{" "}
            <button type="button" className="underline" onClick={() => void lista.refetch()}>
              Tentar novamente
            </button>
          </p>
        ) : itens.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {buscaDeb || perfilId ? "Nenhuma estrutura encontrada para esse filtro." : "Nenhuma estrutura disponível na biblioteca ainda."}
          </p>
        ) : (
          <ul className="space-y-1" id={`${uid}-lista`}>
            {itens.map((e) => {
              const marcada = value.some((v) => v.id === e.id);
              const bloqueio = marcada ? null : motivoDeBloqueio(value, e, max);
              return (
                <li key={e.id}>
                  <button
                    type="button"
                    aria-pressed={marcada}
                    disabled={!!bloqueio}
                    title={bloqueio ? MOTIVO(max)[bloqueio] : undefined}
                    className={cn(
                      "w-full rounded-md border px-2 py-1.5 text-left text-sm hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50",
                      marcada && "border-primary bg-primary/5",
                    )}
                    onClick={() => onChange(alternarEstrutura(value, paraEscolhida(e), max))}
                  >
                    <span className="block truncate font-medium">{e.formula_headline}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      #{e.codigo} · @{e.perfil.handle}
                      {e.formato ? ` · ${ROTULO_FORMATO[e.formato]}` : ""}
                      {bloqueio ? ` · ${MOTIVO(max)[bloqueio]}` : ""}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {lista.data && lista.data.total > itens.length && (
        <p className="text-xs text-muted-foreground">Mostrando {itens.length} de {lista.data.total}. Refine a busca para ver outras.</p>
      )}
      {value.length > 0 && (
        <Button type="button" variant="link" className="h-auto p-0 text-xs" onClick={() => onChange([])}>
          Limpar escolha
        </Button>
      )}
    </fieldset>
  );
}
