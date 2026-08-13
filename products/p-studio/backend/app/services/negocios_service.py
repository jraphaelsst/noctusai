"""Negócios — o funil comercial e os efeitos colaterais de cada avanço.

O negócio é a espinha dorsal: ao andar no funil ele abre a produção e gera o
lançamento financeiro. É por isso que essa regra vive num service e não numa
policy de RLS — foi a peça que faltava no protótipo, onde as três esteiras
eram arrays independentes sem nada ligando uma à outra.

Regras de transição (spec § 2, § 4, § 7):

    → producao   abre a produção (etapa `agendado`), se ainda não existir
    → entregue   marca a produção como entregue e gera o lançamento
                 `a_faturar`, se ainda não existir
    → recebido   dá baixa nos lançamentos em aberto do negócio

Toda regra é idempotente: reentrar numa etapa não duplica nada. O usuário
arrasta o card para frente e para trás no kanban o tempo todo.
"""
from datetime import date, timedelta

from fastapi import HTTPException

from app.database import execute
from app.services.base import CrudService
from app.services.financeiro_service import registrar_recebimento


class NegociosService(CrudService):
    table = "negocios"
    order_by = "created_at"
    order_desc = True

    def _nao_encontrado(self) -> str:
        return "Negócio não encontrado"

    # ── leitura ──────────────────────────────────────────────────────────
    def listar_completo(self) -> list[dict]:
        negocios = self.listar()
        if not negocios:
            return []

        clientes = self._mapa("clientes")
        imoveis = self._mapa("imoveis", "id,endereco,codigo")
        servicos = self._mapa("servicos")
        vinculos = execute(
            self.db.table("negocio_servicos").select("id,negocio_id,servico_id,preco")
        ).data or []

        por_negocio: dict[str, list[dict]] = {}
        for v in vinculos:
            por_negocio.setdefault(v["negocio_id"], []).append(
                {
                    "id": v["id"],
                    "servico_id": v["servico_id"],
                    "nome": (servicos.get(v["servico_id"]) or {}).get("nome"),
                    "preco": float(v.get("preco") or 0),
                }
            )

        return [self._enriquecer(n, clientes, imoveis, por_negocio) for n in negocios]

    def obter_completo(self, negocio_id: str) -> dict:
        negocio = self.obter(negocio_id)
        clientes = self._mapa("clientes")
        imoveis = self._mapa("imoveis", "id,endereco,codigo")
        servicos = self._mapa("servicos")
        vinculos = execute(
            self.db.table("negocio_servicos")
            .select("id,negocio_id,servico_id,preco")
            .eq("negocio_id", negocio_id)
        ).data or []
        por_negocio = {
            negocio_id: [
                {
                    "id": v["id"],
                    "servico_id": v["servico_id"],
                    "nome": (servicos.get(v["servico_id"]) or {}).get("nome"),
                    "preco": float(v.get("preco") or 0),
                }
                for v in vinculos
            ]
        }
        return self._enriquecer(negocio, clientes, imoveis, por_negocio)

    @staticmethod
    def _enriquecer(negocio: dict, clientes: dict, imoveis: dict, servicos: dict) -> dict:
        imovel = imoveis.get(negocio.get("imovel_id")) or {}
        return {
            **negocio,
            "valor": float(negocio.get("valor") or 0),
            "cliente_nome": (clientes.get(negocio.get("cliente_id")) or {}).get("nome"),
            "imovel_endereco": imovel.get("endereco"),
            "servicos": servicos.get(negocio["id"], []),
        }

    # ── escrita ──────────────────────────────────────────────────────────
    def criar_com_servicos(self, payload: dict, servico_ids: list[str]) -> dict:
        catalogo = self._catalogo_por_id(servico_ids)

        # Valor ausente = soma do que foi contratado. O usuário ainda pode
        # informar um valor negociado diferente da tabela.
        if payload.get("valor") is None:
            payload["valor"] = sum(float(s.get("preco") or 0) for s in catalogo.values())

        if not payload.get("titulo"):
            payload["titulo"] = self._titulo_padrao(payload)

        negocio = self.criar(payload)
        self._gravar_servicos(negocio["id"], servico_ids, catalogo)
        return self.obter_completo(negocio["id"])

    def atualizar_com_servicos(
        self, negocio_id: str, changes: dict, servico_ids: list[str] | None
    ) -> dict:
        self.obter(negocio_id)  # 404 antes de qualquer escrita

        if servico_ids is not None:
            catalogo = self._catalogo_por_id(servico_ids)
            execute(
                self.db.table("negocio_servicos").delete().eq("negocio_id", negocio_id)
            )
            self._gravar_servicos(negocio_id, servico_ids, catalogo)

        if changes:
            self.atualizar(negocio_id, changes)
        return self.obter_completo(negocio_id)

    def _catalogo_por_id(self, servico_ids: list[str]) -> dict[str, dict]:
        if not servico_ids:
            return {}
        rows = execute(
            self.db.table("servicos").select("id,nome,preco,prazo_dias").in_("id", servico_ids)
        ).data or []
        catalogo = {r["id"]: r for r in rows}
        faltando = [s for s in servico_ids if s not in catalogo]
        if faltando:
            raise HTTPException(
                status_code=400, detail=f"Serviço inexistente: {', '.join(faltando)}"
            )
        return catalogo

    def _gravar_servicos(
        self, negocio_id: str, servico_ids: list[str], catalogo: dict[str, dict]
    ) -> None:
        if not servico_ids:
            return
        # `preco` é copiado do catálogo agora: o preço de tabela muda com o
        # tempo, o preço já contratado não pode mudar junto.
        linhas = [
            {
                "org_id": self.org_id,
                "negocio_id": negocio_id,
                "servico_id": sid,
                "preco": float((catalogo.get(sid) or {}).get("preco") or 0),
            }
            for sid in dict.fromkeys(servico_ids)  # dedup preservando a ordem
        ]
        execute(self.db.table("negocio_servicos").insert(linhas))

    def _titulo_padrao(self, payload: dict) -> str:
        if payload.get("imovel_id"):
            rows = execute(
                self.db.table("imoveis").select("endereco").eq("id", payload["imovel_id"])
            ).data
            if rows:
                return rows[0]["endereco"]
        rows = execute(
            self.db.table("clientes").select("nome").eq("id", payload["cliente_id"])
        ).data
        return rows[0]["nome"] if rows else "Novo negócio"

    # ── transições de etapa ──────────────────────────────────────────────
    def mudar_etapa(self, negocio_id: str, etapa: str) -> dict:
        negocio = self.obter(negocio_id)
        self.atualizar(negocio_id, {"etapa": etapa})

        if etapa == "producao":
            self._garantir_producao(negocio)
        elif etapa == "entregue":
            self._registrar_entrega(negocio)
        elif etapa == "recebido":
            self._dar_baixa(negocio)

        return self.obter_completo(negocio_id)

    def _garantir_producao(self, negocio: dict) -> None:
        existente = execute(
            self.db.table("producoes").select("id").eq("negocio_id", negocio["id"])
        ).data
        if existente:
            return

        captacao = execute(
            self.db.table("captacoes").select("id").eq("negocio_id", negocio["id"])
        ).data

        execute(
            self.db.table("producoes").insert(
                {
                    "org_id": self.org_id,
                    "negocio_id": negocio["id"],
                    "cliente_id": negocio.get("cliente_id"),
                    "captacao_id": captacao[0]["id"] if captacao else None,
                    "etapa": "agendado",
                    "prazo_entrega": negocio.get("prazo_entrega"),
                }
            )
        )

    def _registrar_entrega(self, negocio: dict) -> None:
        hoje = date.today()

        producoes = execute(
            self.db.table("producoes").select("id,etapa").eq("negocio_id", negocio["id"])
        ).data or []
        for producao in producoes:
            if producao["etapa"] != "entregue":
                execute(
                    self.db.table("producoes")
                    .update({"etapa": "entregue", "entregue_em": hoje.isoformat()})
                    .eq("id", producao["id"])
                )
                execute(
                    self.db.table("producao_eventos").insert(
                        {
                            "org_id": self.org_id,
                            "producao_id": producao["id"],
                            "etapa": "entregue",
                            "tipo": "transicao",
                            "comentario": "Entrega registrada pelo funil comercial",
                        }
                    )
                )

        # A entrega é o que torna o serviço faturável (spec § 7).
        ja_existe = execute(
            self.db.table("lancamentos").select("id").eq("negocio_id", negocio["id"])
        ).data
        if ja_existe:
            return

        execute(
            self.db.table("lancamentos").insert(
                {
                    "org_id": self.org_id,
                    "negocio_id": negocio["id"],
                    "cliente_id": negocio["cliente_id"],
                    "descricao": negocio.get("titulo") or "Serviço entregue",
                    "valor": float(negocio.get("valor") or 0),
                    "status": "a_faturar",
                    "data_entrega": hoje.isoformat(),
                    "vencimento": (hoje + timedelta(days=7)).isoformat(),
                    "forma_pagamento": negocio.get("forma_pagamento"),
                }
            )
        )

    def _dar_baixa(self, negocio: dict) -> None:
        """Liquida os lançamentos do negócio quando ele chega em `recebido`.

        Lançamento com cobrança emitida no provedor é pulado de propósito:
        quem diz que ele foi pago é o banco, não o movimento do card no funil.
        Sem essa guarda, um negócio faturado em três parcelas com só uma paga
        marcaria as outras duas como recebidas — e aí haveria registro
        bancário discordando do nosso.
        """
        abertos = execute(
            self.db.table("lancamentos")
            .select("id,status,provedor_cobranca_id")
            .eq("negocio_id", negocio["id"])
        ).data or []
        for lancamento in abertos:
            if lancamento.get("provedor_cobranca_id"):
                continue
            registrar_recebimento(self.db, lancamento)
