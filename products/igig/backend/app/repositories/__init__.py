"""IgIg repositories — one per core entity, over the seed persistence seam.

Core entities: Cliente · Marca · Contrato · Pauta · Tarefa (the scaffold
brief's answer). ``Apontamento`` is a SUPPORT repository under Tarefa — the
play/pause timesheet produces N segments per tarefa, so the hours cannot be a
column on tarefa itself.

Every method takes ``org_id`` first because the store requires it; on SQLite
that argument IS the tenant boundary.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from noctusai_lib.integrations.persistence import Op, Order, QuerySpec, Record, RecordStore
from noctusai_lib.security.encrypted_tokens import decrypt, encrypt

from .base import BaseRepository, RecordNotFound

__all__ = [
    "BaseRepository",
    "RecordNotFound",
    "ClienteRepository",
    "MarcaRepository",
    "ContratoRepository",
    "PautaRepository",
    "TarefaRepository",
    "ApontamentoRepository",
    "AprovacaoRepository",
    "FuncaoRepository",
    "ProfissionalRepository",
    "AcessoRepository",
    "PecaRepository",
    "PublicacaoRepository",
    "MetricaRepository",
    "Repositorios",
    "ETAPAS",
]

#: The rigid 8-step esteira from Módulo 4, in order. Sequence matters: the
#: kanban advances one step at a time, and the DB CHECK constraint mirrors
#: this exact set on both backends.
ETAPAS: tuple[str, ...] = (
    "aguardando_roteiro",
    "roteiro_em_producao",
    "aguardando_design",
    "design_em_producao",
    "revisao_interna",
    "aprovacao_cliente",
    "pronto_para_agendamento",
    "agendado",
)


class ClienteRepository(BaseRepository):
    table = "cliente"
    default_order = (Order("nome"),)

    def listar_por_status(self, org_id: str, status: str) -> list[Record]:
        return self._por("status", status, org_id)

    def buscar_por_nome(self, org_id: str, termo: str) -> list[Record]:
        """Case-insensitive substring search — the Clientes page filter."""
        return self.listar(org_id, spec=QuerySpec().with_filter("nome", Op.CONTAINS, termo))

    def ativar(self, org_id: str, cliente_id: str) -> Record:
        """Módulo 1: contract signature flips a prospect to ativo."""
        return self.atualizar(org_id, cliente_id, {"status": "ativo"})

    def marcar_inadimplente(self, org_id: str, cliente_id: str) -> Record:
        """Módulo 6: gates the approval portal after N days overdue."""
        return self.atualizar(org_id, cliente_id, {"status": "inadimplente"})


class MarcaRepository(BaseRepository):
    table = "marca"
    default_order = (Order("nome"),)

    def do_cliente(self, org_id: str, cliente_id: str) -> list[Record]:
        return self._por("cliente_id", cliente_id, org_id)

    def repertorio(self, org_id: str, cliente_id: str) -> Record | None:
        """The payload behind Módulo 2's persistent sidebar.

        Returns the client's first brand, or ``None`` when none exists —
        ``None`` is meaningful here (a client legitimately may not have a
        brand yet), unlike a by-id miss, which raises.
        """
        marcas = self.do_cliente(org_id, cliente_id)
        return marcas[0] if marcas else None


class ContratoRepository(BaseRepository):
    table = "contrato"

    def do_cliente(self, org_id: str, cliente_id: str) -> list[Record]:
        return self._por("cliente_id", cliente_id, org_id)

    def ativos(self, org_id: str) -> list[Record]:
        return self._por("status", "ativo", org_id)

    def registrar_assinatura(self, org_id: str, contrato_id: str) -> Record:
        """Módulo 1: the signature webhook lands here."""
        return self.atualizar(
            org_id,
            contrato_id,
            {"status": "ativo", "assinado_em": datetime.now(timezone.utc).isoformat()},
        )


class PautaRepository(BaseRepository):
    table = "pauta"
    default_order = (Order("data_publicacao"),)

    def do_cliente(self, org_id: str, cliente_id: str) -> list[Record]:
        return self._por("cliente_id", cliente_id, org_id)

    def no_periodo(self, org_id: str, inicio: str, fim: str) -> list[Record]:
        """Calendário editorial window — Módulo 3, and Módulo 6's excedentes."""
        spec = (
            QuerySpec()
            .with_filter("data_publicacao", Op.GTE, inicio)
            .with_filter("data_publicacao", Op.LTE, fim)
        )
        return self.listar(org_id, spec=spec)

    def por_funil(self, org_id: str, nivel: str) -> list[Record]:
        return self._por("funil", nivel, org_id)


class TarefaRepository(BaseRepository):
    table = "tarefa"

    def por_etapa(self, org_id: str, etapa: str) -> list[Record]:
        return self._por("etapa", etapa, org_id)

    def quadro(self, org_id: str) -> dict[str, list[Record]]:
        """Every tarefa grouped by etapa — the Módulo 4 kanban payload.

        One query, grouped in memory: eight per-etapa queries would be eight
        round-trips for a board that always renders all columns at once.
        """
        board: dict[str, list[Record]] = {etapa: [] for etapa in ETAPAS}
        for tarefa in self.listar(org_id):
            board.setdefault(tarefa.get("etapa", ""), []).append(tarefa)
        return board

    def mover(self, org_id: str, tarefa_id: str, etapa: str) -> Record:
        if etapa not in ETAPAS:
            raise ValueError(f"etapa inválida: {etapa!r}; esperada uma de {ETAPAS}")
        return self.atualizar(org_id, tarefa_id, {"etapa": etapa})

    def solicitar_ajuste(self, org_id: str, tarefa_id: str, observacao: str = "") -> Record:
        """Módulo 4: the client's [Solicitar Ajuste] button.

        Reopens the tarefa at revisão interna AND increments the Contador de
        Refações, which Módulo 5's BI de eficiência reports per client. The
        read-then-write is not atomic on either backend; a concurrent double
        click could lose one increment. Acceptable today (one client acts on
        one tarefa at a time) and the fix — an atomic increment on the store —
        belongs in the seam, not here, when a second consumer needs it.
        """
        atual = self.buscar(org_id, tarefa_id)
        return self.atualizar(
            org_id,
            tarefa_id,
            {
                "etapa": "revisao_interna",
                "refacoes": int(atual.get("refacoes") or 0) + 1,
                "observacao_cliente": observacao,
            },
        )

    def aprovar(self, org_id: str, tarefa_id: str) -> Record:
        """Módulo 4: [Aprovar Conteúdo] jumps straight to scheduling."""
        return self.atualizar(org_id, tarefa_id, {"etapa": "pronto_para_agendamento"})


class ApontamentoRepository(BaseRepository):
    """Timesheet segments — support table under Tarefa."""

    table = "apontamento"
    default_order = (Order("iniciado_em", descending=True),)

    def da_tarefa(self, org_id: str, tarefa_id: str) -> list[Record]:
        return self._por("tarefa_id", tarefa_id, org_id)

    def aberto_do_usuario(self, org_id: str, usuario_id: str) -> Record | None:
        """The user's running timer, if any.

        The DB carries a partial unique index making at most one open segment
        per user possible, so this returning a list of >1 would be a schema
        breach rather than a case to handle.
        """
        spec = (
            QuerySpec()
            .with_filter("usuario_id", Op.EQ, usuario_id)
            .with_filter("encerrado_em", Op.IS_NULL, True)
        )
        abertos = self.listar(org_id, spec=spec)
        return abertos[0] if abertos else None

    def iniciar(self, org_id: str, tarefa_id: str, usuario_id: str) -> Record:
        """Start the timer, auto-pausing whatever else was running.

        The spec requires the clock to stop when another tarefa starts, so
        this closes any open segment first rather than letting the unique
        index reject the insert.
        """
        aberto = self.aberto_do_usuario(org_id, usuario_id)
        if aberto is not None:
            self.encerrar(org_id, str(aberto["id"]))
        return self.criar(
            org_id,
            {
                "tarefa_id": tarefa_id,
                "usuario_id": usuario_id,
                "iniciado_em": datetime.now(timezone.utc).isoformat(),
                "minutos": 0,
            },
        )

    def encerrar(self, org_id: str, apontamento_id: str) -> Record:
        """Stop the timer and persist the elapsed minutes."""
        atual = self.buscar(org_id, apontamento_id)
        fim = datetime.now(timezone.utc)
        inicio = datetime.fromisoformat(str(atual["iniciado_em"]))
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        minutos = max(0, int((fim - inicio).total_seconds() // 60))
        return self.atualizar(
            org_id, apontamento_id, {"encerrado_em": fim.isoformat(), "minutos": minutos}
        )

    def minutos_da_tarefa(self, org_id: str, tarefa_id: str) -> int:
        """Total measured minutes — the input to custo real do job."""
        return sum(int(a.get("minutos") or 0) for a in self.da_tarefa(org_id, tarefa_id))


class AprovacaoRepository(BaseRepository):
    """Portal de Aprovação Externo links — Módulo 4.

    The token IS the auth: the client has no noc account, so the portal is
    unauthenticated and the token must be unguessable, expirable and
    single-decision.

    **The token carries its own org.** The persistence seam requires an
    ``org_id`` on every call — that requirement IS the tenant boundary on the
    SQLite path — but a public caller has no org to supply. Rather than punch
    a cross-org lookup through the seam and weaken that invariant for every
    other consumer, the token is minted as ``<org_id>.<secret>``: the public
    endpoint parses the org out of the token and then performs an ordinary
    org-scoped query. The org half is not a secret (it is a UUID the client
    could never guess anything from) and the ``<secret>`` half still carries
    the full 256 bits of entropy, so guessability is unchanged.
    """

    table = "aprovacao"

    #: Links stop working after this long. A link that never expires is a
    #: permanent unauthenticated hole into a client's content.
    VALIDADE_PADRAO = timedelta(days=14)

    def da_tarefa(self, org_id: str, tarefa_id: str) -> list[Record]:
        return self._por("tarefa_id", tarefa_id, org_id)

    @staticmethod
    def montar_token(org_id: str) -> str:
        """``<org_id>.<secret>`` — see the class docstring for the why.

        ``secrets.token_urlsafe(32)`` is 256 bits from a CSPRNG. Not uuid4
        (only 122 bits, and version/variant bits are fixed) and emphatically
        not the row id: a guessable token exposes unpublished client content.
        """
        return f"{org_id}.{secrets.token_urlsafe(32)}"

    @staticmethod
    def org_do_token(token: str) -> str | None:
        """Parse the org half. ``None`` when the token is malformed."""
        org_id, separador, secret = token.partition(".")
        if not separador or not org_id or not secret:
            return None
        return org_id

    def emitir(
        self,
        org_id: str,
        tarefa_id: str,
        *,
        validade: timedelta | None = None,
    ) -> Record:
        """Mint an approval link for a tarefa."""
        expira = datetime.now(timezone.utc) + (validade or self.VALIDADE_PADRAO)
        return self.criar(
            org_id,
            {
                "tarefa_id": tarefa_id,
                "token": self.montar_token(org_id),
                "expira_em": expira.isoformat(),
            },
        )

    def por_token(self, token: str) -> Record | None:
        """Resolve a link by token — the public portal read path.

        Returns ``None`` when the token is malformed or unknown. Callers MUST
        NOT distinguish "unknown" from "expired" in what they return to the
        client, or the endpoint becomes a token oracle.
        """
        org_id = self.org_do_token(token)
        if org_id is None:
            return None
        encontradas = self.listar(org_id, spec=QuerySpec().with_filter("token", Op.EQ, token))
        return encontradas[0] if encontradas else None

    def expirada(self, aprovacao: Record, *, agora: datetime | None = None) -> bool:
        expira_em = aprovacao.get("expira_em")
        if not expira_em:
            return False
        limite = datetime.fromisoformat(str(expira_em))
        if limite.tzinfo is None:
            limite = limite.replace(tzinfo=timezone.utc)
        return (agora or datetime.now(timezone.utc)) > limite

    def decidida(self, aprovacao: Record) -> bool:
        return aprovacao.get("decidido_em") is not None

    def registrar_decisao(
        self, org_id: str, aprovacao_id: str, decisao: str, observacao: str = ""
    ) -> Record:
        if decisao not in {"aprovado", "ajuste"}:
            raise ValueError(f"decisão inválida: {decisao!r}")
        return self.atualizar(
            org_id,
            aprovacao_id,
            {
                "decisao": decisao,
                "observacao": observacao,
                "decidido_em": datetime.now(timezone.utc).isoformat(),
            },
        )


class FuncaoRepository(BaseRepository):
    """Roles and their default hourly cost — the base of the custo/hora model."""

    table = "funcao"
    default_order = (Order("nome"),)


class ProfissionalRepository(BaseRepository):
    """Team members. Hourly cost resolves role-default → per-person override.

    Feeds three separate features that the spec never reconciled: M1's
    calculadora de escopo (minimum price), M5's BI de eficiência (custo real
    do job), and M6's DRE (margin per account). All three read
    :meth:`custo_hora_efetivo`, so the rate is defined once.
    """

    table = "profissional"
    default_order = (Order("nome"),)

    def ativos(self, org_id: str) -> list[Record]:
        return self.listar(org_id, spec=QuerySpec().with_filter("ativo", Op.EQ, True))

    def custo_hora_efetivo(self, org_id: str, profissional_id: str, *, funcoes: "FuncaoRepository") -> float:
        """The rate that actually applies to this person.

        ``custo_hora_override`` NULL means "inherit the função's default";
        ``0`` is a real, deliberate rate (an unpaid intern), so the two must
        not collapse — hence the explicit `is not None` rather than a falsy
        check.
        """
        prof = self.buscar(org_id, profissional_id)
        override = prof.get("custo_hora_override")
        if override is not None:
            return float(override)
        funcao_id = prof.get("funcao_id")
        if not funcao_id:
            # No função and no override: costing this person's hours would be
            # a silent zero, which quietly understates the job. Surface it.
            raise ValueError(
                f"profissional {profissional_id} tem custo_hora indefinido "
                "(sem override e sem função)"
            )
        return float(funcoes.buscar(org_id, str(funcao_id)).get("custo_hora_padrao") or 0)


class AcessoRepository(BaseRepository):
    """Cofre de Acessos — Módulo 2.

    Passwords are encrypted with the seed's Fernet helper
    (``noctusai_lib.security.encrypted_tokens``) before they ever reach the
    store, and decrypted only in process memory at the moment of use. The KEY
    is supplied by the caller from configuration and is never persisted beside
    the ciphertext — if these rows leak via a backup, replica or log line, the
    credentials are not recoverable.

    There is no "reveal all" method by design: decryption is per-record and
    explicit, so an accidental bulk decrypt is not one call away.
    """

    table = "acesso"
    default_order = (Order("rotulo"),)

    def do_cliente(self, org_id: str, cliente_id: str) -> list[Record]:
        """Credentials for one client — ciphertext NOT decrypted."""
        return self._por("cliente_id", cliente_id, org_id)

    def guardar(
        self,
        org_id: str,
        cliente_id: str,
        *,
        rotulo: str,
        senha: str | None = None,
        chave: bytes | None = None,
        **campos: object,
    ) -> Record:
        """Store an access record, encrypting ``senha`` if one is given.

        Refuses to persist a password without a key rather than falling back
        to plaintext — a silent downgrade here is the whole failure this table
        exists to prevent.
        """
        valores: Record = {"cliente_id": cliente_id, "rotulo": rotulo, **campos}
        if senha:
            if not chave:
                raise ValueError(
                    "senha fornecida sem chave de criptografia — recuse-se a gravar "
                    "credencial em texto puro"
                )
            valores["senha_cifrada"] = encrypt(senha, chave)
        return self.criar(org_id, valores)

    def revelar_senha(self, org_id: str, acesso_id: str, chave: bytes) -> str | None:
        """Decrypt ONE password. ``None`` when the record stores none."""
        cifrada = self.buscar(org_id, acesso_id).get("senha_cifrada")
        if not cifrada:
            return None
        return decrypt(str(cifrada), chave)


class PecaRepository(BaseRepository):
    """Visual assets attached to a pauta — Módulo 4's portal view.

    Rows carry a STORAGE KEY, never bytes. The bytes live behind the seed's
    storage seam, so this repository is identical whether the backend is the
    local filesystem or Supabase Storage.
    """

    table = "peca"
    default_order = (Order("ordem"),)

    def da_pauta(self, org_id: str, pauta_id: str) -> list[Record]:
        return self._por("pauta_id", pauta_id, org_id)

    def anexar(
        self,
        org_id: str,
        pauta_id: str,
        *,
        storage_key: str,
        nome_arquivo: str | None = None,
        mime_type: str | None = None,
        tamanho_bytes: int | None = None,
    ) -> Record:
        """Record an uploaded asset. Ordering appends to the end."""
        existentes = self.da_pauta(org_id, pauta_id)
        return self.criar(
            org_id,
            {
                "pauta_id": pauta_id,
                "storage_key": storage_key,
                "nome_arquivo": nome_arquivo,
                "mime_type": mime_type,
                "tamanho_bytes": tamanho_bytes,
                "ordem": len(existentes),
            },
        )


class PublicacaoRepository(BaseRepository):
    """One publish attempt, per channel — Módulo 5."""

    table = "publicacao"
    default_order = (Order("agendada_para"),)

    def da_pauta(self, org_id: str, pauta_id: str) -> list[Record]:
        return self._por("pauta_id", pauta_id, org_id)

    def agendar(self, org_id: str, pauta_id: str, canal: str, quando: str) -> Record:
        return self.criar(
            org_id,
            {"pauta_id": pauta_id, "canal": canal, "agendada_para": quando, "status": "agendada"},
        )

    def pendentes(self, org_id: str, ate: str) -> list[Record]:
        """Scheduled publications due by ``ate`` — the worker's queue."""
        spec = (
            QuerySpec()
            .with_filter("status", Op.EQ, "agendada")
            .with_filter("agendada_para", Op.LTE, ate)
        )
        return self.listar(org_id, spec=spec)

    def marcar_publicada(
        self, org_id: str, publicacao_id: str, *, external_id: str, permalink: str | None = None
    ) -> Record:
        """Only ever called with a platform-confirmed id.

        `external_id` is required by the signature so a caller cannot mark a
        post published without the handle every later metrics fetch needs.
        """
        return self.atualizar(
            org_id,
            publicacao_id,
            {
                "status": "publicada",
                "external_id": external_id,
                "permalink": permalink,
                "publicada_em": datetime.now(timezone.utc).isoformat(),
                "erro": None,
            },
        )

    def marcar_falha(self, org_id: str, publicacao_id: str, erro: str) -> Record:
        """Record a failure AND the attempt count.

        Incrementing here rather than in the caller keeps 'how many times have
        we tried' in one place; a retry policy elsewhere can trust it.
        """
        atual = self.buscar(org_id, publicacao_id)
        return self.atualizar(
            org_id,
            publicacao_id,
            {
                "status": "falhou",
                "erro": erro[:2000],
                "tentativas": int(atual.get("tentativas") or 0) + 1,
            },
        )


class MetricaRepository(BaseRepository):
    """Engagement snapshots. APPEND-ONLY — see the migration's note."""

    table = "metrica"
    default_order = (Order("coletada_em", descending=True),)

    def da_publicacao(self, org_id: str, publicacao_id: str) -> list[Record]:
        return self._por("publicacao_id", publicacao_id, org_id)

    def registrar(self, org_id: str, publicacao_id: str, **valores: object) -> Record:
        return self.criar(
            org_id,
            {
                "publicacao_id": publicacao_id,
                "coletada_em": datetime.now(timezone.utc).isoformat(),
                **valores,
            },
        )

    def ultima(self, org_id: str, publicacao_id: str) -> Record | None:
        """The most recent snapshot — what a dashboard tile shows."""
        historico = self.da_publicacao(org_id, publicacao_id)
        return historico[0] if historico else None


class Repositorios:
    """All repositories bound to one store — what routers receive.

    A single object keeps the dependency surface small: a router asks for
    ``Repositorios`` and reaches the entity it needs, rather than declaring
    six separate dependencies.
    """

    def __init__(self, store: RecordStore) -> None:
        self.store = store
        self.cliente = ClienteRepository(store)
        self.marca = MarcaRepository(store)
        self.contrato = ContratoRepository(store)
        self.pauta = PautaRepository(store)
        self.tarefa = TarefaRepository(store)
        self.apontamento = ApontamentoRepository(store)
        self.aprovacao = AprovacaoRepository(store)
        self.funcao = FuncaoRepository(store)
        self.profissional = ProfissionalRepository(store)
        self.acesso = AcessoRepository(store)
        self.peca = PecaRepository(store)
        self.publicacao = PublicacaoRepository(store)
        self.metrica = MetricaRepository(store)
