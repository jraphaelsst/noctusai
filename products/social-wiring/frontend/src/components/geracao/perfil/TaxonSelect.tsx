/**
 * Searchable checkbox list over a static taxonomy with a hard selection cap
 * (Meu Perfil: nichos / profissões, max 3). At the cap the unchecked options are
 * disabled and the CoreStudio error text is shown; the server enforces the cap too.
 */
import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Taxon } from "@/types/geracao";

interface Props {
  id: string;
  label: string;
  /** Tooltip/help text under the label. */
  ajuda: string;
  dica: string;
  erroMax: string;
  opcoes: Taxon[];
  valor: number[];
  max: number;
  onChange: (ids: number[]) => void;
}

export function TaxonSelect({ id, label, ajuda, dica, erroMax, opcoes, valor, max, onChange }: Props) {
  const [busca, setBusca] = useState("");
  const noLimite = valor.length >= max;
  const termo = busca.trim().toLowerCase();
  const visiveis = termo ? opcoes.filter((o) => o.nome.toLowerCase().includes(termo)) : opcoes;
  const nomes = new Map(opcoes.map((o) => [o.id, o.nome]));

  function alternar(taxonId: number, marcado: boolean) {
    if (marcado) {
      if (!noLimite) onChange([...valor, taxonId]);
    } else {
      onChange(valor.filter((v) => v !== taxonId));
    }
  }

  return (
    <fieldset className="space-y-2" aria-labelledby={`${id}-label`}>
      <div>
        <Label id={`${id}-label`} title={ajuda}>
          {label}
        </Label>
        <p className="text-xs text-muted-foreground">{ajuda}</p>
      </div>
      {valor.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label={`${label} selecionados`}>
          {valor.map((v) => (
            <li key={v} className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs">
              {nomes.get(v) ?? `#${v}`}
            </li>
          ))}
        </ul>
      )}
      <Input
        aria-label={`Buscar ${label.toLowerCase()}`}
        placeholder="Buscar..."
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
      />
      <div className="max-h-44 space-y-1 overflow-y-auto rounded-md border p-2">
        {visiveis.length === 0 ? (
          <p className="p-1 text-sm text-muted-foreground">Nenhuma opção encontrada.</p>
        ) : (
          visiveis.map((o) => {
            const marcado = valor.includes(o.id);
            return (
              <label
                key={o.id}
                className={`flex items-center gap-2 rounded px-1.5 py-1 text-sm ${
                  !marcado && noLimite ? "opacity-50" : "cursor-pointer hover:bg-muted/50"
                }`}
              >
                <input
                  type="checkbox"
                  checked={marcado}
                  disabled={!marcado && noLimite}
                  onChange={(e) => alternar(o.id, e.target.checked)}
                />
                {o.nome}
              </label>
            );
          })
        )}
      </div>
      {noLimite ? (
        <p role="alert" className="text-xs text-destructive">
          {erroMax}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">{dica}</p>
      )}
    </fieldset>
  );
}
