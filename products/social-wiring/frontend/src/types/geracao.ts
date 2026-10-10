/**
 * Geração (Criação de Mídia) — wire types. Verbatim from
 * projects/core-studio/specs/geracao-contract.md §4.8 (`export` added only).
 * BE schemas mirror these; change the contract first.
 */
export type LoteOrigem = 'form_me' | 'form_public' | 'form_viral' | 'biblioteca' | 'sugestao_auto'
export type GeracaoStatus = 'criando' | 'processando' | 'completo' | 'falha'
export type RoteiroStatus = 'criando' | 'perguntas' | 'processando' | 'completo' | 'falha'
export type Criatividade = 'essencial' | 'equilibrado' | 'explorador'
export type Gatilho = 'recompensa'|'misterio'|'reconhecimento'|'popularidade'|'crenca'|'autoridade'|'disrupcao'
export type Taxon = { id: number; nome: string }
export type Taxonomias = { nichos: Taxon[]; profissoes: Taxon[]; formatos: (Taxon & { definicao: string })[];
                    gatilhos: { slug: Gatilho; nome: string; formula: string }[]; tons: Taxon[] }
export type PerfilCriacao = { marca_id: string; bio: string; nichos: number[]; profissoes: number[];
                       apresentacao_magnetica: string; ctas: string; updated_at: string | null }
export type Treinamento = { id: string; ordem: number; titulo: string; descricao: string; video_url: string | null; ativo: boolean }
export type PerfilStatus = 'aguardando'|'ativo'|'pausado'|'nao_encontrado'|'sem_conta'|'erro'
export type PerfilMonitorado = { id: string; handle: string; nome: string | null; foto_url: string | null; seguidores: number | null;
                          status: PerfilStatus; erro_mensagem: string | null; ultima_sync_em: string | null;
                          metrica_base: 'views' | 'engajamento' | null; mediana_metrica: number | null;
                          virais: number; posts: number;
                          /** Kill-switch state of the library ingestion (false => monitoring not activated yet). */
                          ingestao_ativa: boolean }
export type TranscricaoViralStatus = 'nao_aplicavel'|'pendente'|'na_fila'|'concluida'|'falhou'|'grande_demais'|'longa_demais'|'sem_orcamento'
export type ViralCard = { id: string; codigo: number; perfil: { id: string; handle: string }; thumbnail_url: string | null;
                   permalink: string; publicado_em: string; views: number | null; likes: number | null; comments: number | null;
                   duracao_s: number | null; score_viral: number | null; e_viral: boolean; trecho: string | null }
export type ViralDetalhe = ViralCard & { caption: string | null; gancho: string | null; transcricao_texto: string | null;
                   transcricao_status: TranscricaoViralStatus; classificacao_status: 'pendente'|'processando'|'concluida'|'falhou';
                   nichos: Taxon[]; profissoes: Taxon[]; formatos: Taxon[]; gatilho: Gatilho | null;
                   estrutura_utilizavel: boolean; blueprint?: string | null }
export type Referencia = { id: string; modo: 'perfil' | 'video'; perfil: PerfilMonitorado | null; viral: ViralCard | null;
                    auto_atualizar: boolean; posts_ate: string | null; updated_at: string }
export type ItemUsado = { slot: string; item_id: string; conteudo: string }
export type Headline = { id: string; marca_id: string; lote_id: string | null; texto: string; texto_original: string | null;
                  angulo: 1 | 2 | null; viral: ViralCard | null; template_metodo: number | null; itens_usados: ItemUsado[];
                  favorita: boolean; modo: 'manual' | 'automatico' | null; roteiro_id: string | null; created_at: string }
export type HeadlineLote = { id: string; marca_id: string; origem: LoteOrigem; status: GeracaoStatus; etapa: string | null;
                      estruturas_total: number; estruturas_processadas: number; estruturas_com_erro: number;
                      aviso_poucas_estruturas: boolean; fallback_metodo: boolean; erro: string | null;
                      resumo: string; created_at: string; finished_at: string | null }
export type HeadlineLoteDetalhe = HeadlineLote & { parametros: Record<string, unknown>; headlines: Headline[] }
export type RoteiroPergunta = { id: string; pergunta: string; resposta: string | null }
export type RoteiroResumo = { id: string; nome: string; headline_texto: string; headline_id: string | null;
                       status: RoteiroStatus; created_at: string }
export type Roteiro = RoteiroResumo & { instrucoes: string; fonte: 'ia' | 'web' | 'link'; duracao: 'auto'|'1'|'2'|'3';
                 brain_id: string | null; viral: ViralCard | null; perguntas: RoteiroPergunta[]; etapa: string | null;
                 conteudo: string | null; fontes: string | null; versao: number; feedback: 'gostei'|'nao_gostei'|null;
                 feedback_motivo: string | null; erro: string | null }
export type Agente = 'headline' | 'roteiro'
export type Conversa = { id: string; marca_id: string; agente: Agente; titulo: string; last_message_at: string | null }
export type MencaoTipo = 'pesquisa' | 'cerebro' | 'biblioteca' | 'headline'
export type Mencao = { tipo: MencaoTipo; id: string; rotulo: string; detalhe: string | null }
export type Mensagem = { id: string; role: 'user' | 'assistant'; conteudo: string; referencias: Mencao[];
                  status: 'completa' | 'parcial' | 'erro'; truncada: boolean; created_at: string }
export type Memoria = { id: string; texto: string; created_at: string }
export type EventoHistorico = { tipo: string; texto: string; ator: string | null; em: string }
export type DashboardCriacao = { saudacao_nome: string; kpis: { headlines_geradas: number; roteiros_gerados: number; itens_pendentes: number };
                          historico: EventoHistorico[]; sugeridas: Headline[] }
