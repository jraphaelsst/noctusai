// Segundo Cérebro — contract §4 (verbatim). Shared by FE-A/B/C and the backend schemas.

export type BrainKind = 'sistema' | 'custom'
export type BrainDisplayStatus = 'vazio' | 'pronto' | 'processando'
export type SynthesisStatus = 'idle' | 'processing' | 'error'
export type ReviewStatus = 'none' | 'pending' | 'done' | 'error'
export type ReviewVerdict = 'approved' | 'rejected'
export type ReviewDecision = 'accepted' | 'dismissed'
export type TranscricaoStatus = 'na_fila' | 'processando' | 'concluida' | 'falhou' | 'cancelada'   // shared, transcription-contract §4
export type ImportStatus = 'processing' | 'appended' | 'error'
export type ExtractionStatus = 'transcribing' | 'ready' | 'applied' | 'error'

export type BrainQuestion = { id: string; position: number; group: number; text: string; hint: string | null; optional: boolean }
export type BrainTemplate = { slug: string; name: string; description: string; sort_order: number; questions: BrainQuestion[] }
export type BrainSummary = { id: string; marca_id: string; kind: BrainKind; template_slug: string | null; name: string;
                      status: BrainDisplayStatus; content_chars: number; answered: number | null;
                      total_questions: number | null; synthesis_status: SynthesisStatus; updated_at: string }
export type Transcricao = { id: string; status: TranscricaoStatus; posicao: number | null; duracao_s: number | null;
                     texto: string | null; erro: { codigo: string; mensagem: string } | null }
export type Answer = { question_id: string; text: string; updated_at: string | null; transcricao: Transcricao | null;
                review: { status: ReviewStatus; verdict: ReviewVerdict | null; reason: string | null;
                          improved: string | null; decision: ReviewDecision | null; error: string | null } }
export type BrainImport = { id: string; kind: 'file' | 'youtube'; filename: string | null; source_url: string | null;
                     status: ImportStatus; chars_appended: number | null; error_message: string | null; created_at: string }
export type BrainDetail = BrainSummary & { content: string; content_version: number; synthesis_error: string | null;
                     synthesized_at: string | null; template: BrainTemplate | null; answers: Answer[]; imports: BrainImport[] }
export type Perfil = { marca_id: string; bio: string; updated_at: string | null }
export type ExtractionTarget = { brain_id: string; brain_name: string; applied_at: string | null }
export type ExtractionSummary = { id: string; marca_id: string; name: string; source_kind: 'url' | 'text'; source_url: string | null;
                           status: ExtractionStatus; error_message: string | null; targets: ExtractionTarget[]; created_at: string }
export type ExtractionDetail = ExtractionSummary & { transcript: string | null }
