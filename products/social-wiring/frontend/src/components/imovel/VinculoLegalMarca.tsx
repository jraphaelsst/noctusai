/**
 * Field marker for a linked imóvel's `GET /dados` → `vinculo_legal`
 * (CONTRACT §8.7): "do cadastro manual" when the value was filled from the
 * manual record, "em conflito — revise" (linking to `ImovelConflitosCard`,
 * `#imovel-conflitos`) when the two records disagree.
 */
import type { VinculoLegal } from "@/hooks/useImovelDados";

export type MarcaVinculo = "conflito" | "manual" | null;

function conflitoCampos(vl: VinculoLegal): string[] {
  return Array.isArray(vl.conflitos)
    ? vl.conflitos.map((c) => (typeof c === "string" ? c : (c.campo ?? "")))
    : [];
}

export function marcaDoCampo(
  vl: VinculoLegal | null | undefined,
  campo: string,
): MarcaVinculo {
  if (!vl) return null;
  if (conflitoCampos(vl).includes(campo)) return "conflito";
  const f = vl.fontes;
  if (Array.isArray(f)) return f.includes(campo) ? "manual" : null;
  if (f && typeof f === "object") {
    const origem = f[campo];
    return origem && origem === vl.manual_codigo ? "manual" : null;
  }
  return null;
}

export default function VinculoLegalMarca({
  vinculoLegal,
  campo,
}: {
  vinculoLegal: VinculoLegal | null | undefined;
  campo: string;
}) {
  const marca = marcaDoCampo(vinculoLegal, campo);
  if (!marca) return null;
  return marca === "conflito" ? (
    <a
      href="#imovel-conflitos"
      className="text-xs font-medium text-amber-700 underline dark:text-amber-300"
      data-testid={`vinculo-legal-${campo}`}
    >
      em conflito — revise
    </a>
  ) : (
    <span
      className="text-xs text-sky-800 dark:text-sky-300"
      data-testid={`vinculo-legal-${campo}`}
    >
      do cadastro manual
    </span>
  );
}
