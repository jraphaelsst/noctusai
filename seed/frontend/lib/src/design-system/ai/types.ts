/**
 * Shared AI-output types — mirrors `noctusai_lib.ai.outputs.AIOutput` 1:1.
 * Keep this file in sync if the backend dataclass adds/removes a field.
 */

export type AIOutputKind =
  | 'classification'
  | 'score'
  | 'flag'
  | 'extraction'
  | 'narrative';

export interface AIOutput {
  id: string;
  ref_type: string;
  ref_id: string;
  kind: AIOutputKind;
  label: string;
  score: number | null;
  chip: string | null;
  explanation: string | null;
  confidence: number | null;
  model_version: string | null;
  prompt_version: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
