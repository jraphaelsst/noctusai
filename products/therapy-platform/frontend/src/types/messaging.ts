export interface Conversation {
  id: string;
  mode: 'human' | 'ai_managed' | 'hybrid';
  last_message_at?: string;
  created_at: string;
  other_participant_name: string;
  other_participant_avatar?: string;
  other_participant_type: 'user' | 'clinic' | 'platform_support';
  last_message_preview?: string;
  unread_count: number;
  is_muted: boolean;
  is_support: boolean;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_type: 'user' | 'clinic_entity' | 'platform_support' | 'ai_agent';
  sender_user_id?: string;
  sender_clinic_id?: string;
  message_type: 'text' | 'system' | 'ai' | 'image' | 'audio';
  content?: string;
  file_url?: string;
  file_type?: string;
  file_size?: number;
  ai_processed_content?: string;
  created_at: string;
  is_own: boolean;
}

export interface MessageReport {
  id: string;
  conversation_id: string;
  message_id?: string;
  reason: string;
  status: 'pending' | 'reviewed' | 'resolved';
  resolution?: string;
  created_at: string;
}

export type ConversationFilter = 'todas' | 'nao_lidas' | 'pacientes' | 'terapeutas' | 'clinicas' | 'suporte';
