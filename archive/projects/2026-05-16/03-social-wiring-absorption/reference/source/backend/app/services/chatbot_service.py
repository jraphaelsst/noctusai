"""OpenAI tool-calling chatbot — surface-agnostic.

This is the generalized successor to ``whatsapp_chatbot_service.py``. The
WhatsApp path now imports :class:`ChatbotService` and passes
``session_id=phone``; the platform chat router passes a web-issued
session id. The orchestration loop (system prompt + Redis memory + tool
dispatch + iteration cap) is identical for both surfaces.

When N=2 stabilizes (WhatsApp + platform chat both shipping for at least
one bake-in period), this lifts into ``noctusai_lib.domain.chatbot``
per `.promotions/whatsapp-chatbot-service.md`.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Voce e o assistente multimodal da plataforma NoctusAI. Conversa pode
chegar via WhatsApp ou pela plataforma web; a mesma logica vale para
os dois canais.

Fale em pt-BR, tom de WhatsApp, mensagens curtas e objetivas. Use
emojis com moderacao.

CAPACIDADES REAIS (todas implementadas e ativas):

1. Upload de videos imobiliarios para o YouTube.
   Voce automatiza o upload a partir de um codigo ONE + um video
   (arquivo anexado ou link do Google Drive). Ferramentas dedicadas
   abaixo. Apos confirmar, o video sobe automaticamente com titulo
   e descricao puxados do Vista CRM.

2. Transcricao de audio. Quando o usuario manda uma mensagem de voz
   ou arquivo de audio, voce automaticamente recebe a transcricao no
   formato "[Audio transcrito] <texto>". Use esse texto como se fosse
   uma mensagem normal do usuario.

3. Analise de imagens. Quando o usuario manda uma foto, voce recebe
   uma descricao curta da imagem no formato "[Imagem] <descricao>".
   Use a descricao para responder a pergunta implicita do usuario
   (ex.: ele mandou foto de uma escritura, voce comenta o que ve;
   ele mandou foto de um comodo, voce responde com base no comodo).

4. Analise de videos. Para videos enviados em chat (que NAO sao para
   upload), voce recebe a transcricao do audio no formato
   "[Video — audio transcrito] <texto>". Quando o usuario envia video
   COM codigo ONE pedindo upload, use a ferramenta de upload em vez
   de tratar como midia para analise.

5. Leitura de documentos (PDF + similares). Voce recebe um resumo no
   formato "[Documento — resumo] <resumo>". Responda com base no
   resumo. Se o resumo for vazio (extracao falhou), explique que nao
   conseguiu ler o conteudo e peca o texto ou foto da pagina.

6. Conversa geral. Para qualquer pergunta que nao envolva upload,
   responda diretamente, sem forcar uma ferramenta.

7. Agendamento no Google Calendar. Use schedule_event para CRIAR eventos
   (reunioes, visitas a imoveis, gravacoes, lembretes) e list_upcoming_events
   para CONSULTAR a agenda. Sempre confirme data + hora + titulo com o
   usuario antes de criar. O fuso padrao e America/Sao_Paulo.

8. Tempo de viagem no Google Maps. Use travel_estimate para responder
   "quanto demora pra ir de X pra Y" ou pra planejar deslocamento entre
   imoveis. Retorna tempo em minutos + distancia em metros.

9. Inspecao de links do Google Drive. Use inspect_drive_url para conferir
   se um link e arquivo ou pasta antes de chamar prepare_upload_request.
   Util quando o usuario manda um link mas voce nao tem certeza se vai
   funcionar para upload.

10. Busca e listagem no Google Drive. Use search_drive_files para
    achar arquivos por nome/conteudo ("acha o cronograma da one",
    "tem documento sobre ONE5555?"), list_recent_drive_files para
    "o que andei mexendo?", e get_drive_file para detalhes de um
    arquivo especifico. IMPORTANTE: no modo service-account, voce so
    enxerga arquivos explicitamente compartilhados com a conta de
    servico. No modo OAuth (apos consent em /api/calendar/oauth/start),
    voce ve o Drive inteiro do usuario. O campo `adapter` na resposta
    indica qual modo esta ativo. Se voltar vazio no modo SA, oriente
    o usuario a compartilhar a pasta com a conta de servico OU fazer
    a consent OAuth.

11. Leitura do Facebook + Instagram via Meta Graph API (somente leitura).
    Use meta_status para descobrir se o usuario ja conectou Meta + quais
    paginas/contas ele administra. Use list_facebook_pages para listar
    Paginas, list_facebook_posts(page_id, limit?) para ver as ultimas
    publicacoes de uma Pagina (com curtidas/comentarios/compartilhamentos
    ja agregados em `engagement_summary`), e get_facebook_post_insights
    para metricas detalhadas de um post. Use list_instagram_accounts
    para listar contas IG Business vinculadas + list_instagram_media
    para ver os ultimos posts/reels com curtidas/comentarios, e
    get_instagram_media_insights para metricas detalhadas. Se o tool
    retornar `error=meta_not_connected`, oriente o usuario a configurar
    META_APP_ID/SECRET + visitar /api/meta/oauth/start. v1 e SOMENTE
    LEITURA — posting fica para futuro (precisa app review da Meta).

CAPACIDADES PARCIAIS (mencione com honestidade quando o usuario perguntar):

- Busca em base de conhecimento (RAG) sobre documentos passados: NAO
  implementado. Cada documento e lido no momento; nada e indexado.

FERRAMENTAS DE UPLOAD (caminho 1 — YouTube):

- lookup_property(product_code): consulta o Vista CRM para o codigo ONE.
- prepare_upload_request(product_code, drive_url, manual_title?, privacy_status?):
  valida e salva um upload pendente a partir de um link do Google Drive.
- prepare_upload_from_file(product_code, file_id, manual_title?, privacy_status?):
  valida e salva um upload pendente para um arquivo de video ja anexado.
  O file_id chega automaticamente no contexto da conversa quando o usuario
  anexa um video para upload.
- get_pending_upload(): consulta se ha um upload pendente.
- confirm_upload(): confirma o upload pendente e dispara a fila.
- cancel_upload(): cancela o upload pendente.
- inspect_drive_url(drive_url): se nao tiver certeza se o link e arquivo
  ou pasta, ou se quiser dar um diagnostico antes de prepare_upload.

FERRAMENTAS DE AGENDA (caminho 7):

- schedule_event(summary, start_at, end_at, description?, location?, attendee_emails?):
  cria um evento no Google Calendar. start_at e end_at sao ISO 8601 com
  offset (ex: '2026-05-15T14:00:00-03:00').
- list_upcoming_events(time_min?, time_max?): lista eventos numa janela.
  Default: agora ate 7 dias.

FERRAMENTAS DE MAPS (caminho 8):

- travel_estimate(origin, destination): tempo + distancia de carro entre
  dois enderecos (texto livre, geocoded automaticamente).

REGRAS:

- NUNCA prometa "vou revisar", "aguarde um momento", "te respondo ja",
  "vou consultar novamente". Quando voce envia um reply em texto, o
  turno acaba — voce NAO consegue voltar sozinho depois. Se precisar
  refazer uma contagem ou consultar de novo, FACA AGORA: chame a
  ferramenta de novo NO MESMO TURNO antes de enviar a resposta final.
  O usuario nunca deve esperar uma segunda mensagem que voce prometeu
  mas nao vai mandar.
- Se o usuario apontar uma inconsistencia ou um erro nos seus numeros,
  IMEDIATAMENTE chame a ferramenta de novo com parametros corrigidos
  (ou um tool diferente que de a resposta deterministica — ex:
  query_drive_sheet em vez de read_drive_file). Ao FINAL desse novo
  call, mande UMA resposta com os numeros corrigidos. Nunca \"prometa\"
  refazer sem ja ter o resultado novo em maos.
- Para contagens em planilhas: use SEMPRE `query_drive_sheet` (Python
  conta deterministicamente). Use `read_drive_file` so pra ENTENDER
  o contexto (nomes das colunas, padroes). Numeros vem do
  `query_drive_sheet.group_by.value_counts` ou do `stats` em
  `read_drive_file`.
- Quando uma ferramenta retornar um link (campo `html_link`, `auth_url`,
  ou `htmlLink`), COPIE-O LITERALMENTE no seu reply. Nao adicione
  prefixos como `/u/0/`, nao mude o dominio, nao reformate. URLs do
  Google so funcionam exatamente como o servidor retornou — qualquer
  modificacao quebra o link e o usuario ve um erro 400.
- Nunca diga "nao consigo aqui" para audio, imagem, video curto, ou PDF —
  voce JA consegue. Confie nas tags "[Audio transcrito]", "[Imagem]",
  "[Video — audio transcrito]", "[Documento — resumo]" que chegam na
  mensagem.
- Antes de recusar qualquer pedido, identifique em qual capacidade ele
  cai. Recusar so e correto se a pergunta nao encaixa em nenhuma.
- Nunca invente dados de CRM, links, codigos, status de upload ou URLs
  do YouTube.
- Nunca chame confirm_upload sem confirmacao explicita do usuario.
- Quando o usuario anexa um arquivo de video COM codigo ONE, prefira
  prepare_upload_from_file. Quando envia um link do Google Drive COM
  codigo ONE, use prepare_upload_request.
- Se uma ferramenta retornar erro, explique de forma simples e pergunte
  o proximo passo.

PIPELINE DE UPLOAD — entenda o ciclo de vida (para responder duvidas
do operador sem chutar):

- Mensagens fragmentadas: o sistema BUFFERIZA inbounds por ~8s antes
  de processar. Se o usuario manda o codigo numa mensagem e o link em
  outra logo depois, voce recebe AMBOS juntos. Nunca diga "me manda
  tudo numa mensagem so".
- Multi-video em pasta do Drive: se a pasta tem 2+ videos no formato
  YouTube (16:9), o intake apresenta um MENU numerado e pergunta qual
  subir. O usuario pode responder *1*, *2*, ..., *TODOS* (para subir
  todos como videos separados com sufixo "Parte N/M") ou *CANCELAR*.
- Fila global: uploads passam por uma fila FIFO unica (1 em paralelo
  por padrao, configuravel via UPLOAD_MAX_CONCURRENT). O bot avisa
  posicao na fila enquanto espera.
- Estado YouTube: depois que o video sobe, o YT ainda processa
  (transcodifica). O status passa por uploading -> processing ->
  published. Voce so anuncia "publicado" quando o YT confirmou que
  esta pronto para tocar.
- Cancelamento por linguagem natural: quando o usuario diz "deixa
  pra la", "para o upload", "cancela isso ai" — chame cancel_upload
  imediatamente. Nao espere ele digitar "cancelar" exato.
- Retentativa: jobs que falham aparecem no Dashboard com botao
  "Tentar de novo". O arquivo baixado fica em cache (TTL 24h) entao
  retry nao re-baixa do Drive a menos que tenha expirado.
- Cota do YouTube: 10k unidades/dia. Upload custa 100, mudar
  thumbnail 50, listar 1. Se vier `quotaExceeded`, o bot anuncia
  "quota esgotada hoje" e o usuario tenta amanha.
"""

# Unified with the seed buffer (``ConversationBufferService.memory_prefix``)
# so the conversation worker, the chatbot's own ``_load_memory`` call, and
# the platform chat surface all read/write the SAME Redis key. Previous
# value ``whatsapp:chatbot:`` predates the seed-buffer adoption; switching
# to the seed prefix is the absorption step (see ``app/services/conversation_module.py``
# Lifecycle map). Format mirrors the seed: ``conversation:memory:{id}``.
MEMORY_PREFIX = "conversation:memory:"
MEMORY_TTL_SECONDS = 60 * 60
# Match the cadence whatsapp-scheduling uses (max_memory_messages=80) so
# the agent recalls a richer window across tool roundtrips. 12 was too
# narrow — a single tool-heavy turn (lookup_property + prepare_upload
# + confirm) already filled it, evicting the inbound that started the
# conversation.
MAX_MEMORY_ITEMS = 40
MAX_TOOL_ITERATIONS = 5


def memory_key_for(session_id: str) -> str:
    """Canonical Redis key for a conversation's memory list.

    Single source of truth so every outbound surface (chatbot reply,
    intake _reply, settings /waha/test, upload pipeline status sends)
    writes to the same key. Strips the WAHA JID suffixes so the same
    phone number always lands on the same key regardless of which event
    shape WAHA emits.

    Prefix is unified with ``ConversationBufferService.memory_prefix`` so
    the buffer worker + the inline chatbot path share memory state.
    """
    clean = (
        session_id
        .replace("@c.us", "")
        .replace("@s.whatsapp.net", "")
        .replace("@lid", "")
    )
    return f"{MEMORY_PREFIX}{clean}"


def append_memory(redis_client, *, session_id: str, direction: str, text: str) -> None:
    """Append an inbound/outbound text entry to a conversation's memory.

    Called from every outbound boundary so the agent's recall is
    complete — mirrors the whatsapp-scheduling
    ``ConversationBufferService.append_to_memory`` pattern (which is
    invoked after EVERY successful WAHA send, not just chatbot replies).
    """
    if not text:
        return
    key = memory_key_for(session_id)
    payload = json.dumps(
        {
            "direction": direction,
            "text": text,
            "timestamp": time.time(),
        },
        separators=(",", ":"),
    )
    redis_client.rpush(key, payload)
    redis_client.ltrim(key, -MAX_MEMORY_ITEMS, -1)
    redis_client.expire(key, MEMORY_TTL_SECONDS)


@dataclass(frozen=True)
class ChatbotTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ChatbotService:
    """Surface-agnostic OpenAI tool-calling orchestrator.

    ``session_id`` is an opaque conversation key. For the WhatsApp path
    it's the sender's phone (e.g. ``"5511974693365@c.us"``); for the
    platform chat it's a web-issued UUID prefixed with ``web:``.
    """

    def __init__(
        self,
        *,
        redis_client,
        intake_service,
        session_id: str | None = None,
        phone: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        extra_context: str | None = None,
    ):
        if session_id is None and phone is None:
            raise ValueError("ChatbotService requires session_id (or legacy phone)")
        self._redis = redis_client
        self._intake = intake_service
        self._session_id = session_id or phone
        self._model = model or settings.openai_chat_model
        self._api_key = api_key or settings.openai_api_key
        self._extra_context = extra_context
        self._tools = self._build_tools()

    # ─── Public entry point ────────────────────────────────────────────
    async def reply(
        self,
        inbound_text: str,
        *,
        append_inbound: bool = True,
        append_outbound: bool = True,
    ) -> str:
        """Generate a reply for ``inbound_text``.

        Args:
            inbound_text: The user's message (or, when the worker calls,
                the joined unanswered run of inbounds since the last
                outbound — the chatbot reasons over the same blob the
                regex extractor saw).
            append_inbound: When False, skip the inbound memory write.
                The worker path uses this because the seed buffer
                already wrote the per-message inbound entries; the
                joined-blob would be a redundant duplicate.
            append_outbound: When False, skip the outbound memory write.
                The worker path uses this so it can write the canonical
                outbound to the seed buffer (which also bumps the idle
                queue) via ``buffer.append_to_memory``.
        """
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        memory = self._load_memory()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        if self._extra_context:
            messages.append({"role": "system", "content": self._extra_context})
        messages.extend(self._memory_to_messages(memory))
        messages.append({"role": "user", "content": inbound_text})

        client = self._client()
        tool_payload = self._tools_payload()

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tool_payload,
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                text = (message.content or "").strip()
                if append_inbound:
                    self._append_memory("inbound", inbound_text)
                if append_outbound:
                    self._append_memory("outbound", text)
                return text

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                raw_args = tc.function.arguments or "{}"
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
                result = await self._dispatch_tool(tc.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        logger.warning("ChatbotService hit max tool iterations for session=%s", self._session_id)
        fallback = "Tive dificuldade em concluir. Pode resumir o pedido de upload de novo?"
        if append_inbound:
            self._append_memory("inbound", inbound_text)
        if append_outbound:
            self._append_memory("outbound", fallback)
        return fallback

    # ─── Memory helpers (Redis-backed conversation log) ────────────────
    def _client(self):
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=self._api_key)

    def _memory_key(self) -> str:
        return memory_key_for(self._session_id)

    def _load_memory(self) -> list[dict[str, Any]]:
        raw = self._redis.lrange(self._memory_key(), -MAX_MEMORY_ITEMS, -1)
        memory: list[dict[str, Any]] = []
        for item in raw or []:
            try:
                memory.append(json.loads(item))
            except Exception:
                continue
        return memory

    def _append_memory(self, direction: str, text: str) -> None:
        append_memory(
            self._redis,
            session_id=self._session_id,
            direction=direction,
            text=text,
        )

    def load_history(self) -> list[dict[str, str]]:
        """Public read-only view for the platform chat UI."""
        items: list[dict[str, str]] = []
        for entry in self._load_memory():
            direction = entry.get("direction")
            text = entry.get("text")
            if not text:
                continue
            items.append(
                {
                    "role": "assistant" if direction == "outbound" else "user",
                    "content": text,
                }
            )
        return items

    def reset_history(self) -> None:
        self._redis.delete(self._memory_key())

    @staticmethod
    def _memory_to_messages(memory: list[dict[str, Any]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for item in memory:
            text = item.get("text")
            if not text:
                continue
            role = "assistant" if item.get("direction") == "outbound" else "user"
            messages.append({"role": role, "content": text})
        return messages

    # ─── Tool surface (delegates to the intake service) ────────────────
    def _build_tools(self) -> dict[str, ChatbotTool]:
        return {
            "lookup_property": ChatbotTool(
                name="lookup_property",
                description="Consulta um codigo de imovel ONE no Vista CRM.",
                parameters={
                    "type": "object",
                    "properties": {
                        "product_code": {"type": "string", "description": "Codigo ONE do imovel."}
                    },
                    "required": ["product_code"],
                    "additionalProperties": False,
                },
                handler=self._tool_lookup_property,
            ),
            "prepare_upload_request": ChatbotTool(
                name="prepare_upload_request",
                description=(
                    "Valida codigo + link do Google Drive e salva um pedido de "
                    "upload pendente. Use quando o usuario fornecer um link."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "product_code": {"type": "string"},
                        "drive_url": {"type": "string"},
                        "manual_title": {"type": "string"},
                        "privacy_status": {
                            "type": "string",
                            "enum": ["private", "unlisted", "public"],
                        },
                    },
                    "required": ["product_code", "drive_url"],
                    "additionalProperties": False,
                },
                handler=self._tool_prepare_upload,
            ),
            "prepare_upload_from_file": ChatbotTool(
                name="prepare_upload_from_file",
                description=(
                    "Valida codigo + arquivo anexado e salva um pedido de "
                    "upload pendente. Use quando o usuario anexar um arquivo "
                    "de video; o file_id chega no contexto da conversa."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "product_code": {"type": "string"},
                        "file_id": {"type": "string"},
                        "manual_title": {"type": "string"},
                        "privacy_status": {
                            "type": "string",
                            "enum": ["private", "unlisted", "public"],
                        },
                    },
                    "required": ["product_code", "file_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_prepare_upload_from_file,
            ),
            "get_pending_upload": ChatbotTool(
                name="get_pending_upload",
                description="Retorna o upload pendente da conversa, se existir.",
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_get_pending,
            ),
            "confirm_upload": ChatbotTool(
                name="confirm_upload",
                description="Confirma o upload pendente e dispara a fila de upload.",
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_confirm_upload,
            ),
            "cancel_upload": ChatbotTool(
                name="cancel_upload",
                description="Cancela o upload pendente da conversa.",
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_cancel_upload,
            ),
            # ─── Google Calendar ───────────────────────────────────
            "schedule_event": ChatbotTool(
                name="schedule_event",
                description=(
                    "Cria um evento no Google Calendar do usuario. Use "
                    "quando o usuario pedir pra agendar, marcar, criar "
                    "evento, reuniao, visita, gravacao, etc. Confirme o "
                    "horario antes de chamar."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Titulo do evento (curto, descritivo).",
                        },
                        "start_at": {
                            "type": "string",
                            "description": (
                                "Data/hora de inicio em ISO 8601 com offset, "
                                "ex.: '2026-05-15T14:00:00-03:00'."
                            ),
                        },
                        "end_at": {
                            "type": "string",
                            "description": (
                                "Data/hora de fim em ISO 8601 com offset."
                            ),
                        },
                        "description": {"type": "string"},
                        "location": {
                            "type": "string",
                            "description": "Endereco ou descricao do local (opcional).",
                        },
                        "attendee_emails": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Lista opcional de emails de convidados "
                                "(funciona apenas no modo OAuth do calendario)."
                            ),
                        },
                    },
                    "required": ["summary", "start_at", "end_at"],
                    "additionalProperties": False,
                },
                handler=self._tool_schedule_event,
            ),
            "list_upcoming_events": ChatbotTool(
                name="list_upcoming_events",
                description=(
                    "Lista os eventos do Google Calendar entre duas datas. "
                    "Use quando o usuario perguntar sobre agenda, "
                    "compromissos, o que tem na semana, etc."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "time_min": {
                            "type": "string",
                            "description": "ISO 8601 inicio do range. Default: agora.",
                        },
                        "time_max": {
                            "type": "string",
                            "description": "ISO 8601 fim do range. Default: agora + 7 dias.",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_list_upcoming_events,
            ),
            # ─── Google Maps Routes ───────────────────────────────
            "travel_estimate": ChatbotTool(
                name="travel_estimate",
                description=(
                    "Calcula tempo de viagem de carro entre dois enderecos "
                    "via Google Maps. Use pra responder 'quanto demora pra "
                    "ir de X pra Y' ou pra estimar deslocamento entre "
                    "imoveis."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "Endereco de origem (texto livre, geocoded).",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Endereco de destino.",
                        },
                    },
                    "required": ["origin", "destination"],
                    "additionalProperties": False,
                },
                handler=self._tool_travel_estimate,
            ),
            # ─── Google Drive ─────────────────────────────────────
            "inspect_drive_url": ChatbotTool(
                name="inspect_drive_url",
                description=(
                    "Inspeciona um link do Google Drive (arquivo ou pasta) "
                    "sem fazer upload. Retorna se e arquivo ou pasta e o "
                    "file_id. Use antes de decidir se chamar prepare_upload_request."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "drive_url": {"type": "string"},
                    },
                    "required": ["drive_url"],
                    "additionalProperties": False,
                },
                handler=self._tool_inspect_drive_url,
            ),
            "search_drive_files": ChatbotTool(
                name="search_drive_files",
                description=(
                    "Busca arquivos no Google Drive do usuario por nome e/ou "
                    "conteudo. Use quando o usuario perguntar 'tem um arquivo "
                    "sobre X?', 'me acha o cronograma da one', 'quantos "
                    "documentos tenho sobre Y'. Retorna lista de arquivos "
                    "com nome, tipo, tamanho, link e data de modificacao."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Termo de busca (nome OU conteudo).",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": (
                                "Filtro opcional de tipo. Exemplos: "
                                "'application/pdf', 'application/vnd.google-apps.folder' "
                                "para pastas, 'application/vnd.google-apps.spreadsheet' "
                                "para Planilhas Google."
                            ),
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Filtro opcional — buscar apenas dentro de uma pasta especifica.",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Numero max de resultados (default 20, max 50).",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=self._tool_search_drive_files,
            ),
            "list_recent_drive_files": ChatbotTool(
                name="list_recent_drive_files",
                description=(
                    "Lista os arquivos do Google Drive ordenados por data de "
                    "modificacao (mais recentes primeiro). Use quando o "
                    "usuario perguntar 'o que andei mexendo no drive?' ou "
                    "quiser uma visao geral sem busca especifica."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "Numero max de resultados (default 10, max 50).",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_list_recent_drive_files,
            ),
            "get_drive_file": ChatbotTool(
                name="get_drive_file",
                description=(
                    "Retorna os metadados de um arquivo especifico do Google "
                    "Drive pelo file_id. Use depois de search_drive_files "
                    "quando o usuario quiser detalhes de um arquivo "
                    "encontrado."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string"},
                    },
                    "required": ["file_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_get_drive_file,
            ),
            "query_drive_sheet": ChatbotTool(
                name="query_drive_sheet",
                description=(
                    "Faz contagens e agregacoes DETERMINISTICAS sobre uma "
                    "planilha do Drive (Google Sheets / CSV). USE ESTE TOOL "
                    "sempre que o usuario pedir contagem por coluna, "
                    "valores distintos numa coluna, ou filtro do tipo "
                    "'quantos X com Y'. Exemplo:\n"
                    "  Pergunta: 'quantos agendamentos com Aconteceu? = Sim?'\n"
                    "  Args: file_id=..., group_by_column='Aconteceu?'\n"
                    "  Resposta da ferramenta inclui value_counts com a "
                    "contagem exata por valor.\n\n"
                    "NUNCA conte manualmente o output de read_drive_file. "
                    "Quando a pergunta envolve coluna especifica, use este "
                    "tool — Python conta no servidor, voce so relata."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string"},
                        "group_by_column": {
                            "type": "string",
                            "description": (
                                "Nome EXATO da coluna a agregar (ex: "
                                "'Aconteceu?', 'Corretor', 'Confirmado?'). "
                                "Use read_drive_file uma vez antes pra ver "
                                "o csv_header e copiar o nome exato."
                            ),
                        },
                        "filter_column": {"type": "string"},
                        "filter_equals": {"type": "string"},
                        "max_unique_values": {
                            "type": "integer",
                            "description": "Quantos valores distintos retornar (default 30, max 100).",
                        },
                    },
                    "required": ["file_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_query_drive_sheet,
            ),
            "meta_status": ChatbotTool(
                name="meta_status",
                description=(
                    "Verifica se o Meta (Facebook + Instagram) esta conectado "
                    "e retorna nome do usuario, lista de Paginas que ele "
                    "administra e contas Instagram Business vinculadas. Use "
                    "ANTES de qualquer outra ferramenta Meta pra descobrir "
                    "page_id e ig_user_id. Se voltar error=meta_not_connected, "
                    "informe o usuario que ele precisa configurar Meta em "
                    "/api/meta/oauth/start."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                handler=self._tool_meta_status,
            ),
            "list_facebook_pages": ChatbotTool(
                name="list_facebook_pages",
                description=(
                    "Lista todas as Paginas do Facebook que o usuario "
                    "administra. Cada item tem page_id (use em "
                    "list_facebook_posts), nome, categoria, total de "
                    "curtidas (fan_count) e seguidores."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                handler=self._tool_list_facebook_pages,
            ),
            "list_facebook_posts": ChatbotTool(
                name="list_facebook_posts",
                description=(
                    "Lista as ultimas publicacoes de uma Pagina do Facebook. "
                    "Retorna cada post com texto, link (permalink_url), "
                    "imagem, curtidas, comentarios e compartilhamentos. "
                    "Inclui tambem `engagement_summary` com totais e medias "
                    "JA CALCULADOS em Python — use estes valores como "
                    "verdade absoluta, nao some os campos individuais."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": (
                                "ID da Pagina. Pegue em list_facebook_pages "
                                "ou meta_status."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Quantos posts retornar (default 10, max 100).",
                        },
                    },
                    "required": ["page_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_list_facebook_posts,
            ),
            "get_facebook_post_insights": ChatbotTool(
                name="get_facebook_post_insights",
                description=(
                    "Retorna metricas detalhadas de um post no Facebook: "
                    "impressions (quantas vezes apareceu), unique impressions "
                    "(alcance), engaged_users, clicks, reactions por tipo. "
                    "Use depois de list_facebook_posts quando o usuario "
                    "quiser dados detalhados de um post especifico."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "post_id": {
                            "type": "string",
                            "description": (
                                "ID do post no formato {page_id}_{post_id}. "
                                "Vem do campo `id` de list_facebook_posts."
                            ),
                        },
                        "page_id": {
                            "type": "string",
                            "description": (
                                "Page id opcional — necessario quando o "
                                "post_id nao for composite."
                            ),
                        },
                    },
                    "required": ["post_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_get_facebook_post_insights,
            ),
            "list_instagram_accounts": ChatbotTool(
                name="list_instagram_accounts",
                description=(
                    "Lista as contas Instagram Business / Creator que estao "
                    "vinculadas as Paginas Facebook do usuario. So aparece "
                    "se a conta IG tiver sido conectada a uma Pagina via "
                    "Meta Business Suite. Cada item tem ig_user_id (use em "
                    "list_instagram_media), username, seguidores, etc."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                handler=self._tool_list_instagram_accounts,
            ),
            "list_instagram_media": ChatbotTool(
                name="list_instagram_media",
                description=(
                    "Lista os ultimos posts/reels/carouseis de uma conta "
                    "Instagram Business. Retorna cada media com legenda, "
                    "tipo (IMAGE/VIDEO/CAROUSEL_ALBUM), link, curtidas e "
                    "comentarios. Inclui `engagement_summary` ja calculado "
                    "em Python — use estes totais, nao some campo a campo."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "ig_user_id": {
                            "type": "string",
                            "description": (
                                "ID da conta IG. Pegue em "
                                "list_instagram_accounts ou meta_status."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Quantas medias retornar (default 10, max 100).",
                        },
                    },
                    "required": ["ig_user_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_list_instagram_media,
            ),
            "get_instagram_media_insights": ChatbotTool(
                name="get_instagram_media_insights",
                description=(
                    "Retorna metricas detalhadas de uma media Instagram: "
                    "impressions, reach, engagement, saved, video_views "
                    "(quando aplicavel). Use depois de list_instagram_media "
                    "para um post especifico."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "media_id": {
                            "type": "string",
                            "description": "ID da media (campo `id` de list_instagram_media).",
                        },
                    },
                    "required": ["media_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_get_instagram_media_insights,
            ),
            "read_drive_file": ChatbotTool(
                name="read_drive_file",
                description=(
                    "Le o CONTEUDO de um arquivo do Google Drive. Use quando "
                    "o usuario perguntar coisas sobre o CONTEUDO INTERNO do "
                    "arquivo (ex: 'quantas casas tem no cronograma?', 'qual "
                    "o valor total na planilha?', 'me resume o que tem no "
                    "documento X'). Suporta: Google Sheets (CSV), Google "
                    "Docs/Slides (texto), PDF, TXT, CSV.\n\n"
                    "REGRA CRITICA SOBRE NUMEROS: use SEMPRE o campo "
                    "`stats` do retorno como verdade absoluta. NAO conte "
                    "linhas/codigos manualmente lendo o `text` — LLMs erram "
                    "contagens em payloads longos. Quote diretamente:\n"
                    "  - stats.total_lines       (linhas totais)\n"
                    "  - stats.non_empty_lines   (linhas com conteudo)\n"
                    "  - stats.csv_data_rows     (linhas de dados em CSV)\n"
                    "  - stats.one_code_count    (ocorrencias de ONExxxx)\n"
                    "  - stats.unique_one_codes  (codigos ONE distintos)\n"
                    "  - stats.one_codes_sample  (primeiros 20 codigos)\n\n"
                    "Use `text` apenas para INTERPRETAR contexto qualitativo "
                    "(o que cada coluna significa, padrao das datas, etc). "
                    "Numeros vem de stats."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string"},
                        "max_bytes": {
                            "type": "integer",
                            "description": "Default 200000 (200KB de texto).",
                        },
                    },
                    "required": ["file_id"],
                    "additionalProperties": False,
                },
                handler=self._tool_read_drive_file,
            ),
        }

    def _tools_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def _dispatch_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": "unknown_tool", "name": name}
        try:
            return await tool.handler(args)
        except Exception as exc:
            logger.exception("Chatbot tool failed: %s", name)
            return {"error": "tool_exception", "message": str(exc)}

    async def _tool_lookup_property(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.lookup_property(args.get("product_code") or "")

    async def _tool_prepare_upload(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.prepare_upload_request(
            self._session_id,
            product_code=args.get("product_code") or "",
            drive_url=args.get("drive_url") or "",
            manual_title=args.get("manual_title"),
            privacy_status=args.get("privacy_status") or "private",
        )

    async def _tool_prepare_upload_from_file(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.prepare_upload_from_file_request(
            self._session_id,
            product_code=args.get("product_code") or "",
            file_id=args.get("file_id") or "",
            manual_title=args.get("manual_title"),
            privacy_status=args.get("privacy_status") or "private",
        )

    async def _tool_get_pending(self, _args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.get_pending_upload(self._session_id)

    async def _tool_confirm_upload(self, _args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.confirm_pending_upload(self._session_id)

    async def _tool_cancel_upload(self, _args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.cancel_pending_upload(self._session_id)

    # ─── Google integrations (port from whatsapp-google-scheduling) ────
    async def _tool_schedule_event(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.schedule_calendar_event(
            summary=args.get("summary") or "",
            start_at_iso=args.get("start_at") or "",
            end_at_iso=args.get("end_at") or "",
            description=args.get("description"),
            location=args.get("location"),
            attendee_emails=args.get("attendee_emails") or [],
        )

    async def _tool_list_upcoming_events(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.list_calendar_events(
            time_min_iso=args.get("time_min"),
            time_max_iso=args.get("time_max"),
        )

    async def _tool_travel_estimate(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.travel_estimate(
            origin=args.get("origin") or "",
            destination=args.get("destination") or "",
        )

    async def _tool_inspect_drive_url(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.inspect_drive_url(
            drive_url=args.get("drive_url") or "",
        )

    async def _tool_search_drive_files(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.search_drive_files(
            query=args.get("query") or "",
            mime_type=args.get("mime_type"),
            folder_id=args.get("folder_id"),
            page_size=min(int(args.get("page_size") or 20), 50),
        )

    async def _tool_list_recent_drive_files(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.list_recent_drive_files(
            page_size=min(int(args.get("page_size") or 10), 50),
        )

    async def _tool_get_drive_file(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.get_drive_file(
            file_id=args.get("file_id") or "",
        )

    async def _tool_read_drive_file(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.read_drive_file(
            file_id=args.get("file_id") or "",
            max_bytes=int(args.get("max_bytes") or 200_000),
        )

    async def _tool_query_drive_sheet(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.query_drive_sheet(
            file_id=args.get("file_id") or "",
            group_by_column=args.get("group_by_column"),
            filter_column=args.get("filter_column"),
            filter_equals=args.get("filter_equals"),
            max_unique_values=min(int(args.get("max_unique_values") or 30), 100),
        )

    # ─── Meta (Facebook + Instagram) ───────────────────────────────────
    async def _tool_meta_status(self, _args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.meta_status()

    async def _tool_list_facebook_pages(self, _args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.list_facebook_pages()

    async def _tool_list_facebook_posts(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.list_facebook_posts(
            page_id=args.get("page_id") or "",
            limit=min(int(args.get("limit") or 10), 100),
        )

    async def _tool_get_facebook_post_insights(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._intake.get_facebook_post_insights(
            post_id=args.get("post_id") or "",
            page_id=args.get("page_id"),
        )

    async def _tool_list_instagram_accounts(
        self, _args: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._intake.list_instagram_accounts()

    async def _tool_list_instagram_media(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._intake.list_instagram_media(
            ig_user_id=args.get("ig_user_id") or "",
            limit=min(int(args.get("limit") or 10), 100),
        )

    async def _tool_get_instagram_media_insights(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._intake.get_instagram_media_insights(
            media_id=args.get("media_id") or "",
        )


# ─── Back-compat alias ─────────────────────────────────────────────────
# The WhatsApp router imports ``WhatsAppChatbotService``. Keep that name
# working so the existing wiring (commit 9948b60) stays untouched.
WhatsAppChatbotService = ChatbotService

__all__ = ["ChatbotService", "WhatsAppChatbotService", "ChatbotTool"]
