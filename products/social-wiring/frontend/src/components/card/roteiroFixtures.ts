/**
 * Test fixtures for the roteiro lifecycle — built EXACTLY to the contract's
 * shapes (`projects/roteiro-ciclo-CONTRACT.md` §2): `Roteiro` with `status`,
 * `contagem` (the new keys) and the server-computed `permissoes`. A fixture
 * that omits a contract key would be testing a shape the server never sends.
 */
import type {
  ContagemVisitas,
  ImovelVisita,
  Roteiro,
  RoteiroPermissoes,
  Visita,
} from "@/types/cardHub";

export function imovelFx(codigo: string, over: Partial<ImovelVisita> = {}): ImovelVisita {
  return {
    codigo,
    titulo: `Apartamento ${codigo}`,
    empreendimento: "Edifício Aurora",
    logradouro: "Rua das Palmeiras",
    numero: "320",
    complemento: null,
    bairro: "Centro",
    cidade: "Florianópolis",
    uf: "SC",
    cep: "88010-000",
    foto_destaque: null,
    captacao: null,
    corretores: [{ nome: "Ana Prado", email: null }],
    ativo_no_vista: true,
    fonte: "imoveis",
    ...over,
  };
}

export function visitaFx(id: string, codigo: string, over: Partial<Visita> = {}): Visita {
  return {
    id,
    roteiro_id: "r1",
    codigo,
    ordem: 0,
    status: "pendente",
    observacao: null,
    feedback_em: null,
    created_at: "2026-11-09T12:00:00+00:00",
    realizada_em: null,
    imovel: imovelFx(codigo),
    proposta_em: null,
    proposta_por: null,
    proposta_aceita_em: null,
    proposta_aceita_por: null,
    cancelada_por: null,
    cancelada_motivo: null,
    reagendada_para_visita_id: null,
    resultado_em: null,
    resultado_por: null,
    ...over,
  };
}

/** The counts the server derives (CONTRACT §2) — computed here only so fixtures stay coherent. */
export function contagemFx(visitas: Visita[]): ContagemVisitas {
  const n = (s: Visita["status"]) => visitas.filter((v) => v.status === s).length;
  const realizadas = n("realizada");
  const canceladas = n("cancelada");
  const nao_compareceu = n("nao_compareceu");
  const reagendadas = n("reagendada");
  const pendentes = n("pendente");
  return {
    total: visitas.length,
    pendentes,
    realizadas,
    canceladas,
    nao_compareceu,
    reagendadas,
    consolidadas: realizadas,
    perdidas: canceladas + nao_compareceu,
    neutras: reagendadas + pendentes,
  };
}

export const permissoesRascunho = (over: Partial<RoteiroPermissoes> = {}): RoteiroPermissoes => ({
  editar_imoveis: true,
  gerar: true,
  motivo_gerar: null,
  baixar_pdf: false,
  reabrir: false,
  motivo_reabrir: null,
  ...over,
});

export const permissoesGerado = (over: Partial<RoteiroPermissoes> = {}): RoteiroPermissoes => ({
  editar_imoveis: false,
  gerar: false,
  motivo_gerar: null,
  baixar_pdf: true,
  reabrir: true,
  motivo_reabrir: null,
  ...over,
});

export function roteiroFx(over: Partial<Roteiro> = {}): Roteiro {
  const visitas = over.visitas ?? [visitaFx("v1", "ONE9001")];
  const gerado = over.status === "gerado";
  return {
    id: "r1",
    atendimento_id: "a1",
    titulo: "Terça de manhã",
    data_visita: "2026-11-14",
    hora_visita: null,
    created_at: "2026-11-09T12:00:00+00:00",
    updated_at: "2026-11-09T12:00:00+00:00",
    status: "rascunho",
    gerado_em: gerado ? "2026-11-12T15:42:00+00:00" : null,
    gerado_por: gerado ? "u-cindy" : null,
    reaberto_em: null,
    reaberto_por: null,
    criado_por: "u1",
    feedback_status: "pendente",
    feedback_em: null,
    visitas,
    contagem: contagemFx(visitas),
    permissoes: gerado ? permissoesGerado() : permissoesRascunho(),
    ...over,
  };
}
