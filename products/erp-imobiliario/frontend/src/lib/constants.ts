// Centralized status/type configuration maps for the ERP frontend.
// All labels use proper Portuguese accents.

export const PROPOSTA_STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  rascunho: { label: "Rascunho", color: "bg-gray-100 text-gray-800" },
  enviada: { label: "Enviada", color: "bg-blue-100 text-blue-800" },
  em_analise: { label: "Em Análise", color: "bg-yellow-100 text-yellow-800" },
  contraproposta: { label: "Contraproposta", color: "bg-orange-100 text-orange-800" },
  aceita: { label: "Aceita", color: "bg-green-100 text-green-800" },
  recusada: { label: "Recusada", color: "bg-red-100 text-red-800" },
  expirada: { label: "Expirada", color: "bg-gray-100 text-gray-600" },
};

export const CONTRATO_STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  rascunho: { label: "Rascunho", color: "bg-gray-100 text-gray-800" },
  ativo: { label: "Ativo", color: "bg-green-100 text-green-800" },
  suspenso: { label: "Suspenso", color: "bg-yellow-100 text-yellow-800" },
  cancelado: { label: "Cancelado", color: "bg-red-100 text-red-800" },
  concluido: { label: "Concluído", color: "bg-blue-100 text-blue-800" },
  distratado: { label: "Distratado", color: "bg-red-100 text-red-800" },
};

export const CONTRATO_TIPO_CONFIG: Record<string, { label: string }> = {
  venda: { label: "Venda" },
  locacao: { label: "Locação" },
  administracao: { label: "Administração" },
  permuta: { label: "Permuta" },
};

export const VISTORIA_STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  agendada: { label: "Agendada", color: "bg-blue-100 text-blue-800" },
  em_andamento: { label: "Em Andamento", color: "bg-yellow-100 text-yellow-800" },
  concluida: { label: "Concluída", color: "bg-green-100 text-green-800" },
  cancelada: { label: "Cancelada", color: "bg-red-100 text-red-800" },
};

export const VISTORIA_TIPO_CONFIG: Record<string, { label: string }> = {
  entrada: { label: "Entrada" },
  saida: { label: "Saída" },
  periodica: { label: "Periódica" },
  pre_venda: { label: "Pré-venda" },
};

export const MANUTENCAO_STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  pendente: { label: "Pendente", color: "bg-yellow-100 text-yellow-800" },
  em_andamento: { label: "Em Andamento", color: "bg-blue-100 text-blue-800" },
  concluido: { label: "Concluído", color: "bg-green-100 text-green-800" },
  cancelado: { label: "Cancelado", color: "bg-red-100 text-red-800" },
};

export const AGENDA_TIPO_CONFIG: Record<string, { label: string }> = {
  visita: { label: "Visita" },
  reuniao: { label: "Reunião" },
  ligacao: { label: "Ligação" },
  vistoria: { label: "Vistoria" },
  assinatura: { label: "Assinatura" },
  tarefa: { label: "Tarefa" },
  lembrete: { label: "Lembrete" },
  outro: { label: "Outro" },
};

export const GAMIFICACAO_PERIODO_CONFIG: Record<string, { label: string }> = {
  semana: { label: "Semana" },
  mes: { label: "Mês" },
  trimestre: { label: "Trimestre" },
  ano: { label: "Ano" },
};

export const DOCUMENTO_TIPO_CONFIG: Record<string, { label: string }> = {
  contrato: { label: "Contrato" },
  escritura: { label: "Escritura" },
  procuracao: { label: "Procuração" },
  laudo: { label: "Laudo" },
  certidao: { label: "Certidão" },
  foto: { label: "Foto" },
  planta: { label: "Planta" },
  outro: { label: "Outro" },
};

export const MANUTENCAO_PRIORIDADE_CONFIG: Record<string, { label: string; className: string }> = {
  baixa: { label: 'Baixa', className: 'bg-blue-100 text-blue-800' },
  media: { label: 'Média', className: 'bg-yellow-100 text-yellow-800' },
  alta: { label: 'Alta', className: 'bg-orange-100 text-orange-800' },
  urgente: { label: 'Urgente', className: 'bg-red-100 text-red-800' },
};

export const MANUTENCAO_TIPO_CONFIG: Record<string, string> = {
  preventiva: 'Preventiva',
  corretiva: 'Corretiva',
  emergencial: 'Emergencial',
  reforma: 'Reforma',
};

export const NEGOCIACAO_STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  qualificacao: { label: 'Qualificação', color: 'bg-blue-500' },
  visitas: { label: 'Visitas', color: 'bg-purple-500' },
  proposta: { label: 'Proposta', color: 'bg-yellow-500' },
  negociacao: { label: 'Negociação', color: 'bg-orange-500' },
  fechado: { label: 'Fechado', color: 'bg-green-500' },
  cancelado: { label: 'Cancelado', color: 'bg-red-500' },
};

export const MARKETING_STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  rascunho: { label: 'Rascunho', variant: 'secondary' },
  ativa: { label: 'Ativa', variant: 'default' },
  pausada: { label: 'Pausada', variant: 'outline' },
  concluida: { label: 'Concluída', variant: 'secondary' },
};

export const MARKETING_TIPO_CONFIG: Record<string, { label: string }> = {
  email: { label: 'E-mail' },
  whatsapp: { label: 'WhatsApp' },
  alerta_imovel: { label: 'Alerta de Imóvel' },
};

export const ACAO_LABELS: Record<string, string> = {
  // Gamificacao action labels
  cliente_cadastrado: 'Novo cliente cadastrado',
  visita_realizada: 'Visita realizada',
  proposta_enviada: 'Proposta enviada',
  negocio_fechado: 'Negócio fechado',
  meta_concluida: 'Meta concluída',
  avaliacao_imovel: 'Avaliação de imóvel',
  captacao_imovel: 'Captação de imóvel',
  indicacao_cliente: 'Indicação de cliente',
  // LogAcoes action labels
  criar: 'Criou',
  editar: 'Editou',
  excluir: 'Excluiu',
  concluir: 'Concluiu',
  arquivar: 'Arquivou',
  desarquivar: 'Desarquivou',
  mover: 'Moveu',
  login: 'Fez login',
  logout: 'Fez logout',
};

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}
