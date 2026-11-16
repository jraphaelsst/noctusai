import type { EstruturaOrigemCard, EstruturaUso, HeadlineRoteiroItem } from "@/types/estruturas";

export const uso = (over: Partial<EstruturaUso> = {}): EstruturaUso => ({
  id: "e1",
  codigo: 101,
  perfil: { id: "p1", handle: "criador.exemplo", nome: "Criador Exemplo" },
  formula_trecho: "Como [autoridade] resolve [problema]",
  papel: "principal",
  blocos: [],
  ...over,
});

export const itemHR = (over: Partial<HeadlineRoteiroItem> = {}): HeadlineRoteiroItem => ({
  headline: { id: "h1", texto: "Headline de teste", favorita: false, created_at: "2026-11-10T12:00:00Z", acima_recomendado: false },
  headline_texto: "Headline de teste",
  roteiro: { id: "r1", nome: "Roteiro 1", status: "completo", formato: "carrossel", duracao: "auto", ordem_cta: "cta_inicio", versao: 2, aprovacao: null },
  estruturas: [uso()],
  conversa: { id: "c1", titulo: "Conversa A" },
  post: null,
  created_at: "2026-11-10T12:00:00Z",
  ...over,
});

export const origemCard = (over: Partial<EstruturaOrigemCard> = {}): EstruturaOrigemCard => ({
  headline: { id: "h1", texto: "Headline de teste" },
  roteiro: { id: "r1", nome: "Roteiro 1", status: "completo", formato: "stories", duracao: "2", ordem_cta: "cta_final", versao: 1 },
  estruturas: [uso()],
  formato: "stories",
  legenda: { texto: "Legenda IA", origem: "ia" },
  conversa: null,
  ...over,
});
