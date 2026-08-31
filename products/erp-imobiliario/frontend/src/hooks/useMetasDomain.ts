/**
 * Metas domain hooks — teams, periods, company meta, point rules,
 * scoring config, team quotas, rankings, closings.
 *
 * One file, one entity per block of hooks. Follows ERP convention
 * (TanStack Query with api from @noctusai/seed/infra).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ── Types ────────────────────────────────────────────────────────

export interface Equipe {
  id: string;
  org_id: string;
  nome: string;
  cor?: string | null;
  icone?: string | null;
  lider_id?: string | null;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export interface EquipeMembro {
  id: string;
  equipe_id: string;
  user_id: string;
  papel: 'lider' | 'corretor';
  joined_at: string;
  left_at?: string | null;
}

export interface MetaPeriodo {
  id: string;
  org_id: string;
  nome: string;
  tipo: 'quinzenal' | 'mensal' | 'trimestral' | 'anual' | 'diaria' | 'semanal';
  data_inicio: string;
  data_fim: string;
  parent_periodo_id?: string | null;
  status: 'aberto' | 'em_avaliacao' | 'fechado';
}

export interface MetaEmpresa {
  id: string;
  periodo_id: string;
  categoria: string;
  valor_meta: number;
  observacoes?: string | null;
}

export interface CascadeResumo {
  periodo_id: string;
  categoria: string;
  meta_empresa: number;
  alocado_em_equipes: number;
  saldo_a_alocar: number;
  estouro: number;
  equipes_count: number;
}

export interface RegraPontuacao {
  id: string;
  org_id?: string | null;
  vigencia_periodo_id?: string | null;
  evento_tipo: 'captacao' | 'visita' | 'venda' | 'locacao' | 'reuniao';
  modalidade: 'padrao' | 'compartilhada' | 'exclusividade';
  pontos: number;
  descricao?: string | null;
}

export interface MetasConfig {
  org_id: string;
  vgv_por_ponto: number;
  peso_pontos: number;
  peso_vgv: number;
  metrica_ranking_padrao: 'pontos' | 'vgv' | 'unificado';
}

export interface RankingRow {
  corretor_id: string;
  equipe_id_snapshot?: string | null;
  pontos_atividade: number;
  vgv: number;
  pontos_vgv: number;
  score_unificado: number;
  rank: number;
  metric: number;
}

export interface Rankings {
  pontos: RankingRow[];
  vgv: RankingRow[];
  unificado: RankingRow[];
  config: { vgv_por_ponto: number; peso_pontos: number; peso_vgv: number };
}

// ── Helpers ───────────────────────────────────────────────────────

const unwrap = <T,>(res: any): T => (res?.data ?? res) as T;

// ── Equipes ──────────────────────────────────────────────────────

export function useEquipes(ativas_apenas = true) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'equipes', ativas_apenas],
    queryFn: async () => unwrap<Equipe[]>(await api.get(`/api/metas/equipes?ativas_apenas=${ativas_apenas}`)),
    enabled: !!user,
  });
}

export function useEquipe(equipeId: string | null) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'equipe', equipeId],
    queryFn: async () => unwrap<Equipe>(await api.get(`/api/metas/equipes/${equipeId}`)),
    enabled: !!user && !!equipeId,
  });
}

export function useCriarEquipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Partial<Equipe>) => unwrap<Equipe>(await api.post('/api/metas/equipes', body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'equipes'] });
      toast.success('Equipe criada');
    },
    onError: (e: any) => toast.error(`Erro ao criar equipe: ${e.message ?? 'desconhecido'}`),
  });
}

export function useAtualizarEquipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: string } & Partial<Equipe>) =>
      unwrap<Equipe>(await api.patch(`/api/metas/equipes/${id}`, body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'equipes'] });
      toast.success('Equipe atualizada');
    },
    onError: (e: any) => toast.error(`Erro ao atualizar equipe: ${e.message ?? 'desconhecido'}`),
  });
}

export function useDissolverEquipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => unwrap<any>(await api.delete(`/api/metas/equipes/${id}`)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'equipes'] });
      toast.success('Equipe dissolvida');
    },
  });
}

export function useEquipeMembros(equipeId: string | null) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'equipe-membros', equipeId],
    queryFn: async () => unwrap<EquipeMembro[]>(await api.get(`/api/metas/equipes/${equipeId}/membros`)),
    enabled: !!user && !!equipeId,
  });
}

export function useAdicionarMembro(equipeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { user_id: string; papel?: 'lider' | 'corretor' }) =>
      unwrap<EquipeMembro>(await api.post(`/api/metas/equipes/${equipeId}/membros`, body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'equipe-membros', equipeId] });
      qc.invalidateQueries({ queryKey: ['metas', 'equipes'] });
    },
  });
}

export function useAtualizarPapelMembro(equipeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ membro_id, papel }: { membro_id: string; papel: 'lider' | 'corretor' }) =>
      unwrap<EquipeMembro>(await api.patch(`/api/metas/equipes/${equipeId}/membros/${membro_id}`, { papel })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['metas', 'equipe-membros', equipeId] }),
  });
}

export function useRemoverMembro(equipeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (membro_id: string) =>
      unwrap<any>(await api.delete(`/api/metas/equipes/${equipeId}/membros/${membro_id}`)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'equipe-membros', equipeId] });
      qc.invalidateQueries({ queryKey: ['metas', 'equipes'] });
    },
  });
}

// ── Períodos ─────────────────────────────────────────────────────

export function usePeriodos(tipo?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'periodos', tipo ?? 'all'],
    queryFn: async () => {
      const qs = tipo ? `?tipo=${tipo}` : '';
      return unwrap<MetaPeriodo[]>(await api.get(`/api/metas/periodos${qs}`));
    },
    enabled: !!user,
  });
}

export function useGerarTrimestre() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { year: number; quarter: number }) =>
      unwrap<any>(await api.post('/api/metas/periodos/auto-generate', body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'periodos'] });
      toast.success('Trimestre gerado');
    },
  });
}

// ── Meta Empresa ────────────────────────────────────────────────

export function useMetasEmpresa(periodoId?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'empresa', periodoId ?? 'all'],
    queryFn: async () => {
      const qs = periodoId ? `?periodo_id=${periodoId}` : '';
      return unwrap<MetaEmpresa[]>(await api.get(`/api/metas/empresa${qs}`));
    },
    enabled: !!user,
    placeholderData: (prev) => prev,
  });
}

export function useCascadeResumo(periodoId: string | null) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'empresa-resumo', periodoId],
    queryFn: async () =>
      unwrap<CascadeResumo>(await api.get(`/api/metas/empresa/resumo?periodo_id=${periodoId}`)),
    enabled: !!user && !!periodoId,
    placeholderData: (prev) => prev,
  });
}

export function useUpsertMetaEmpresa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { periodo_id: string; valor_meta: number; categoria?: string }) =>
      unwrap<MetaEmpresa>(await api.post('/api/metas/empresa', body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'empresa'] });
      toast.success('Meta da empresa atualizada');
    },
  });
}

// ── Equipe quotas ──────────────────────────────────────────────

export interface MetaEquipe {
  id: string;
  periodo_id: string;
  equipe_id: string;
  categoria: string;
  valor_meta: number;
  observacoes?: string | null;
}

export function useMetasEquipe(periodoId?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'equipes-quotas', periodoId ?? 'all'],
    queryFn: async () => {
      const qs = periodoId ? `?periodo_id=${periodoId}` : '';
      return unwrap<MetaEquipe[]>(await api.get(`/api/metas/equipes-quotas${qs}`));
    },
    enabled: !!user,
    placeholderData: (prev) => prev,
  });
}

export function useUpsertMetaEquipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { periodo_id: string; equipe_id: string; valor_meta: number; categoria?: string }) =>
      unwrap<MetaEquipe>(await api.post('/api/metas/equipes-quotas', body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'equipes-quotas'] });
      qc.invalidateQueries({ queryKey: ['metas', 'empresa-resumo'] });
      toast.success('Meta da equipe atualizada');
    },
    onError: (e: any) => toast.error(`Erro: ${e.message ?? 'desconhecido'}`),
  });
}

// ── Regras Pontuação + Config ──────────────────────────────────

export function useRegrasPontuacao(evento_tipo?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'regras', evento_tipo ?? 'all'],
    queryFn: async () => {
      const qs = evento_tipo ? `?evento_tipo=${evento_tipo}` : '';
      return unwrap<RegraPontuacao[]>(await api.get(`/api/metas/regras-pontuacao${qs}`));
    },
    enabled: !!user,
    placeholderData: (prev) => prev,
  });
}

export function useMetasConfig() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'config'],
    queryFn: async () => unwrap<MetasConfig>(await api.get('/api/metas/configuracao')),
    enabled: !!user,
  });
}

export function useUpsertConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Partial<MetasConfig>) =>
      unwrap<MetasConfig>(await api.put('/api/metas/configuracao', body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'config'] });
      toast.success('Configuração atualizada');
    },
  });
}

export function useCriarRegra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Partial<RegraPontuacao>) =>
      unwrap<RegraPontuacao>(await api.post('/api/metas/regras-pontuacao', body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'regras'] });
      toast.success('Regra criada');
    },
  });
}

export function useAtualizarRegra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: string } & Partial<RegraPontuacao>) =>
      unwrap<RegraPontuacao>(await api.patch(`/api/metas/regras-pontuacao/${id}`, body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'regras'] });
      toast.success('Regra atualizada');
    },
  });
}

export function useDeletarRegra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => unwrap<any>(await api.delete(`/api/metas/regras-pontuacao/${id}`)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'regras'] });
      toast.success('Regra removida');
    },
  });
}

// ── Meta eventos lookup (for contextual indicators) ───────────

export interface MetaEvento {
  id: string;
  org_id: string;
  corretor_id: string;
  evento_tipo: 'captacao' | 'visita' | 'venda' | 'locacao' | 'reuniao';
  modalidade: 'padrao' | 'compartilhada' | 'exclusividade';
  pontos: number;
  valor_vgv: number | null;
  fracao: number | null;
  referencia_tipo: 'ativo' | 'evento' | 'comissoes_split' | 'contrato';
  referencia_id: string;
  data_evento: string;
  created_at: string;
}

export function useMetaEventosFor(referenciaTipo: string | null, referenciaId: string | null) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'meta-eventos', referenciaTipo, referenciaId],
    queryFn: async () => {
      const qs = new URLSearchParams({
        referencia_tipo: referenciaTipo!,
        referencia_id: referenciaId!,
      });
      return unwrap<MetaEvento[]>(await api.get(`/api/metas/meta-eventos?${qs}`));
    },
    enabled: !!user && !!referenciaTipo && !!referenciaId,
    staleTime: 60 * 1000,
  });
}

// ── Rankings ────────────────────────────────────────────────────

export function useRankings(params: { equipe_id?: string; data_inicio?: string; data_fim?: string } = {}) {
  const { user } = useAuthStore();
  const qs = new URLSearchParams();
  if (params.equipe_id) qs.set('equipe_id', params.equipe_id);
  if (params.data_inicio) qs.set('data_inicio', params.data_inicio);
  if (params.data_fim) qs.set('data_fim', params.data_fim);
  return useQuery({
    queryKey: ['metas', 'rankings', qs.toString()],
    queryFn: async () => unwrap<Rankings>(await api.get(`/api/metas/rankings?${qs}`)),
    enabled: !!user,
    staleTime: 30 * 1000,
    placeholderData: (prev) => prev,
  });
}

// ── Fechamentos ─────────────────────────────────────────────────

export function useFechamentos(periodoId?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'fechamentos', periodoId ?? 'all'],
    queryFn: async () => {
      const qs = periodoId ? `?periodo_id=${periodoId}` : '';
      return unwrap<any[]>(await api.get(`/api/metas/fechamentos${qs}`));
    },
    enabled: !!user,
    placeholderData: (prev) => prev,
  });
}

export function useFecharPeriodo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (periodo_id: string) =>
      unwrap<any>(await api.post('/api/metas/fechamentos/fechar', { periodo_id })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metas', 'fechamentos'] });
      qc.invalidateQueries({ queryKey: ['metas', 'periodos'] });
      toast.success('Período fechado');
    },
    onError: (e: any) => toast.error(`Erro ao fechar: ${e.message ?? 'desconhecido'}`),
  });
}

export function useTrimestreAggregate(trimestreId: string | null) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['metas', 'fechamentos-trimestre', trimestreId],
    queryFn: async () => unwrap<any>(await api.get(`/api/metas/fechamentos/trimestre/${trimestreId}`)),
    enabled: !!user && !!trimestreId,
    placeholderData: (prev) => prev,
  });
}
