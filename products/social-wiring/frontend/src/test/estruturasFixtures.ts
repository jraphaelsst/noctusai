/**
 * Synthetic fixtures for the Estruturas UI, typed against estruturas-contract §11.1 so a contract change
 * breaks the compile here first. NO vendor text: every sentence is invented.
 */
import type {
  Bloco,
  EstruturaDetalhe,
  EstruturaResumo,
  ImportacaoRelatorio,
  TipoBloco,
} from "@/types/estruturas";

export const perfilRef = { id: "p1", handle: "criador.exemplo", nome: "Criador Exemplo", foto_url: null };

export const TIPOS: TipoBloco[] = [
  { id: "t1", nome: "Headline", ordem: 1, tempo_tipico: "0–3s", instrucao_referencia: "Abra com a promessa.", ativo: true },
  { id: "t2", nome: "Revelação", ordem: 2, tempo_tipico: null, instrucao_referencia: "Entregue o segredo.", ativo: true },
  { id: "t3", nome: "CTA Salvar", ordem: 3, tempo_tipico: null, instrucao_referencia: "Peça para salvar.", ativo: true },
  { id: "t4", nome: "Outro", ordem: 4, tempo_tipico: null, instrucao_referencia: "Qualquer bloco fora do catálogo.", ativo: true },
  { id: "t9", nome: "Tipo antigo", ordem: 5, tempo_tipico: null, instrucao_referencia: "Descontinuado.", ativo: false },
];

export const bloco = (over: Partial<Bloco> = {}): Bloco => ({
  id: "b1",
  ordem: 1,
  nome: "Gancho inicial",
  tipo: { id: "t1", nome: "Headline" },
  tempo: "0–3s",
  instrucao: "Fale o problema em uma frase.",
  nota: null,
  repeticoes: 1,
  ...over,
});

export const resumo = (over: Partial<EstruturaResumo> = {}): EstruturaResumo => ({
  id: "e1",
  codigo: 101,
  perfil: perfilRef,
  formula_headline: "Como [autoridade teórica] resolve [problema]",
  formato: "reels",
  objetivos: ["autoridade"],
  blocos_total: 2,
  viral: null,
  status: "ativa",
  updated_at: "2026-11-10T12:00:00Z",
  ...over,
});

/** The ADMIN view of a detail (carries provenance); `membro()` strips it the way the server does. */
export const detalheAdmin = (over: Partial<EstruturaDetalhe> = {}): EstruturaDetalhe => ({
  ...resumo({ pendente_revisao: true }),
  versao: 3,
  blocos: [
    bloco({ proveniencia: { nome: "fonte", tipo: "referencia", tempo: "fonte", instrucao: "ia_sugerido" } }),
    bloco({
      id: "b2",
      ordem: 2,
      nome: "Chamada final",
      tipo: { id: "t3", nome: "CTA Salvar" },
      tempo: "slide 5",
      instrucao: null,
      nota: "O vídeo original fecha com uma pergunta.",
      repeticoes: 2,
      proveniencia: { nome: "admin", tipo: "admin", tempo: "admin", instrucao: "admin" },
    }),
  ],
  origem: "import_corestudio",
  ref_externa: "123456",
  referencia_rotulo: "referencia-sintetica",
  formula_herdada_de: null,
  proveniencia: { formula_headline: "referencia", formato: "fonte", objetivos: "admin" },
  ...over,
});

/** What an org member receives: no provenance, no admin extras, no `pendente_revisao`. */
export function membro(d: EstruturaDetalhe): EstruturaDetalhe {
  const { origem: _o, ref_externa: _r, referencia_rotulo: _rr, formula_herdada_de: _h, proveniencia: _p, pendente_revisao: _pr, ...base } = d;
  return { ...base, blocos: d.blocos.map(({ proveniencia: _bp, ...b }) => b) };
}

export const importacao = (over: Partial<ImportacaoRelatorio> = {}): ImportacaoRelatorio => ({
  id: "i1",
  fonte: "referencia",
  status: "concluida",
  dry_run: false,
  arquivo_sha256: "abcdef0123456789abcdef0123456789",
  linhas_total: 10,
  perfis_criados: 2,
  perfis_mesclados: 1,
  estruturas_criadas: 7,
  estruturas_atualizadas: 1,
  estruturas_inalteradas: 1,
  estruturas_ignoradas: 1,
  ignoradas_motivos: { handle_invalido: 1 },
  blocos_criados: 40,
  campos_nao_importados: ["nota_extra"],
  erro: null,
  created_at: "2026-11-15T10:00:00Z",
  finished_at: "2026-11-15T10:01:00Z",
  ...over,
});
