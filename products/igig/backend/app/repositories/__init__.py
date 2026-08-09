"""IgIg repositories — one per core entity, over the seed persistence seam.

Core entities: Cliente · Marca · Contrato · Pauta · Tarefa (the scaffold
brief's answer). ``Apontamento`` is a SUPPORT repository under Tarefa — the
play/pause timesheet produces N segments per tarefa, so the hours cannot be a
column on tarefa itself.

Every method takes ``org_id`` first because the store requires it; on SQLite
that argument IS the tenant boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone

from noctusai_lib.integrations.persistence import Op, Order, QuerySpec, Record, RecordStore

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
