"""Recebimento de eventos do provedor de cobrança.

Este service é diferente de todos os outros do projeto, e a diferença é
deliberada: **ele roda sem JWT**. O webhook chega do provedor, não do
navegador, então não há `CurrentUser` e não há client RLS-scoped — usa-se o
client service-role, que passa por cima da RLS.

Consequência prática: `CrudService` filtra org nenhuma na leitura (confia na
policy), então reusá-lo com um client service-role leria através de todas as
organizações no dia em que isto deixar de ser single-tenant. Por isso este
service **não** herda de `CrudService`, e toda query aqui carrega `org_id`
explícito. O org é resolvido a partir da própria linha do lançamento e
conferido contra `settings.org_id`.

O desenho do fluxo é imposto por uma restrição do Asaas: **a fila de entrega é
interrompida após 15 respostas não-2xx consecutivas**, e só volta com
reativação manual no painel. Um evento que não conseguimos processar, se
devolver erro, para a conciliação de todos os outros pagamentos. Daí:

    grava primeiro → processa depois → responde 200 quase sempre

Evento problemático fica estacionado com `processado_em` nulo e `erro`
preenchido. Esta tabela é a fila de retry, drenada por rota autenticada.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from postgrest.exceptions import APIError

from app.config import settings
from app.database import execute
from app.providers.tipos import EventoCobranca, ProvedorCobranca
from app.services.financeiro_service import registrar_recebimento

# Valores de `provedor_eventos.efeito`.
EFEITO_RECEBIDO = "recebido"
EFEITO_JA_RECEBIDO = "ignorado_ja_recebido"
EFEITO_SEM_LANCAMENTO = "sem_lancamento"
EFEITO_IGNORADO = "ignorado"
EFEITO_ERRO = "erro"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventoDuplicado(Exception):
    """Já vimos este evento. O provedor reentrega em retry — é esperado."""


class IntegracaoService:
    def __init__(self, db, provedor: ProvedorCobranca):
        self.db = db
        self.provedor = provedor
        self.org_id = settings.org_id

    # ── entrada ──────────────────────────────────────────────────────────
    def receber(self, corpo: dict) -> dict:
        """Processa um webhook. Nunca levanta por evento ruim — só por falha
        de infraestrutura, que aí é 5xx legítimo e vale retry do provedor."""
        evento = self.provedor.interpretar_evento(corpo)

        # Id antes de tudo: mesmo evento que não nos interessa é gravado, para
        # o log ser fiel ao que chegou e para o dedupe valer para todos.
        evento_id = evento.id_no_provedor if evento else _id_do_corpo(corpo)
        tipo_bruto = evento.tipo_bruto if evento else str(corpo.get("event") or "?")

        try:
            linha = self._gravar(corpo, evento_id, tipo_bruto, evento)
        except EventoDuplicado:
            return {"status": "duplicado", "evento_id": evento_id}

        if evento is None:
            self._concluir(linha["id"], EFEITO_IGNORADO)
            return {"status": "ignorado", "evento_id": evento_id}

        try:
            efeito, lancamento_id = self._aplicar(evento)
        except Exception as e:  # noqa: BLE001 — ver docstring do módulo
            # Deliberadamente amplo. Evento envenenado fica estacionado e a
            # resposta é 200: insistir 15 vezes só garante parar de receber os
            # eventos dos outros pagamentos.
            self._concluir(linha["id"], EFEITO_ERRO, erro=str(e)[:500])
            return {"status": "erro_registrado", "evento_id": evento_id}

        self._concluir(linha["id"], efeito, lancamento_id=lancamento_id)
        return {"status": "processado", "efeito": efeito, "evento_id": evento_id}

    # ── persistência ─────────────────────────────────────────────────────
    def _gravar(
        self,
        corpo: dict,
        evento_id: str,
        tipo_bruto: str,
        evento: Optional[EventoCobranca],
    ) -> dict:
        """Insert com dedupe pela UNIQUE (provedor, evento_id).

        Não passa por `database.execute()` de propósito: ele traduz 23505 em
        HTTPException(409), e capturar um 409 para usar como controle de fluxo
        lavaria um conceito de banco através de HTTP. Aqui o `APIError` é
        inspecionado direto.
        """
        registro = {
            "org_id": self.org_id,
            "provedor": self.provedor.nome,
            "evento_id": evento_id,
            "tipo": tipo_bruto,
            "cobranca_id": evento.cobranca.id_no_provedor if evento else None,
            "payload": corpo,
        }
        try:
            resposta = self.db.table("provedor_eventos").insert(registro).execute()
        except APIError as e:
            if (e.code or "") == "23505":
                raise EventoDuplicado(evento_id) from e
            raise
        return (resposta.data or [registro])[0]

    def _concluir(
        self,
        linha_id: str,
        efeito: str,
        *,
        erro: Optional[str] = None,
        lancamento_id: Optional[str] = None,
    ) -> None:
        changes: dict = {"efeito": efeito, "erro": erro}
        if lancamento_id:
            changes["lancamento_id"] = lancamento_id
        # `processado_em` fica NULL no caso de erro — é esse o predicado que a
        # rota de reprocessamento consulta.
        if efeito != EFEITO_ERRO:
            changes["processado_em"] = _agora()
        execute(
            self.db.table("provedor_eventos").update(changes).eq("id", linha_id)
        )

    # ── efeito no domínio ────────────────────────────────────────────────
    def _aplicar(self, evento: EventoCobranca) -> tuple[str, Optional[str]]:
        lancamento = self._achar_lancamento(evento)
        if lancamento is None:
            # Cobrança criada direto no painel do provedor, ou lançamento
            # apagado. 200 e segue — 404 aqui pausaria a fila.
            return EFEITO_SEM_LANCAMENTO, None

        self._espelhar(lancamento, evento)

        if evento.tipo != "liquidada":
            return EFEITO_IGNORADO, lancamento["id"]

        pago_em = evento.cobranca.pago_em or date.today()
        liquidou = registrar_recebimento(
            self.db, lancamento, pago_em, evento.cobranca.forma
        )
        # Mesmo quando não liquidou (o funil chegou antes), o espelho já foi
        # gravado acima. Descartar a versão do banco é como a conciliação
        # apodrece em silêncio.
        return (EFEITO_RECEBIDO if liquidou else EFEITO_JA_RECEBIDO), lancamento["id"]

    def _achar_lancamento(self, evento: EventoCobranca) -> Optional[dict]:
        """Procura pela referência que mandamos, e só então pelo id da cobrança.

        A referência é nossa e estável; o id do provedor só existe depois da
        primeira emissão. Ambas as buscas filtram `org_id` explicitamente
        porque este service roda sem RLS.
        """
        referencia = evento.cobranca.referencia_externa
        if referencia and _e_uuid(referencia):
            achados = execute(
                self.db.table("lancamentos")
                .select("*")
                .eq("org_id", self.org_id)
                .eq("id", referencia)
            ).data or []
            if achados:
                return achados[0]

        if evento.cobranca.id_no_provedor:
            achados = execute(
                self.db.table("lancamentos")
                .select("*")
                .eq("org_id", self.org_id)
                .eq("provedor_cobranca_id", evento.cobranca.id_no_provedor)
            ).data or []
            if achados:
                return achados[0]
        return None

    def _espelhar(self, lancamento: dict, evento: EventoCobranca) -> None:
        changes: dict = {
            "provedor": self.provedor.nome,
            "provedor_status": evento.cobranca.status,
            "sincronizado_em": _agora(),
        }
        if not lancamento.get("provedor_cobranca_id"):
            changes["provedor_cobranca_id"] = evento.cobranca.id_no_provedor
        if evento.cobranca.linha_digitavel:
            changes["linha_digitavel"] = evento.cobranca.linha_digitavel
        if evento.cobranca.url_fatura:
            changes["url_fatura"] = evento.cobranca.url_fatura
        execute(
            self.db.table("lancamentos")
            .update(changes)
            .eq("org_id", self.org_id)
            .eq("id", lancamento["id"])
        )

    # ── reprocessamento ──────────────────────────────────────────────────
    def pendentes(self) -> list[dict]:
        return execute(
            self.db.table("provedor_eventos")
            .select("*")
            .eq("org_id", self.org_id)
            .order("created_at", desc=False)
        ).data or []

    def reprocessar(self) -> dict:
        """Drena a fila de eventos que falharam. Chamada por rota autenticada.

        Reprocessar é seguro porque o efeito é idempotente: quem já liquidou
        recebe False de `registrar_recebimento` e nada muda.
        """
        alvos = [e for e in self.pendentes() if e.get("processado_em") is None]
        resultados = {"total": len(alvos), "ok": 0, "erro": 0}

        for linha in alvos:
            evento = self.provedor.interpretar_evento(linha.get("payload") or {})
            if evento is None:
                self._concluir(linha["id"], EFEITO_IGNORADO)
                resultados["ok"] += 1
                continue
            try:
                efeito, lancamento_id = self._aplicar(evento)
            except Exception as e:  # noqa: BLE001
                self._concluir(linha["id"], EFEITO_ERRO, erro=str(e)[:500])
                resultados["erro"] += 1
                continue
            self._concluir(linha["id"], efeito, lancamento_id=lancamento_id)
            resultados["ok"] += 1

        return resultados


def _id_do_corpo(corpo: dict) -> str:
    """Dedupe para evento que o adapter não reconheceu."""
    import hashlib
    import json

    canonico = json.dumps(corpo, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _e_uuid(valor: str) -> bool:
    """A referência parece um id nosso?

    `lancamentos.id` é UUID, e o Postgres **recusa** comparar a coluna com uma
    string que não seja UUID — não devolve vazio, levanta erro. Sem esta
    peneira, uma cobrança criada à mão no painel do Asaas (onde o
    `externalReference` é texto livre, ou nem existe) faz o webhook estacionar
    um evento como `erro` em vez de responder `sem_lancamento` limpo. O evento
    ficaria na fila de retry para sempre, sendo reprocessado e falhando igual.

    Descoberto contra o banco real: o FakeDB dos testes compara strings em
    Python e devolve "não achei", então a suíte inteira passava verde. É a
    diferença entre um fake fiel e um fake conveniente.
    """
    try:
        uuid.UUID(str(valor))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
