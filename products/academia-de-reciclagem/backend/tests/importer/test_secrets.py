"""Tests for `app/importer/secrets.py` — the content secret scan."""
from app.importer.secrets import scan_content


class TestKnownPatterns:
    def test_stripe_secret_key(self):
        assert scan_content("here is a key sk-abcdefghijklmnop1234567890 inline") is True

    def test_stripe_publishable_key(self):
        assert scan_content("pk_live_ABCDEFGHIJ1234567890abcdefgh") is True

    def test_github_pat(self):
        assert scan_content("token: ghp_1234567890abcdefghijklmnopqrstuvwx") is True

    def test_aws_access_key_id(self):
        assert scan_content("AKIAABCDEFGHIJKLMNOP") is True

    def test_pem_private_key_header(self):
        assert scan_content("-----BEGIN RSA PRIVATE KEY-----\nMIIB...") is True

    def test_short_prefix_alone_is_not_a_match(self):
        # "pk_" / "sk-" with too few trailing chars should not trip —
        # avoids flagging incidental short substrings.
        assert scan_content("sk-8 e pk_2 sao valores de exemplo") is False


class TestEntropyHeuristic:
    def test_random_looking_long_token_flagged(self):
        token = "x9J2kLmQ8pZ7vN4rT1sW6yU3bH0dF5gA7cE1nR6"
        assert scan_content(f"segredo encontrado: {token}") is True

    def test_hex_looking_long_token_flagged(self):
        token = "3f9a1c2e7b8d4f6a0c5e2b9d7f1a4c8e6b3d0f9a2c7e5b1d8f4a6c0e3b7d9f2a"
        assert scan_content(token) is True


class TestFalsePositives:
    """§B.6 explicitly requires this scan not to fire on ordinary PT-BR
    prose — including the long hyphenated compound phrases/slugs that
    are common in this knowledge base.
    """

    def test_plain_ptbr_sentence(self):
        content = (
            "A reciclagem de materiais organicos e inorganicos exige "
            "atencao especial ao descarte correto de residuos solidos "
            "urbanos conforme a legislacao vigente no Brasil."
        )
        assert scan_content(content) is False

    def test_long_hyphenated_ptbr_slug(self):
        content = (
            "conforme-a-politica-nacional-de-residuos-solidos-e-a-lei-"
            "12305-de-2010-sobre-logistica-reversa-obrigatoria"
        )
        assert scan_content(content) is False

    def test_multiple_hyphenated_slugs_in_one_document(self):
        content = "\n".join(
            [
                "# Dominio regulatorio",
                "",
                "Ver dominio-regulatorio-pnrs e logistica-reversa-obrigatoria-",
                "para-fabricantes-e-importadores-conforme-normas-ambientais.",
                "",
                "Outro tema: a-reciclagem-de-materiais-organicos-e-inorganicos-",
                "no-brasil-contemporaneo-e-seus-desafios-logisticos.",
            ]
        )
        assert scan_content(content) is False

    def test_markdown_table_of_decisions_is_clean(self):
        content = (
            "| # | Decisão | Motivo |\n"
            "|---|---|---|\n"
            "| D-01 | Usar Supabase para persistencia | Reduz custo operacional |\n"
            "| D-02 | Adotar RLS por organizacao | Isola dados entre clientes |\n"
        )
        assert scan_content(content) is False
