-- Migration: help_chat_conversas
-- Schema: public
--
-- Stored conversations of the seed help-chat organ
-- (noctusai_lib.domain.help_chat) + the end-of-attendance rating.
-- Product-agnostic (one `produto` column). Owner decisions 2026-10-07: FULL
-- text stored; readable ONLY by the NoctusAI platform team (service role);
-- kept forever.
-- NOC-REMEDIATE[help-chat-retention]: no retention/purge job — conversations are kept forever until the owner sets a window — 2026-10-07

SET search_path = public, public;

CREATE TABLE IF NOT EXISTS public.help_chat_conversas (
    id                   uuid PRIMARY KEY,
    produto              text NOT NULL,
    org_id               uuid NOT NULL,
    user_id              uuid,
    iniciada_em          timestamptz NOT NULL DEFAULT now(),
    atualizada_em        timestamptz NOT NULL DEFAULT now(),
    encerrada_em         timestamptz,
    motivo_encerramento  text CHECK (motivo_encerramento IN ('concluido', 'inatividade')),
    nota                 smallint CHECK (nota BETWEEN 1 AND 5),
    comentario           text CHECK (char_length(comentario) <= 1000),
    avaliada_em          timestamptz
);

CREATE INDEX IF NOT EXISTS idx_help_chat_conversas_produto_iniciada
    ON public.help_chat_conversas (produto, iniciada_em DESC);
CREATE INDEX IF NOT EXISTS idx_help_chat_conversas_org
    ON public.help_chat_conversas (org_id);

CREATE TABLE IF NOT EXISTS public.help_chat_mensagens (
    id           bigserial PRIMARY KEY,
    conversa_id  uuid NOT NULL REFERENCES public.help_chat_conversas (id) ON DELETE CASCADE,
    papel        text NOT NULL CHECK (papel IN ('user', 'assistant')),
    conteudo     text NOT NULL,
    pagina_atual text,
    modelo       text,
    latency_ms   integer,
    truncated    boolean NOT NULL DEFAULT false,
    parcial      boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_help_chat_mensagens_conversa
    ON public.help_chat_mensagens (conversa_id, created_at);

-- SERVICE-ROLE ONLY: RLS on, NO policies, anon/authenticated REVOKEd.
ALTER TABLE public.help_chat_conversas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.help_chat_mensagens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.help_chat_conversas FROM anon, authenticated;
REVOKE ALL ON public.help_chat_mensagens FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.help_chat_mensagens_id_seq FROM anon, authenticated;
