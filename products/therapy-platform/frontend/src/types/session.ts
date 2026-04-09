// Session, AI Pipeline & Longitudinal type definitions

export interface SessionRecord {
  id: string;
  appointment_id: string;
  combined_transcript_text?: string;
  therapist_notes_private?: string;
  total_segments: number;
  ai_generated_at?: string;
  audio_deleted_at?: string;
  created_at: string;
}

export interface SessionSummaryVersion {
  id: string;
  session_record_id: string;
  track: 'base' | 'clinical';
  version_number: number;
  summary: string;
  key_points: string[];
  tags: string[];
  source: 'ai_generated' | 'ai_auto_fallback' | 'manual_edit';
  created_at: string;
}

export interface SessionObservation {
  id: string;
  session_record_id: string;
  observation_text: string;
  is_initial: boolean;
  created_at: string;
  updated_at: string;
  deleted_at?: string;
}

export interface PatientSessionNote {
  id: string;
  session_record_id: string;
  patient_id: string;
  note_text: string;
  created_at: string;
  updated_at: string;
}

export interface ClinicalLongitudinal {
  id: string;
  patient_id: string;
  therapist_id: string;
  version_number: number;
  narrative_summary: string;
  recurring_themes: string[];
  progress_timeline: string[];
  unresolved_topics: string[];
  observation_insights?: string;
  session_count_at_generation: number;
  created_at: string;
}

export interface PatientLongitudinal {
  id: string;
  patient_id: string;
  therapist_id: string;
  version_number: number;
  narrative_summary: string;
  recurring_themes: string[];
  progress_reflection: string[];
  ongoing_topics: string[];
  session_count_at_generation: number;
  created_at: string;
}

export interface SessionStatus {
  appointment_id: string;
  video_room_status: string;
  accessible_from: string;
  accessible_until: string;
  reopen_until?: string;
  session_started_at?: string;
  last_paused_at?: string;
  total_pauses: number;
  can_start: boolean;
  can_resume: boolean;
  can_reopen: boolean;
  minutes_remaining?: number;
}

export interface AudioSegment {
  id: string;
  segment_number: number;
  segment_type: 'initial' | 'resumed' | 'reopened';
  audio_file_url?: string;
  download_expires_at?: string;
  is_transcribed: boolean;
}
