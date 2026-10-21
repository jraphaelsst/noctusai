/**
 * CEP lookup for the address form — `GET /api/card-hub/cep/{cep}` (a thin
 * proxy over the seed's ViaCEP/BrasilAPI `CepLookupAdapter`).
 *
 * Advisory enrichment, never a precondition: an unresolved CEP (404), a
 * network failure or a malformed value all return `null` and the operator
 * simply types the address by hand.
 */
import { api } from "@noctusai/seed/infra";

export interface EnderecoPorCep {
  logradouro: string | null;
  bairro: string | null;
  cidade: string | null;
  uf: string | null;
}

export type BuscarCep = (cep: string) => Promise<EnderecoPorCep | null>;

/** The 8 digits of a CEP, or `null` when the value is not a complete CEP. */
export function cepOitoDigitos(valor: string | null | undefined): string | null {
  const d = (valor ?? "").replace(/\D/g, "");
  return d.length === 8 ? d : null;
}

export const consultarCep: BuscarCep = async (cep) => {
  const d = cepOitoDigitos(cep);
  if (!d) return null;
  try {
    return await api.get<EnderecoPorCep>(`/api/card-hub/cep/${d}`);
  } catch {
    // Deliberate, not silent: the lookup is advisory enrichment (see header) — the
    // operator's fallback is typing the address, which the form always allows.
    return null;
  }
};

const CAMPOS: ReadonlyArray<[keyof EnderecoPorCep, string]> = [
  ["logradouro", "endereco_logradouro"],
  ["bairro", "endereco_bairro"],
  ["cidade", "endereco_cidade"],
  ["uf", "endereco_uf"],
];

/** Fills ONLY the empty address fields of `atual` from `endereco`; whatever the operator typed wins. */
export function preencherEnderecoVazio<T extends object>(
  atual: T,
  endereco: EnderecoPorCep,
): T {
  const out = { ...atual } as Record<string, unknown>;
  for (const [de, para] of CAMPOS) {
    const novo = endereco[de];
    const corrente = out[para];
    const vazio = corrente == null || String(corrente).trim() === "";
    if (vazio && novo) out[para] = de === "uf" ? novo.toUpperCase() : novo;
  }
  return out as T;
}
