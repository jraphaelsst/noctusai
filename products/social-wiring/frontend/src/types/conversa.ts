/** CONTRACT §2 (sw-lead-to-contract S2) — the card's WhatsApp conversation. */
export interface MensagemAnexo {
  mime: string | null;
  nome: string | null;
  documento_id: string | null;
}

export interface Mensagem {
  id: string;
  direcao: "in" | "out";
  texto: string;
  enviada_em: string | null;
  anexo: MensagemAnexo | null;
}

export interface Conversa {
  chat_id: string | null;
  connection_id: string | null;
  mensagens: Mensagem[];
}

export interface PedirDocumentosResposta {
  mensagem_id: string;
  itens_solicitados: string[];
}

/** A document that arrived by WhatsApp and waits for the operator to pick its type. */
export interface DocumentoAClassificar {
  id: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  created_at: string;
  origem_entrada: "upload" | "whatsapp";
  classificacao_tipo_provavel: string | null;
  classificacao_confianca: "alta" | "baixa" | "nenhuma" | null;
}
