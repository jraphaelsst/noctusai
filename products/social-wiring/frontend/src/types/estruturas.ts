/**
 * Estruturas (platform library of script structures) — wire types. Verbatim from
 * projects/core-studio-build/specs/estruturas-contract.md §11.1 (only the import line is added).
 * BE schemas mirror these; change the contract first.
 */
import type { PostRef, RoteiroEstrutura, RoteiroStatus, ViralCard } from './geracao'

export type EstruturaFormato = 'reels' | 'carrossel' | 'stories' | 'post'
export type EstruturaObjetivo = 'alcance' | 'autoridade' | 'conexao' | 'venda'
export type EstruturaStatus = 'rascunho' | 'ativa' | 'arquivada'
export type EstruturaOrigem = 'manual' | 'import_corestudio' | 'import_maquina' | 'viral_auto'
export type OrigemCampo = 'fonte' | 'referencia' | 'ia_sugerido' | 'admin'
export type EstruturaPerfilRef = { id: string; handle: string; nome: string | null; foto_url?: string | null /* absent for non-admins */ }
export type TipoBloco = { id: string; nome: string; ordem: number; tempo_tipico: string | null; instrucao_referencia: string; ativo: boolean }
export type Bloco = { id: string; ordem: number; nome: string; tipo: { id: string; nome: string }; tempo: string | null; instrucao: string | null;
  nota: string | null; repeticoes: number;
  proveniencia?: { nome: OrigemCampo; tipo: OrigemCampo; tempo: OrigemCampo; instrucao: OrigemCampo } /* admin only */ }
export type EstruturaResumo = { id: string; codigo: number; perfil: EstruturaPerfilRef; formula_headline: string; formato: EstruturaFormato | null;
  objetivos: EstruturaObjetivo[]; blocos_total: number; viral: { id: string; codigo: number; permalink: string; thumbnail_url: string | null } | null;
  status: EstruturaStatus; selecionada_pela_marca?: boolean; updated_at: string; pendente_revisao?: boolean /* admin only */;
  origem?: EstruturaOrigem /* admin only; absent for members and in lists today */; revisao_por_desuso?: string | null /* admin only */ }
export type EstruturaDetalhe = EstruturaResumo & { blocos: Bloco[]; versao: number;
  ref_externa?: string | null; referencia_rotulo?: string | null; formula_herdada_de?: string | null;
  proveniencia?: { formula_headline: OrigemCampo; formato: OrigemCampo; objetivos: OrigemCampo } /* admin only */ }
export type EstruturaRef = { id: string; codigo: number; perfil: { id: string; handle: string; nome: string | null }; formula_trecho: string }
export type EstruturaUso = EstruturaRef & { papel: 'principal' | 'mistura'; blocos: { id: string; nome: string }[] }
export type PerfilCandidato = { perfil_id: string; handle: string; nome: string | null }
export type ResolucaoPerfis = { resolvidos: (PerfilCandidato & { via: 'mencao' | 'handle' | 'nome'; confianca: number })[];
  ambiguos: { trecho: string; candidatos: PerfilCandidato[] }[]; nao_encontrados: { trecho: string; sugestoes: PerfilCandidato[] }[] }
export type PropostaEstrutura = { id: string; codigo: number; perfil: { id: string; handle: string; nome: string | null }; principal: boolean }
export type Proposta = { id: string; ordem: number; texto: string; gatilho_tag: string | null; estruturas: PropostaEstrutura[];
  status: 'proposta' | 'escolhida'; headline_id: string | null }
export type FluxoEtapa = 'headline_salva' | 'roteiro_gerando' | 'roteiro_pronto' | 'falhou'
export type Fluxo = { proposta_id: string; etapa: FluxoEtapa; headline: { id: string; texto: string };
  roteiro: { id: string; nome: string; status: RoteiroStatus; formato: EstruturaFormato; duracao: 'auto'|'1'|'2'|'3'; ordem_cta: RoteiroEstrutura; versao: number } | null;
  post: PostRef | null; estruturas: EstruturaUso[]; legenda: 'pendente' | 'gerada' | 'indisponivel'; erro_codigo: string | null }
export type ImportacaoRelatorio = { id: string; fonte: 'referencia' | 'maquina_de_roteiros'; status: 'simulada'|'em_andamento'|'concluida'|'falhou';
  dry_run: boolean; arquivo_sha256: string; linhas_total: number; perfis_criados: number; perfis_mesclados: number; estruturas_criadas: number;
  estruturas_atualizadas: number; estruturas_inalteradas: number; estruturas_ignoradas: number; ignoradas_motivos: Record<string, number>;
  blocos_criados: number; campos_nao_importados: string[]; erro: string | null; created_at: string; finished_at: string | null }
export type VideoPorLinkResultado = { viral: ViralCard; perfil_criado: boolean; ja_existia: boolean }
export type HeadlineRoteiroItem = { headline: { id: string; texto: string; favorita: boolean; created_at: string; acima_recomendado: boolean } | null;
  headline_texto: string;
  roteiro: { id: string; nome: string; status: RoteiroStatus; formato: EstruturaFormato; duracao: 'auto'|'1'|'2'|'3'; ordem_cta: RoteiroEstrutura; versao: number;
    aprovacao: { estado: 'pendente' | 'aprovado' | 'rejeitado' } | null } | null;
  estruturas: EstruturaUso[]; conversa: { id: string; titulo: string } | null; post: PostRef | null; created_at: string }
export type EstruturaOrigemCard = { headline: { id: string; texto: string } | null;
  roteiro: { id: string; nome: string; status: RoteiroStatus; formato: EstruturaFormato; duracao: 'auto'|'1'|'2'|'3'; ordem_cta: RoteiroEstrutura; versao: number } | null;
  estruturas: EstruturaUso[]; formato: EstruturaFormato | null; legenda: { texto: string | null; origem: 'ia' | 'usuario' | null }; conversa: { id: string; titulo: string } | null }
