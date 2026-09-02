"""Tests for the C1-C6 identity-resolution predicate (`identidade_service.py`).

Pure functions, no database — this module is what CAN be verified before
`048_clientes_person_layer.sql` is ever applied (contract §7: there is no
dev database). Every case here mirrors
`products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §3's table
literally, plus the edge cases the contract leaves implicit (0 named rows,
nameless-in-review, mixed leads/meta_ads_leads sources).
"""
from __future__ import annotations

import pytest

from app.services import identidade_service as ident

from app.services.identidade_service import (
    GroupClassification,
    SourceRow,
    build_clusters,
    classify_group,
    classify_names,
    leads_row_to_source,
    longest_raw_name,
    meta_lead_row_to_source,
    normalize_name,
    span,
)


def _row(nome, ocorreu_em="2026-08-01", origem="leads", origem_id="1", chave="+5511994573387"):
    return SourceRow(
        origem_tabela=origem,
        origem_id=origem_id,
        org_id="org-a",
        nome=nome,
        chave_canonica=chave,
        chave_tipo="telefone",
        ocorreu_em=ocorreu_em,
    )


# ─── normalize_name ──────────────────────────────────────────────────────


class TestNormalizeName:
    def test_lowercases(self):
        assert normalize_name("MARIA") == "maria"

    def test_strips_accents(self):
        assert normalize_name("Fátima Araújo") == "fatima araujo"

    def test_collapses_whitespace(self):
        assert normalize_name("  Maria   Silva  ") == "maria silva"

    def test_none_is_empty_string(self):
        assert normalize_name(None) == ""

    def test_blank_is_empty_string(self):
        assert normalize_name("   ") == ""

    def test_idempotent(self):
        once = normalize_name("Ana Paula Soares Franco")
        assert normalize_name(once) == once


# ─── source-row extraction ───────────────────────────────────────────────


class TestLeadsRowToSource:
    def test_maps_contato_norm_and_tipo(self):
        s = leads_row_to_source(
            {
                "id": "lead-1", "org_id": "org-a", "cliente_nome": "Ana",
                "contato_norm": "+5511994573387", "contato_tipo": "telefone",
                "data_entrada": "2026-08-01",
            }
        )
        assert s.origem_tabela == "leads"
        assert s.chave_canonica == "+5511994573387"
        assert s.chave_tipo == "telefone"
        assert s.nome == "Ana"

    def test_keyless_row_has_no_chave_and_no_tipo(self):
        """contato_tipo can still say 'telefone' for an unparseable value
        with no contato_norm (leads_service._derive_contato_fields) — that
        is NOT a usable key and must not leak through as chave_tipo."""
        s = leads_row_to_source(
            {
                "id": "lead-2", "org_id": "org-a", "cliente_nome": "Bob",
                "contato_norm": None, "contato_tipo": "telefone",
                "data_entrada": "2026-08-01",
            }
        )
        assert s.chave_canonica is None
        assert s.chave_tipo is None


class TestContactDataIsCarriedApartFromTheKey:
    """🔴 The person's CONTACT DATA is not the identity KEY.

    Only one contact can be canonical, so a source carrying both a phone and
    an email loses one when resolution picks a winner — and a KEYLESS row
    loses both, even with a phone sitting in the column. That is what shipped:
    `clientes.celular`/`.email` were never written, so the card showed "—"
    and `stage_gate` refused every move because the checklist had nothing to
    tick.
    """

    def test_keyless_lead_still_carries_its_phone(self):
        """The reported bug: a lead whose contact never normalised still has
        the number the operator typed, and the card must show it."""
        s = leads_row_to_source({
            "id": "lead-3", "org_id": "org-a", "cliente_nome": "José Roberto",
            "contato": "+5511999978888", "contato_norm": None,
            "contato_tipo": "telefone", "data_entrada": "2026-09-02",
        })
        assert s.chave_canonica is None, "still keyless — that half is unchanged"
        assert s.telefone == "+5511999978888"

    def test_keyed_lead_prefers_the_normalised_value(self):
        s = leads_row_to_source({
            "id": "lead-4", "org_id": "org-a", "cliente_nome": "Ana",
            "contato": "11 99457-3387", "contato_norm": "+5511994573387",
            "contato_tipo": "telefone", "data_entrada": "2026-08-01",
        })
        assert s.telefone == "+5511994573387"
        assert s.email is None

    def test_email_lead_carries_email_not_phone(self):
        s = leads_row_to_source({
            "id": "lead-5", "org_id": "org-a", "cliente_nome": "Ana",
            "contato": "Ana@Example.COM", "contato_norm": "ana@example.com",
            "contato_tipo": "email", "data_entrada": "2026-08-01",
        })
        assert s.email == "ana@example.com"
        assert s.telefone is None

    def test_meta_lead_keeps_the_email_the_key_discarded(self):
        """A campaign lead routinely supplies both; the phone wins the key, so
        the email would vanish entirely if it were not carried separately."""
        s = meta_lead_row_to_source({
            "id": "m-1", "org_id": "org-a", "full_name": "Ana Lima",
            "phone": "+5511996019031", "email": "Analu.Moreira@Gmail.com",
            "created_time": "2026-08-01T00:00:00Z",
        })
        assert s.chave_canonica == "+5511996019031"
        assert s.telefone == "+5511996019031"
        assert s.email == "analu.moreira@gmail.com"


class TestMetaLeadRowToSource:
    def test_phone_wins_over_email(self):
        s = meta_lead_row_to_source(
            {
                "id": "meta-1", "org_id": "org-a", "full_name": "Ana",
                "phone": "+5511994573387", "email": "ana@example.com",
                "created_time": "2026-08-01T10:00:00+00:00",
            }
        )
        assert s.chave_canonica == "+5511994573387"
        assert s.chave_tipo == "telefone"

    def test_email_used_when_no_phone(self):
        s = meta_lead_row_to_source(
            {
                "id": "meta-2", "org_id": "org-a", "full_name": "Ana",
                "phone": None, "email": "Ana@Example.COM",
                "created_time": "2026-08-01T10:00:00+00:00",
            }
        )
        assert s.chave_canonica == "ana@example.com"
        assert s.chave_tipo == "email"

    def test_no_contact_is_keyless(self):
        s = meta_lead_row_to_source(
            {"id": "meta-3", "org_id": "org-a", "full_name": "Ana", "phone": None, "email": None}
        )
        assert s.chave_canonica is None
        assert s.chave_tipo is None


# ─── classify_names / classify_group — the C1-C6 table ──────────────────


class TestC1IdenticalNames:
    def test_all_identical(self):
        motivo, auto_merge = classify_names(["Ana Paula", "Ana Paula", "ANA PAULA"])
        assert motivo == "C1"
        assert auto_merge is True

    def test_single_row(self):
        motivo, auto_merge = classify_names(["Ana"])
        assert motivo == "C1"
        assert auto_merge is True

    def test_all_nameless_is_vacuous_c1(self):
        """No names anywhere in the group -- nothing to disagree about.
        A genuine interpretation call (the contract's table doesn't name
        this case), documented in identidade_service's module docstring."""
        motivo, auto_merge = classify_names([None, None])
        assert motivo == "C1"
        assert auto_merge is True


class TestC2PrefixCompatible:
    def test_shorter_is_a_token_prefix(self):
        motivo, auto_merge = classify_names(["Maria Silva", "Maria"])
        assert motivo == "C2"
        assert auto_merge is True

    def test_three_token_prefix(self):
        motivo, auto_merge = classify_names(["Ana Paula Soares Franco", "Ana Paula"])
        assert motivo == "C2"

    def test_raw_substring_is_not_a_token_prefix(self):
        """"Mari" is a character-prefix of "Maria" but not a token prefix
        -- must NOT be treated as compatible."""
        motivo, auto_merge = classify_names(["Mari", "Maria"])
        assert motivo != "C2"
        assert auto_merge is False


class TestC3NamelessRidesAlong:
    def test_one_named_cluster_plus_nameless(self):
        motivo, auto_merge = classify_names(["Ana", None, "Ana"])
        assert motivo == "C3"
        assert auto_merge is True

    def test_two_prefix_compatible_plus_nameless(self):
        motivo, auto_merge = classify_names(["Maria Silva", "Maria", None])
        assert motivo == "C3"
        assert auto_merge is True


class TestC4SameFirstTokenDiverging:
    def test_same_first_name_different_surname(self):
        motivo, auto_merge = classify_names(["Maria Silva", "Maria Souza"])
        assert motivo == "C4"
        assert auto_merge is False


class TestC5GenuinelyDifferent:
    def test_two_unrelated_names(self):
        """The Carmen Real Dias / Luana Batista shared-phone case from the
        roadmap."""
        motivo, auto_merge = classify_names(["Carmen Real Dias", "Luana Batista"])
        assert motivo == "C5"
        assert auto_merge is False


class TestC6ThreeOrMoreDistinct:
    def test_three_distinct_names(self):
        motivo, auto_merge = classify_names(["Ana", "Bob", "Carla"])
        assert motivo == "C6"
        assert auto_merge is False

    def test_four_distinct_names_still_c6(self):
        motivo, auto_merge = classify_names(["Ana", "Bob", "Carla", "Dario"])
        assert motivo == "C6"


# ─── classify_group -- named_clusters + has_nameless bookkeeping ────────


class TestClassifyGroup:
    def test_named_clusters_groups_rows_by_normalized_name(self):
        rows = [_row("Maria Silva", origem_id="1"), _row("Maria", origem_id="2"), _row("maria SILVA", origem_id="3")]
        result = classify_group(rows)
        assert isinstance(result, GroupClassification)
        assert result.motivo == "C2"
        assert set(result.named_clusters) == {"maria silva", "maria"}
        assert len(result.named_clusters["maria silva"]) == 2

    def test_has_nameless_true_when_any_row_nameless(self):
        rows = [_row("Ana", origem_id="1"), _row(None, origem_id="2")]
        result = classify_group(rows)
        assert result.has_nameless is True

    def test_has_nameless_false_when_all_named(self):
        rows = [_row("Ana", origem_id="1"), _row("Ana", origem_id="2")]
        result = classify_group(rows)
        assert result.has_nameless is False

    def test_empty_group_raises(self):
        import pytest

        with pytest.raises(ValueError):
            classify_group([])


# ─── build_clusters -- row assignment, separate from classification ─────


class TestBuildClusters:
    def test_auto_merge_folds_everything_into_one_cluster(self):
        rows = [_row("Maria Silva", origem_id="1"), _row("Maria", origem_id="2"), _row(None, origem_id="3")]
        classification = classify_group(rows)
        assert classification.auto_merge is True
        clusters = build_clusters(rows, classification)
        assert list(clusters.keys()) == [None]
        assert len(clusters[None]) == 3

    def test_review_splits_named_clusters_and_a_nameless_one(self):
        rows = [
            _row("Carmen Real Dias", origem_id="1"),
            _row("Luana Batista", origem_id="2"),
            _row(None, origem_id="3"),
        ]
        classification = classify_group(rows)
        assert classification.motivo == "C5"
        clusters = build_clusters(rows, classification)
        assert set(clusters) == {"carmen real dias", "luana batista", None}
        assert len(clusters[None]) == 1

    def test_review_without_nameless_rows_has_no_none_cluster(self):
        rows = [_row("Ana", origem_id="1"), _row("Bob", origem_id="2"), _row("Carla", origem_id="3")]
        classification = classify_group(rows)
        clusters = build_clusters(rows, classification)
        assert None not in clusters
        assert len(clusters) == 3


# ─── longest_raw_name / span ─────────────────────────────────────────────


class TestLongestRawName:
    def test_picks_the_longest_variant(self):
        rows = [_row("Paula", "2026-01-01"), _row("Ana Paula Soares Franco", "2026-01-02")]
        assert longest_raw_name(rows) == "Ana Paula Soares Franco"

    def test_all_nameless_returns_none(self):
        rows = [_row(None), _row(None)]
        assert longest_raw_name(rows) is None

    def test_ties_keep_first_encountered(self):
        rows = [_row("AAAA", "2026-01-01"), _row("BBBB", "2026-01-02")]
        assert longest_raw_name(rows) == "AAAA"


class TestSpan:
    def test_earliest_and_latest(self):
        earliest, latest = span(["2026-08-05", "2026-08-01", "2026-08-10"])
        assert earliest == "2026-08-01"
        assert latest == "2026-08-10"

    def test_bare_date_vs_full_timestamp_same_day(self):
        """A bare-date row must not lose to a same-day timestamp purely
        because it's a shorter string."""
        earliest, latest = span(["2026-08-01", "2026-08-01T23:00:00+00:00"])
        assert earliest == "2026-08-01"
        assert latest == "2026-08-01T23:00:00+00:00"

    def test_single_value(self):
        earliest, latest = span(["2026-08-01"])
        assert earliest == latest == "2026-08-01"

    def test_empty_raises(self):
        import pytest

        with pytest.raises(ValueError):
            span([])


class TestNormalizacaoAmpliada:
    """Punctuation and origin-marker folding — widened 2026-08-25.

    Every input here is a REAL pair taken from the live review queue, not an
    invented one. They were 351 groups of manual work; these are the ones that
    were never a disagreement about who the person is.
    """

    @pytest.mark.parametrize(
        "a,b",
        [
            ("alex sandro", "alex sandro*"),
            ("alessandro biasi", "alessandro biasi*"),
            ("julia eloy", "julia eloy*"),
            ("simone solla", "simone solla*"),
            ("nei nunes", "nei_nunes"),
            ("ricardo santos", "ricardo.santos"),
            ("hp luiza", "luiza"),
            ("morgana", "retono morgana"),
            ("adilaine pavan", "v4 adilaine pavan"),
            ("geanny bezerra", "prof geanny bezerra"),
        ],
    )
    def test_these_normalize_to_the_same_person(self, a, b):
        assert ident.normalize_name(a) == ident.normalize_name(b)
        motivo, auto = ident.classify_names([a, b])
        assert auto is True, f"{a!r}/{b!r} still lands in the review queue ({motivo})"

    @pytest.mark.parametrize(
        "a,b",
        [
            # Spelling variants — probably the same person, and NOTHING in the
            # letters proves it. A human decides.
            ("elisabeth", "elizabeth"),
            ("erick", "erik"),
            ("william", "willian"),
            ("jennifer", "jenniffer"),
            # Two people sharing a phone. Merging these destroys records.
            ("fernanda", "lucilene ferreira alves"),
            ("jardel", "rodney cassemiro"),
            ("amanda", "wemerson silva"),
        ],
    )
    def test_these_still_need_a_human(self, a, b):
        _motivo, auto = ident.classify_names([a, b])
        assert auto is False, (
            f"{a!r}/{b!r} was auto-merged — the normalization got greedy and "
            "is now folding together names that only a person can judge"
        )

    def test_a_handle_tagline_is_not_part_of_the_name(self):
        """Instagram display names carry a profession after a bar. Two rows in
        the live queue were the same person split by exactly that."""
        assert ident.normalize_name(
            "Rose Oliveira | Nutricionista Oncológica"
        ) == ident.normalize_name("Rose Oliveira")
        assert ident.normalize_name(
            "Ataiana Kempner | Advogada"
        ) == ident.normalize_name("Ataiana Kempner")

    def test_a_leading_bar_does_not_erase_the_name(self):
        """🔴 `|Maria Veiga` has nothing BEFORE the bar. Truncating there would
        turn a named row into a nameless one, which then rides along with
        whatever else shares the phone — a far stronger claim than any of this
        is entitled to make."""
        assert ident.normalize_name("|MAria Veiga") == "maria veiga"

    def test_a_marker_alone_is_not_stripped_to_nothing(self):
        """"Lead" as the whole name stays a name. Emptying it would silently
        promote the row to nameless, which rides along with whatever else is
        in the group — a much bigger claim than "this has a prefix"."""
        assert ident.normalize_name("Lead") == "lead"
        assert ident.normalize_name("HP") == "hp"

    def test_a_marker_in_the_middle_of_a_name_survives(self):
        """"de" is a marker at the edge and a name particle in the middle."""
        assert ident.normalize_name("Ana de Souza") == "ana de souza"
        assert ident.normalize_name("de lead Ana de Souza") == "ana de souza"

    def test_punctuation_becomes_a_separator_not_a_deletion(self):
        """`nei_nunes` must become two tokens matching `nei nunes`, not one
        glued `neinunes` that matches nothing."""
        assert ident.normalize_name("nei_nunes") == "nei nunes"
        assert ident.normalize_name("ju cantowitz +") == "ju cantowitz"

    def test_accent_form_does_not_split_a_person(self):
        """One row carried a combining acute, the other a precomposed í."""
        combinado = "Thai" + "\u0301" + "s Lima"
        assert ident.normalize_name(combinado) == ident.normalize_name("Thaís Lima")
