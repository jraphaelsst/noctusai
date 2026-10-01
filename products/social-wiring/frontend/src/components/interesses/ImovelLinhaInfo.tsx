/**
 * ImovelLinhaInfo — the shared "row face" of an imóvel in every list this
 * slice renders (interesses, propriedades, typeahead hits, similares):
 * first photo thumb, código, endereço + complemento, valor R$.
 *
 * One component so the four lists can never drift on how a property reads.
 * Presentational only.
 */
import { ImageOff } from "lucide-react";
import type { ReactNode } from "react";

import { formatValor } from "@/hooks/useImoveis";
import type { ImovelResumo } from "@/types/interesses";

/** `endereco` (CONTRACT §0.1) + `complemento`; falls back to the raw columns
 *  when the backend has not shipped the derived key yet. */
export function enderecoComComplemento(imovel: ImovelResumo): string | null {
  const base =
    imovel.endereco ??
    ([
      [imovel.logradouro, imovel.numero].filter(Boolean).join(", "),
      imovel.bairro,
      [imovel.cidade, imovel.uf].filter(Boolean).join("/"),
    ]
      .filter(Boolean)
      .join(" — ") ||
      null);
  const compl = imovel.complemento?.trim();
  if (base && compl) return `${base} · ${compl}`;
  return base ?? compl ?? null;
}

/** `valor` (venda, else locação) with a tipo hint; "—" when unknown. */
export function valorDoImovel(imovel: ImovelResumo): string {
  const v = imovel.valor ?? imovel.valor_venda ?? imovel.valor_locacao ?? null;
  const texto = formatValor(v);
  return v !== null && imovel.valor_tipo === "locacao" ? `${texto}/mês` : texto;
}

export function ImovelThumb({ imovel }: { imovel: ImovelResumo }) {
  return imovel.foto_destaque ? (
    <img
      src={imovel.foto_destaque}
      alt=""
      loading="lazy"
      className="h-12 w-16 shrink-0 rounded object-cover"
      data-testid="imovel-thumb"
    />
  ) : (
    <div
      className="flex h-12 w-16 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground"
      data-testid="imovel-thumb-vazio"
    >
      <ImageOff className="h-4 w-4" aria-hidden />
    </div>
  );
}

export function ImovelLinhaInfo({
  imovel,
  extra,
}: {
  imovel: ImovelResumo;
  /** Extra line under the address (origem, score chips…). */
  extra?: ReactNode;
}) {
  const endereco = enderecoComComplemento(imovel);
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <ImovelThumb imovel={imovel} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm font-semibold" data-testid="imovel-codigo">
            {imovel.codigo}
          </span>
          <span className="text-sm font-medium text-foreground/80" data-testid="imovel-valor">
            {valorDoImovel(imovel)}
          </span>
        </div>
        <p className="truncate text-xs text-muted-foreground" data-testid="imovel-endereco">
          {endereco ?? "Endereço não informado"}
        </p>
        {extra}
      </div>
    </div>
  );
}
