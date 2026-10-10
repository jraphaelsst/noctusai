"""Extrair Pesquisa — extractor prompt rendering + strict literal-span parser."""
from __future__ import annotations

from app.modules.media_creation.pesquisa_fontes import PostFonte
from app.modules.media_creation.pesquisa_variables import CLASSIFIABLE
from app.modules.media_creation.prompts.pesquisa_extractor import (
    CONTENT_MAX_CHARS,
    MAX_PAIRS_PER_POST,
    PESQUISA_EXTRACTOR_SYSTEM_PROMPT,
    build_extractor_user_message,
    parse_extractor_output,
    truncate_headline,
)

TEXTO = (
    "Eu sou mulher e tenho mais de 40 anos. Sofro com insônia há anos! "
    "Já tentei várias dietas e nada funcionou.   Quero perder 8kg em 3 meses."
)


def test_prompt_is_draft_and_renders_all_classifiable_slugs():
    import app.modules.media_creation.prompts.pesquisa_extractor as m

    assert "DRAFT — awaiting owner validation" in m.__doc__
    assert len(CLASSIFIABLE) == 36
    for v in CLASSIFIABLE:
        assert f"{{{{{v.slug}}}}} | {v.description}" in PESQUISA_EXTRACTOR_SYSTEM_PROMPT
    assert "LITERAIS" in PESQUISA_EXTRACTOR_SYSTEM_PROMPT


def test_user_message_has_metrics_header_with_dash_for_null():
    post = PostFonte("instagram_media", "a", "1", None, None, "2026-10-01T10:00:00+00:00", TEXTO,
                     True, None, 3, 0, {})
    msg = build_extractor_user_message(post)
    assert "Instagram" in msg and "2026-10-01" in msg
    assert "Views: —" in msg and "Likes: 3" in msg and "Comentários: 0" in msg
    assert msg.endswith(TEXTO)


def test_valid_pairs_pass_with_excerpts():
    reply = (
        "{{DORES-TANGIVEIS-DO-AVATAR}}\n[Sofro com insônia há anos]\n\n"
        "{{FRUSTRACOES-DO-AVATAR}}\n[Já tentei várias dietas]\n"
    )
    pairs, excerpts, desc = parse_extractor_output(reply, TEXTO)
    assert pairs == [("DORES-TANGIVEIS-DO-AVATAR", "Sofro com insônia há anos"),
                     ("FRUSTRACOES-DO-AVATAR", "Já tentei várias dietas")]
    assert desc == 0
    # truncateHeadline: the right cut is searched from max(matchEnd, leftCut+30),
    # so a very short sentence runs on into the next one (CoreStudio's rule).
    assert excerpts[pairs[0]] == "Sofro com insônia há anos! Já tentei várias dietas e nada funcionou."
    assert excerpts[pairs[1]] == "Já tentei várias dietas e nada funcionou."


def test_literal_match_ignores_case_whitespace_and_edge_punctuation():
    reply = "{{DESEJOS-TANGIVEIS-DO-AVATAR}}\n[quero  PERDER 8kg em 3 meses!]"
    pairs, _, desc = parse_extractor_output(reply, TEXTO)
    assert len(pairs) == 1 and desc == 0


def test_unknown_slug_non_literal_overlong_and_chatter_are_discarded_and_counted():
    reply = (
        "Claro! Aqui estão os itens:\n"                                  # chatter -> 1
        "{{INVENTADA}}\n[Sofro com insônia há anos]\n\n"                  # unknown slug -> 1
        "{{DORES-TANGIVEIS-DO-AVATAR}}\n[sofre de insônia crônica]\n\n"   # non-literal -> 1
        "{{DORES-TANGIVEIS-DO-AVATAR}}\n[" + "a" * (CONTENT_MAX_CHARS + 1) + "]\n\n"  # too long -> 1
        "{{DESEJOS-TANGIVEIS-DO-AVATAR}}\n[perder 8kg em 3 meses]\n\n"    # valid
        "{{DORES-TANGIVEIS-DO-AVATAR}}\n"                                 # slug with no content -> 1
    )
    pairs, _, desc = parse_extractor_output(reply, TEXTO)
    assert pairs == [("DESEJOS-TANGIVEIS-DO-AVATAR", "perder 8kg em 3 meses")]
    assert desc == 5


def test_global_variable_slug_is_not_accepted():
    from app.modules.media_creation.pesquisa_variables import VARIABLES

    g = next(v for v in VARIABLES if not v.classifiable)
    pairs, _, desc = parse_extractor_output(f"{{{{{g.slug}}}}}\n[insônia]", TEXTO)
    assert pairs == [] and desc == 1


def test_cap_per_post_and_in_reply_duplicates():
    words = [f"palavra{i}" for i in range(MAX_PAIRS_PER_POST + 3)]
    texto = " ".join(words)
    reply = "\n\n".join(f"{{{{DORES-TANGIVEIS-DO-AVATAR}}}}\n[{w}]" for w in words)
    reply += "\n\n{{DORES-TANGIVEIS-DO-AVATAR}}\n[palavra0]"
    pairs, _, desc = parse_extractor_output(reply, texto)
    assert len(pairs) == MAX_PAIRS_PER_POST and desc == 3  # duplicate is not counted


def test_empty_reply_and_empty_text():
    assert parse_extractor_output("", TEXTO) == ([], {}, 0)
    assert parse_extractor_output("{{DORES-TANGIVEIS-DO-AVATAR}}\n[x]", "")[2] == 1


def test_truncate_headline_rule():
    t = "Primeira frase longa o bastante. Segunda frase com o alvo no meio dela. Terceira."
    assert truncate_headline(t, "o alvo") == "Segunda frase com o alvo no meio dela."
    assert truncate_headline("sem pontuação alvo aqui", "alvo") == "sem pontuação alvo aqui"
    assert truncate_headline("abc def", "zzz") == "abc def"
