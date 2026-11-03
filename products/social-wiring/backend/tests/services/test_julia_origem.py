"""Julia contact origin: the resolver precedence (a-d), the CTWA referral parse, first-write-wins, and the
agents contexto reading it back (`estado.origem.canal_origem`)."""
from __future__ import annotations

from uuid import UUID, uuid4

from noctusai_lib.testing import MockSupabaseClient

from app.services import julia_contatos_service as contatos
from app.services import julia_origem_service as origem
from app.services.julia_contexto_service import ContextoCtx, _prov_estado

ORG = UUID("00000000-0000-4000-8000-0000000000a1")
CONN = uuid4()
TEL = "+5511988887777"


def _sw():
    return MockSupabaseClient().schema("social_wiring")


def _seed(sw, table, **row):
    full = {"id": str(uuid4()), "org_id": str(ORG), **row}
    sw.table(table).insert(full).execute()
    return full


def _fonte(sw, slug):
    row = {"id": str(uuid4()), "org_id": str(ORG), "slug": slug, "label": slug, "categoria": "portal", "ordem": 0}
    sw.table("lead_sources").insert(row).execute()
    return row["id"]


def _ctwa_body(**ad):
    reply = {"sourceType": "ad", "sourceId": "AD123", "sourceUrl": "https://fb.me/x", "title": "Casa 3 quartos",
             "ctwaClid": "clid", **ad}
    return {"event": "message", "payload": {"_data": {"message": {"extendedTextMessage": {"contextInfo": {"externalAdReply": reply}}}}}}


class TestReferralParse:
    def test_present(self):
        ref = origem.extrair_referral_ctwa(_ctwa_body())
        assert ref == {"source_id": "AD123", "source_type": "ad", "source_url": "https://fb.me/x", "title": "Casa 3 quartos"}

    def test_present_on_a_media_message(self):
        body = {"payload": {"_data": {"message": {"imageMessage": {"contextInfo": {"externalAdReply": {"sourceType": "ad", "sourceId": 77}}}}}}}
        assert origem.extrair_referral_ctwa(body)["source_id"] == "77"

    def test_normalized_referral(self):
        body = {"payload": {"referral": {"source_type": "ad", "source_id": "9", "headline": "H"}}}
        assert origem.extrair_referral_ctwa(body) == {"source_id": "9", "source_type": "ad", "source_url": None, "title": "H"}

    def test_absent(self):
        assert origem.extrair_referral_ctwa({"payload": {"body": "oi"}}) is None
        assert origem.extrair_referral_ctwa({"payload": {"_data": {"message": {"conversation": "oi"}}}}) is None

    def test_link_preview_is_not_an_ad(self):
        assert origem.extrair_referral_ctwa(_ctwa_body(sourceType="url", ctwaClid=None)) is None

    def test_malformed_never_raises(self):
        for body in (None, [], "x", {"payload": "x"}, {"payload": {"_data": []}}, {"payload": {"_data": {"message": {"a": 1}}}},
                     {"payload": {"_data": {"message": {"a": {"contextInfo": {"externalAdReply": "x"}}}}}},
                     {"payload": {"referral": "x"}}, _ctwa_body(sourceId=None), _ctwa_body(sourceId={"a": 1})):
            assert origem.extrair_referral_ctwa(body) is None


class TestResolver:
    def test_a_explicit_meta_lead_uses_its_crm_lead_source(self):
        sw = _sw()
        sid = _fonte(sw, "meta-lead-ads")
        lead = _seed(sw, "leads", meta_lead_id="ml-1", origem_id=sid, contato_norm=TEL)
        ml = {"id": "ml-1", "campaign_name": "C10023", "campaign_id": "99", "ad_id": "AD9"}
        got = origem.resolver_origem(sw, ORG, meta_lead=ml, referral={"source_id": "X"}, telefone=TEL)
        assert (got["origem_slug"], got["campanha_origem"], got["anuncio_origem"]) == ("meta-lead-ads", "C10023", "AD9")
        assert got["lead_id"] == lead["id"]

    def test_a_without_crm_lead_falls_back_to_the_ingest_slug(self):
        got = origem.resolver_origem(_sw(), ORG, meta_lead={"id": "ml-2", "campaign_id": "99"})
        assert got["origem_slug"] == "meta-lead-ads" and got["campanha_origem"] == "99"

    def test_b_ctwa_referral_beats_phone_match(self):
        sw = _sw()
        _seed(sw, "meta_ads_leads", id="ml-0", ad_id="AD123", campaign_name="Campanha Casas")
        sid = _fonte(sw, "zap")
        _seed(sw, "leads", origem_id=sid, contato_norm=TEL)
        got = origem.resolver_origem(sw, ORG, referral=origem.extrair_referral_ctwa(_ctwa_body()), telefone=TEL)
        assert (got["origem_slug"], got["anuncio_origem"], got["campanha_origem"]) == ("meta-ctwa", "AD123", "Campanha Casas")
        assert any(r["slug"] == "meta-ctwa" for r in sw.table("lead_sources").select("*").execute().data)

    def test_b_ctwa_without_known_campaign_leaves_it_null(self):
        got = origem.resolver_origem(_sw(), ORG, referral={"source_id": "AD1"})
        assert got["origem_slug"] == "meta-ctwa" and got["campanha_origem"] is None and got["anuncio_origem"] == "AD1"

    def test_c_phone_match_uses_the_leads_source_and_links_it(self):
        sw = _sw()
        sid = _fonte(sw, "imovel-web")
        lead = {"id": str(uuid4()), "org_id": str(ORG), "origem_id": sid, "contato_norm": TEL}
        sw.table("leads").insert(lead).execute()
        got = origem.resolver_origem(sw, ORG, telefone=TEL)
        assert got["origem_slug"] == "imovel-web" and got["lead_id"] == lead["id"]
        assert got["campanha_origem"] is None and got["anuncio_origem"] is None

    def test_c_phone_match_of_a_meta_lead_brings_campaign_and_ad(self):
        sw = _sw()
        sid = _fonte(sw, "meta-lead-ads")
        _seed(sw, "leads", origem_id=sid, meta_lead_id="ml-5", contato_norm=TEL)
        _seed(sw, "meta_ads_leads", id="ml-5", campaign_name="Camp", ad_id="AD5")
        got = origem.resolver_origem(sw, ORG, telefone=TEL)
        assert (got["origem_slug"], got["campanha_origem"], got["anuncio_origem"]) == ("meta-lead-ads", "Camp", "AD5")

    def test_d_direct(self):
        got = origem.resolver_origem(_sw(), ORG, telefone=TEL)
        assert got == {"origem_slug": "whatsapp", "campanha_origem": None, "anuncio_origem": None,
                       "codigo_imovel_campanha": None, "lead_id": None}


class TestFirstWriteWins:
    def _criar(self, sw, origem_arg):
        return contatos.obter_ou_criar_contato(sw, org_id=ORG, connection_id=CONN, chat_id="c1", telefone_e164=TEL, origem=origem_arg)

    def test_written_on_create_and_never_overwritten(self):
        sw = _sw()
        row = self._criar(sw, {"origem_slug": "meta-ctwa", "anuncio_origem": "AD1"})
        assert row["origem_slug"] == "meta-ctwa"
        again = self._criar(sw, lambda: (_ for _ in ()).throw(AssertionError("must not resolve when origin is set")))
        assert again["origem_slug"] == "meta-ctwa" and again["anuncio_origem"] == "AD1"
        later = self._criar(sw, {"origem_slug": "zap", "anuncio_origem": "OTHER"})
        assert later["origem_slug"] == "meta-ctwa"
        stored = contatos.buscar_contato(sw, ORG, CONN, "c1")
        assert stored["origem_slug"] == "meta-ctwa" and stored["anuncio_origem"] == "AD1"

    def test_existing_contact_without_origin_is_filled_on_next_inbound(self):
        sw = _sw()
        self._criar(sw, None)
        assert contatos.buscar_contato(sw, ORG, CONN, "c1").get("origem_slug") is None
        filled = self._criar(sw, lambda: {"origem_slug": "whatsapp"})
        assert filled["origem_slug"] == "whatsapp"
        assert contatos.buscar_contato(sw, ORG, CONN, "c1")["origem_slug"] == "whatsapp"


def test_contexto_canal_origem_is_populated():
    sw = _sw()
    row = contatos.obter_ou_criar_contato(sw, org_id=ORG, connection_id=CONN, chat_id="c9", telefone_e164=TEL,
                                          origem=lambda: origem.resolver_origem(sw, ORG, referral={"source_id": "AD1"}))
    estado = _prov_estado(ContextoCtx(client=sw, org_id=ORG, contato=row))["estado"]
    assert estado["origem"]["canal_origem"] == "meta-ctwa"
