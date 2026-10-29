"""The LEAD media path (GUARDRAILS B2 / B8): streamed size caps, no redirects, the WAHA key only to the WAHA host, no video, the media AI
budget before any AI call, masked output, SW-owned placeholders. The HTTP seam is `httpx.MockTransport`; the AI calls are a Fake subclass
that records whether it was reached."""
from __future__ import annotations

import httpx
import pytest

from app.services import media_service as ms
from app.services.media_service import (
    LEAD_AUDIO_BYTES, LEAD_IMAGEM_BYTES, LEAD_PDF_BYTES, PLACEHOLDERS_MIDIA, MediaService, MediaTooLarge, midia_recusada,
)

pytestmark = pytest.mark.asyncio
WAHA = "http://waha.internal:3000"
URL = "http://localhost:3000/api/files/default/abc.bin"


class FakeAI(MediaService):
    def __init__(self, handler, **kw):
        super().__init__(waha_base_url=WAHA, waha_api_key="waha-secret", org_id="org-1",
                         transport=httpx.MockTransport(handler), **kw)
        self.ai_calls: list[str] = []
        self.vision_prompts: list[str] = []
        self.resposta = "Tipo: documento de identidade\nResumo: um documento oficial com foto."

    async def _call_whisper(self, audio_bytes, *, filename):
        self.ai_calls.append("whisper")
        return self.resposta

    async def _call_vision(self, image_bytes, *, mimetype, prompt):
        self.ai_calls.append("vision")
        self.vision_prompts.append(prompt)
        return self.resposta

    async def _resumir_pdf_lead(self, pdf, *, prompt):
        self.ai_calls.append("pdf")
        self.vision_prompts.append(prompt)
        return self.resposta


def serve(body: bytes = b"x" * 100, headers=None, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, content=body, headers=headers or {})
    return handler


async def lead(svc, mimetype, *, url=URL, **kw):
    return await svc.resolve_inbound_lead(url=url, mimetype=mimetype, **kw)


class TestDownloadGuards:
    async def test_the_body_is_cut_off_at_the_cap_while_streaming_even_if_content_length_lies(self):
        reads = []

        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                for _ in range(10):
                    reads.append(1)
                    yield b"x" * 1024

        def handler(request):
            return httpx.Response(200, stream=Stream(), headers={"content-length": "10"})

        svc = FakeAI(handler)
        with pytest.raises(MediaTooLarge):
            await svc._download(URL, max_bytes=3000)
        assert len(reads) < 10  # stopped reading: nothing past the cap was pulled

    async def test_a_declared_length_over_the_cap_is_refused_before_reading(self):
        svc = FakeAI(serve(headers={"content-length": str(LEAD_IMAGEM_BYTES + 1)}))
        r = await lead(svc, "image/jpeg")
        assert r.estado == "recusada" and r.codigo == "grande_demais" and svc.ai_calls == []

    async def test_a_redirect_is_an_error_not_a_second_request(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://evil.example/steal"})

        svc = FakeAI(handler)
        r = await lead(svc, "image/jpeg")
        assert r.estado == "falhou" and svc.ai_calls == [] and len(seen) == 1 and "evil" not in seen[0]

    async def test_the_waha_key_goes_only_to_the_waha_host(self):
        seen = []
        svc = FakeAI(serve(seen=seen))
        await svc._download(URL)  # rewritten onto the WAHA base host
        assert seen[-1].headers.get("x-api-key") == "waha-secret" and seen[-1].url.host == "waha.internal"
        await svc._download("https://cdn.example.com/file.jpg")
        assert "x-api-key" not in seen[-1].headers and seen[-1].url.host == "cdn.example.com"
        await svc._download("http://waha.internal.evil.example:3000/x.jpg")
        assert "x-api-key" not in seen[-1].headers


class TestLeadResolution:
    async def test_video_is_never_downloaded_or_processed(self):
        seen = []
        svc = FakeAI(serve(seen=seen))
        r = await lead(svc, "video/mp4", legenda="olha")
        assert r.tipo == "video" and r.codigo == "video_desativado" and seen == [] and svc.ai_calls == []
        assert r.texto_extraido == PLACEHOLDERS_MIDIA["video_desativado"] and r.legenda == "olha"

    async def test_an_unsupported_type_and_a_missing_url_are_placeholders(self):
        svc = FakeAI(serve())
        assert (await lead(svc, "application/zip")).codigo == "tipo_nao_suportado"
        assert (await lead(svc, "image/png", url=None)).codigo == "sem_url"
        assert svc.ai_calls == []

    async def test_the_budget_is_reserved_before_the_download_and_a_refusal_makes_no_call(self):
        seen = []
        svc = FakeAI(serve(seen=seen))
        r = await lead(svc, "audio/ogg", reservar=lambda: "chat")
        assert r.codigo == "orcamento_chat" and seen == [] and svc.ai_calls == []
        assert (await lead(svc, "audio/ogg", reservar=lambda: "conexao")).codigo == "orcamento_conexao"

    async def test_the_per_type_caps_are_16mb_audio_8mb_image_10mb_pdf(self):
        assert (LEAD_AUDIO_BYTES, LEAD_IMAGEM_BYTES, LEAD_PDF_BYTES) == (16 << 20, 8 << 20, 10 << 20)
        assert (ms.LEAD_AUDIO_SEGUNDOS, ms.LEAD_PDF_PAGINAS) == (300, 3)

    async def test_audio_over_five_minutes_is_refused_without_whisper(self):
        svc = FakeAI(serve())
        r = await lead(svc, "audio/ogg", duracao_s=301)
        assert r.codigo == "audio_longo" and svc.ai_calls == []
        ok = await lead(svc, "audio/ogg", duracao_s=299)
        assert ok.estado == "ok" and svc.ai_calls == ["whisper"]

    async def test_a_pdf_over_three_pages_is_refused_without_ai(self):
        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        for _ in range(4):
            doc.new_page()
        svc = FakeAI(serve(doc.tobytes()))
        r = await lead(svc, "application/pdf")
        assert r.codigo == "pdf_paginas" and svc.ai_calls == []

    async def test_the_default_prompt_asks_for_type_and_a_non_identifying_summary_and_an_org_prompt_wins(self):
        svc = FakeAI(serve())
        await lead(svc, "image/jpeg")
        assert "TIPO" in svc.vision_prompts[0] and "NÃO identificador" in svc.vision_prompts[0]
        assert svc.vision_prompts[0] == ms.PROMPT_DOCUMENTO_LEAD_PADRAO
        await lead(svc, "image/jpeg", prompt_documento="Só o tipo do documento, nada mais, por favor.")
        assert svc.vision_prompts[1].startswith("Só o tipo")

    async def test_cpf_rg_cnh_numbers_in_the_extraction_are_masked_before_it_leaves(self):
        svc = FakeAI(serve())
        svc.resposta = "Tipo: RG\nResumo: CPF 529.982.247-25, CNH 04512345678, RG 12.345.678-9."
        r = await lead(svc, "image/jpeg")
        assert r.estado == "ok"
        for numero in ("529.982.247-25", "04512345678", "12.345.678-9"):
            assert numero not in r.texto_extraido
        assert ms.MidiaLead.para_agents(r)["texto_extraido"] == r.texto_extraido

    async def test_the_wire_shape_is_tipo_texto_extraido_legenda_and_capped_at_2000(self):
        svc = FakeAI(serve())
        svc.resposta = "Tipo: foto\nResumo: " + "a" * 5000
        r = await lead(svc, "image/jpeg", legenda="a fachada")
        wire = r.para_agents()
        assert set(wire) == {"tipo", "texto_extraido", "legenda"} and wire["tipo"] == "imagem"
        assert len(wire["texto_extraido"]) <= 2000

    async def test_a_refusal_style_vision_answer_becomes_a_placeholder_not_text(self):
        svc = FakeAI(serve())
        svc.resposta = "Desculpe, não posso ajudar com isso."
        r = await lead(svc, "image/jpeg")
        assert r.estado == "falhou" and r.texto_extraido == PLACEHOLDERS_MIDIA["falhou"]

    async def test_a_download_error_logs_the_type_only_never_the_url(self, caplog):
        def handler(request):
            raise httpx.ConnectError("boom https://secret.example/token=abc", request=request)

        svc = FakeAI(handler)
        with caplog.at_level("DEBUG"):
            r = await lead(svc, "image/jpeg")
        assert r.estado == "falhou" and "secret.example" not in caplog.text and "token=abc" not in caplog.text

    def test_a_placeholder_never_carries_agent_wording_and_has_a_closed_code(self):
        r = midia_recusada("image/png", "x.png", "bloqueado", legenda="oi")
        assert r.tipo == "imagem" and r.texto_extraido == PLACEHOLDERS_MIDIA["bloqueado"] and r.legenda == "oi"
        with pytest.raises(KeyError):
            midia_recusada("image/png", None, "inventado")
