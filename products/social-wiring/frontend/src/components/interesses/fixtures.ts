/** Contract-shaped fixtures (CONTRACT §0.1 / §4.1) shared by this slice's tests. */
import type { ImovelResumo, InteresseItem } from "@/types/interesses";

export function imovelResumo(codigo: string, over: Partial<ImovelResumo> = {}): ImovelResumo {
  return {
    codigo,
    titulo: `Apartamento ${codigo}`,
    empreendimento: "Edifício Aurora",
    logradouro: "Rua das Flores",
    numero: "10",
    complemento: "apto 52",
    bairro: "Centro",
    cidade: "Florianópolis",
    uf: "SC",
    cep: null,
    foto_destaque: `https://img.test/${codigo}.jpg`,
    captacao: null,
    corretores: [],
    ativo_no_vista: true,
    fonte: "imoveis",
    endereco: "Rua das Flores, 10 — Centro, Florianópolis/SC",
    valor: 850000,
    valor_tipo: "venda",
    ...over,
  };
}

export function interesse(codigo: string, over: Partial<InteresseItem> = {}): InteresseItem {
  return {
    id: `int-${codigo}`,
    codigo,
    origem: "lead",
    created_at: "2026-09-01T10:00:00Z",
    created_by: null,
    lead_id: null,
    meta_ads_lead_id: null,
    imovel: imovelResumo(codigo),
    ...over,
  };
}
