"""Método Audience — the in-home content methodology the generation stages obey.

This is the platform's own copy of the attention-economy methodology used to
structure Instagram-first posts (carousel / single / reels). It is embedded
here so the media-creation module is fully self-contained: no runtime or
authoring dependency on any external folder or sibling repo.

Injected into the storyboard + copy system prompts so every generated post is
built on an explicit trigger + template + role skeleton instead of generic
benefit copy. Keep this the single source of truth — the prompts reference it,
they do not re-state it.
"""

# ── The 7 attention triggers — choose exactly ONE dominant per post ──────────
METODO_TRIGGERS = """## Os 7 gatilhos de atenção (escolha exatamente UM dominante; 0–2 embutidos)

1. **Recompensa** — "Me dê [tempo curto] e eu [resolvo sua dor / realizo seu desejo]."
2. **Mistério** — "Descubra por que [evento impactante] está acontecendo."
3. **Reconhecimento** — "O que [grupo específico] precisa saber sobre [assunto]."
4. **Popularidade** — "O que [figura/tema popular] pode nos ensinar sobre [tema relevante]."
5. **Crença** — "Quando foi que [mudança significativa] virou [situação atual]?" (questiona uma crença aceita)
6. **Autoridade** — "[Coisas] que eu jamais [faria] como [profissão/especialista]."
7. **Disrupção** — "[Assunto popular] não é sobre [crença comum], e sim sobre [nova perspectiva]."

Regra: o gatilho declarado precisa OPERAR de fato no texto — nunca é só um rótulo."""

# ── The post structure skeleton — the ordered beats every post is built from ─
METODO_STRUCTURE = """## A estrutura do post (a espinha — beats em ordem, capa primeiro, CTA por último)

- **capa** — o gancho que para o scroll (≤7 palavras). Carrega o gatilho dominante.
- **identificacao** — chama o público exato pelo nome ("Pra [pessoa] que [situação]…"). O leitor precisa se reconhecer.
- **virada** — o reenquadramento ("isso não é X, é Y"): quebra a crença comum montada na capa.
- **nome** — dá nome à causa oculta / ao mecanismo real ("não foi [X], foi [o tipo/o nome]").
- **prova** — prova por ESPECIFICIDADE (um sinal concreto e verificável, não um número inventado).
- **valor** — UM passo prático que o leitor consegue executar sozinho, sem mais contexto.
- **cta** — fechamento pedindo SALVAR + MARCAR/ENVIAR (sends/saves são o sinal de alcance atual).

Distribua os beats no `slide_count` pedido: SEMPRE `capa` no 1 e `cta` no último; preencha o
miolo com os beats na ordem acima, priorizando `virada` e `prova`. Funde beats quando houver
poucos slides; nunca pule a `capa` nem o `cta`. Use exatamente esses valores de `role`."""

# ── The 32-template headline library — the fill-in patterns ──────────────────
METODO_TEMPLATES = """## Biblioteca de 32 templates de headline (cite o(s) número(s) que usar)

1. Conselho ultra-específico (ordem direta) — "Seja [adjetivo] em [ano]."
2. Autoridade → mudança de hábito.  3. Contraste enganoso (parece bom, faz mal).
4. O maior motivo.  5. Questionar uma crença popular.  6. O inimigo mexeu em algo importante.
7. O inimigo ama/odeia quando você…  8. Atalho de tempo (anos → minutos).  9. Aviso antes de um evento.
10. Redefinir autoridade/desejo.  11. Quebra de padrão (contraintuitivo).  12. Transformação (dor → resultado).
13. Comparação A vs. B (termine num ponto de vista pessoal).  14. O que fazer quando… (solução de situação).
15. Alerta segmentado.  16. O elemento subestimado.  17. Três efeitos de um comportamento.
18. Permissão para o incomum.  19. Nós vs. eles (grupos).  20. Obrigatório para quem tem X.
21. Efeito sobre o corpo/vida.  22. Sinais de que você…  23. "E é assim que…" (gancho de situação).
24. Antes de um evento, faça X.  25. Lista de itens com impacto ("essas 3 coisas…").
26. Não foi por X, e sim por Y (causa oculta) — SÓ quando montado sobre uma notícia/evento já viral.
27. A causa do seu problema é você.  28. Reenquadramento ("isso não é X, é Y").
29. Não é 1, nem 2, nem 3 — é algo oculto.  30. Erros ao fazer X.
31. Autoridade descobre o porquê ("Finalmente [autoridade] descobriu por que…").
32. Quem decidiu que isso deveria ser assim?

Fidelidade ao template: se declarar o 26, ele PRECISA estar montado sobre um evento viral — caso
contrário é o 28. Não confie no rótulo; construa o mecanismo."""

# ── Quality rules the auditor enforces (bake them into generation) ───────────
METODO_QUALITY = """## Regras de qualidade (obedeça na geração — é o mesmo padrão que um auditor cobraria)

1. **Especificidade** — público/comportamento/objeto/prazo o mais específico possível ("cafezinho preto" > "café").
2. **Cumpra a promessa** — o que a capa promete (o "nome", o primeiro passo) é ENTREGUE no conteúdo. Sem isca sem entrega.
3. **Emoções quentes** (medo, raiva, euforia) movem; emoções frias (tristeza) paralisam — prefira quentes.
4. **Moeda social** — quem compartilha parece mais inteligente/informado? Evite o óbvio.
5. **Um gatilho dominante por post**; combine ≥2 assuntos de interesse na headline quando possível.
6. **CTA = salvar + marcar/enviar** (alinhado ao sinal de alcance de sends/saves).
7. **Anonimato + atemporalidade** — sem nomes reais / @ / marcas / números de resultado inventados; nada datado.
   Deixe placeholders `[seu nome]` / `[sua abordagem]` para a pessoa preencher a própria identidade."""

# The full methodology block, assembled once, injected into system prompts.
METODO_AUDIENCE = "\n\n".join(
    [
        "# Método Audience (a metodologia que rege este post)",
        METODO_TRIGGERS,
        METODO_STRUCTURE,
        METODO_TEMPLATES,
        METODO_QUALITY,
    ]
)

__all__ = [
    "METODO_AUDIENCE",
    "METODO_TRIGGERS",
    "METODO_STRUCTURE",
    "METODO_TEMPLATES",
    "METODO_QUALITY",
]
