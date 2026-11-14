-- ============================================================================
-- 122_seed_fotos_rotular.sql -- prompt registry row `fotos.rotular` (photo labeling, vision).
--
-- ONE-TIME SEED of starting content, inserted ON CONFLICT DO NOTHING. After it lands the DB row
-- (public.plataforma_agentes) is the only truth, edited in the registry UI; nothing here is ever
-- re-applied over it. Owner decision 2026-11-13: vision runs on Anthropic (standard tier,
-- model_policy: claude-sonnet-5). Consumed by noctusai_lib.domain.photo_editing.labeling.label_photo
-- and the toolkit tool noctus.dev.photo_label_dataset.
-- Forward-only + idempotent. NOT applied by the slice that authored it -- the steward/owner applies it.
-- ============================================================================
INSERT INTO public.plataforma_agentes (chave, nome, descricao, vendor, modelo, prompt, capacidade)
VALUES (
    'fotos.rotular',
    'Fotos: rotulador de fotos de imoveis',
    'Rotula UMA foto de imovel (tipo de ambiente + atributos de qualidade/edicao). Saida JSON estrita.',
    'anthropic',
    'claude-sonnet-5',
    $prompt$
You label real-estate listing photos for a training dataset.
Return ONLY a JSON object, no prose, with exactly these keys:
room_type: one of ['sala', 'sala_jantar', 'cozinha', 'quarto', 'suite', 'banheiro', 'lavabo', 'varanda', 'area_servico', 'fachada', 'area_lazer', 'piscina', 'churrasqueira', 'academia', 'garagem', 'jardim', 'vista', 'planta', 'detalhe', 'outro']
exposure: under|ok|over
white_balance: warm|neutral|cool|mixed
verticals: straight|tilted   (vertical lines of walls/doors/facade converge or lean => tilted)
sky: none|dull|blue|replaced   (none if no sky is visible, e.g. interiors)
windows: blown|balanced|n_a
staging: empty|furnished|cluttered
framing: wide|normal|tight
lens: ultrawide|normal
quality_score: integer 1-5 (5 = magazine-ready listing photo)
edit_needed: list of short strings, the edits that would most improve it (e.g. "straighten verticals", "lift shadows", "pull windows", "declutter", "neutralize WB")
notes: one short sentence
$prompt$,
    'vision'
)
ON CONFLICT (chave) DO NOTHING;
