"""The LLM guardrails organ: detectors, fingerprint, redaction, bounds, and the Fake/Real/factory shape."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from noctusai_lib.integrations.llm.guardrails import (
    FakeOutputGuard,
    Fingerprint,
    GuardContext,
    GuardRule,
    OutputGuard,
    RealOutputGuard,
    canario,
    contar_padroes,
    contato_nao_permitido,
    count_redactions,
    count_words,
    detectar_vazamento,
    esqueleto,
    fingerprint_of,
    formato_suspeito,
    get_output_guard,
    limpar,
    link_nao_permitido,
    lista_de_spec,
    mascarar_dados_da_org,
    outside_enum,
    outside_word_band,
    padroes_proibidos,
    pii_na_resposta,
    redact_payload,
    redact_pii,
    sem_falas_de_exemplo,
    tem_caractere_oculto,
    unretrieved_sources,
)

PROMPT = "Voce e a assistente da agencia e deve sempre responder em portugues com educacao e clareza ao cliente interessado"


def test_link_unknown_host_flagged_own_domain_and_tool_link_allowed():
    assert link_nao_permitido("veja evil.com/x", [], []) == {"links": 1}
    assert link_nao_permitido("veja https://loja.exemplo.com.br/a", [], ["exemplo.com.br"]) is None
    assert link_nao_permitido("https://x.io/1", ["https://x.io/1"], []) is None


def test_contact_allowed_only_when_official_or_typed_by_lead():
    assert contato_nao_permitido("ligue (11) 99999-1234", [], []) == {"telefones": 1}
    assert contato_nao_permitido("ligue (11) 99999-1234", ["11999991234"], []) is None
    assert contato_nao_permitido("mande para a@b.com", [], ["meu email a@b.com"]) is None
    assert contato_nao_permitido("chave pix: abc", [], []) == {"pix": 1}


def test_pii_valid_cpf_flagged_invalid_ignored_own_cnpj_allowed():
    assert pii_na_resposta("cpf 529.982.247-25") == {"cpf": 1}
    assert pii_na_resposta("cpf 111.111.111-11") is None
    assert pii_na_resposta("cnpj 11.222.333/0001-81", ["11222333000181"]) is None


def test_format_shapes_are_codes_never_fragments():
    assert formato_suspeito("```x```") == {"bloco_codigo": True}
    assert formato_suspeito("a" * 5, max_chars=3) == {"longo": True}
    assert formato_suspeito("oi") is None
    assert tem_caractere_oculto("a​b") and formato_suspeito("a​b") == {"caractere_oculto": True}


def test_patterns_run_on_skeleton_and_bad_pattern_is_skipped_not_fatal(caplog):
    assert padroes_proibidos("garanto aprovacao", [r"garanto"]) == {"padroes": 1}
    assert padroes_proibidos("g a r a n t o", [r"garanto"]) == {"padroes": 1}  # spaced-out letters meet the skeleton
    assert contar_padroes(["x"], ["("]) == 0
    assert "invalid_pattern" in caplog.text


def test_skeleton_and_clean():
    assert esqueleto("reserva one ponto com ponto br") == "reserva one.com.br"
    assert limpar("a​b") == "ab"
    assert lista_de_spec("a, b;c\nd") == ["a", "b", "c", "d"]


def test_leak_by_canary_and_by_shingle_window():
    c = canario(UUID(int=1), UUID(int=2), segredo="s")
    assert len(c) == 20 and c == canario(UUID(int=1), UUID(int=2), segredo="s")
    assert detectar_vazamento(f"codigo {c}", canario_do_prompt=c, impressao=None) == {"canario": True}
    fp = fingerprint_of(PROMPT, 8)
    assert isinstance(fp, Fingerprint)
    out = detectar_vazamento(PROMPT.upper(), canario_do_prompt=None, impressao=fp)
    assert out and out["janelas"] > 0
    assert detectar_vazamento("bom dia, tudo bem?", canario_do_prompt=c, impressao=fp) is None


def test_example_speech_in_quotes_is_not_fingerprinted_and_org_data_is_masked():
    assert "exemplo" not in sem_falas_de_exemplo('diga "exemplo de fala" ao lead')
    masked = mascarar_dados_da_org("funcionamos de segunda a sexta", ["de segunda a sexta"])
    assert "segunda" not in masked and "dadodaorg" in masked


def test_real_guard_composes_rules_and_checks_the_deobfuscated_copy():
    g = RealOutputGuard()
    ctx = GuardContext(allowed_domains=["minha.com"])
    assert g.evaluate("link_nao_permitido", "acesse outra ponto com", ctx) == {"links": 1}
    assert g.evaluate("link_nao_permitido", "acesse minha.com/a", ctx) is None
    rules = {"link_nao_permitido": GuardRule("bloquear"), "formato_suspeito": GuardRule("registrar", {"max_chars": 5})}
    found = g.check("veja evil.com e mais texto", ctx, rules)
    assert [(f.rule, f.policy) for f in found] == [("link_nao_permitido", "bloquear"), ("formato_suspeito", "registrar")]


def test_real_guard_leak_uses_fingerprint_canary_and_derived():
    fp = SimpleNamespace(shingle_tokens=8, shingles=fingerprint_of(PROMPT, 8).shingles)
    g = RealOutputGuard()
    assert g.evaluate("vazamento_prompt", PROMPT, GuardContext(fingerprint=fp))["janelas"] > 0
    assert g.evaluate("vazamento_prompt", "ola", GuardContext(fingerprint=fp)) is None


def test_unknown_rule_is_refused_loudly():
    for g in (RealOutputGuard(), FakeOutputGuard()):
        try:
            g.evaluate("nope", "x", GuardContext())
        except KeyError:
            continue
        raise AssertionError("unknown rule must raise")


def test_fake_and_factory_shape():
    fake = get_output_guard(fake_findings={"pii_na_resposta": {"cpf": 1}})
    assert isinstance(fake, FakeOutputGuard) and isinstance(fake, OutputGuard)
    assert isinstance(get_output_guard(), RealOutputGuard) and isinstance(RealOutputGuard(), OutputGuard)
    out = fake.check("x", GuardContext(), {"pii_na_resposta": GuardRule("bloquear")})
    assert out[0].detail == {"cpf": 1} and fake.calls == [("pii_na_resposta", "x")]


def test_redaction_is_idempotent_ordered_and_deep():
    raw = "mail a@b.com cpf 123.456.789-00 cnpj 12.345.678/0001-90 tel (11) 99999-9999 https://u:p@h.com/x"
    once = redact_pii(raw)
    assert "[REDACTED_URL_WITH_CREDS]" in once and "[REDACTED_EMAIL]" in once and "[REDACTED_CNPJ]" in once
    assert "[REDACTED_CPF]" in once and "[REDACTED_PHONE]" in once
    assert redact_pii(once) == once and count_redactions(once) >= 5  # debug tally, per-pattern as the original
    assert redact_pii("") == "" and redact_pii("sem pii") == "sem pii"
    assert redact_payload({"a": ["a@b.com", 3, {"b": None}]}) == {"a": ["[REDACTED_EMAIL]", 3, {"b": None}]}


def test_bounds():
    assert count_words("tres palavras aqui") == 3
    assert outside_word_band("um dois", 3, 5) and not outside_word_band("um dois tres", 3, 5)
    assert outside_enum(["a", "z"], {"a", "b"}) and not outside_enum(["a"], {"a", "b"})
    assert unretrieved_sources(["s1", "s9"], ["s1"]) and not unretrieved_sources(["s1"], {"s1", "s2"})
