import { CategoriaMeta } from "@/types";

// Ordem das categorias conforme solicitado
export const categoriaOrdem: CategoriaMeta[] = [
  'captacao_imoveis',
  'captacao_compradores',
  'atualizacao_imoveis',
  'visitas',
  'propostas',
  'fechamento',
  'outro',
];

// Categorias disponíveis para seleção
export const categoriasDisponiveis: CategoriaMeta[] = [
  'captacao_imoveis',
  'captacao_compradores',
  'atualizacao_imoveis',
  'visitas',
  'propostas',
  'fechamento',
];

// Categorias para configuração (excluindo "outro")
export const categoriasConfig: CategoriaMeta[] = [
  'captacao_imoveis',
  'captacao_compradores',
  'atualizacao_imoveis',
  'visitas',
  'propostas',
  'fechamento',
];

export const categoriaLabels: Record<CategoriaMeta, string> = {
  captacao: "Captação",
  captacao_imoveis: "Captação de Imóveis",
  captacao_compradores: "Captação de Compradores",
  atualizacao_imoveis: "Atualização de Imóveis",
  visitas: "Visita",
  propostas: "Proposta",
  fechamento: "Fechamento",
  contatos: "Contatos", // mantido para compatibilidade
  outro: "Outro",
};

export const getDisplayCategoria = (meta: { categoria: CategoriaMeta; categoria_custom?: string }): string => {
  if (meta.categoria === 'outro' && meta.categoria_custom) {
    return meta.categoria_custom;
  }
  return categoriaLabels[meta.categoria];
};

// Ordem de prioridade das categorias para ordenação
const categoriaOrdemMap: Record<CategoriaMeta, number> = {
  atualizacao_imoveis: 0,
  captacao_imoveis: 1,
  captacao_compradores: 2,
  visitas: 3,
  propostas: 4,
  fechamento: 5,
  captacao: 6,
  contatos: 7,
  outro: 8,
};

// Função de ordenação de metas
export const sortMetasByCategoria = <T extends { categoria: CategoriaMeta; data_prazo: string; created_at: string }>(
  metas: T[]
): T[] => {
  return [...metas].sort((a, b) => {
    // Primeira camada: ordenar por categoria
    const categoriaOrder = (categoriaOrdemMap[a.categoria] ?? 999) - (categoriaOrdemMap[b.categoria] ?? 999);
    if (categoriaOrder !== 0) return categoriaOrder;

    // Segunda camada: se não forem do mesmo dia, ordenar por data de criação (mais antiga primeiro)
    const sameDay = a.data_prazo === b.data_prazo;
    if (!sameDay) {
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    }

    // Mesma categoria e mesmo dia: mantém ordem original (estável)
    return 0;
  });
};
