"""Curated CRUD tools for the high-traffic Omie resources.

The generic seam (`omie.call.*`) already reaches all 461 methods. This
module exists because "reachable" is not "ergonomic": an agent asked to
"list overdue receivables for Acme" should not first have to discover
that the method is `ListarContasReceber`, that it lives on
`/financas/contareceber/`, and that its record array is named
`conta_receber_cadastro`.

So the ~25 resources that carry most real work get first-class
`list / get / upsert / delete` tools with pagination already wired.

**The table is the code.** Adding a resource is one `Resource(...)` row —
the handlers and descriptors are generated. Hand-writing four
near-identical modules per resource is exactly the N≥3 duplication the
DRY rule forbids, and it would drift from the catalog the moment Omie
renames a method.

Every method name below was read out of the harvested catalog
(`data/catalog.json.gz`), not guessed — and `tests/test_smoke.py`
re-verifies each one against that catalog, so a typo or an upstream
rename fails the suite instead of failing live in front of a user.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mcp.server import Server
from mcp.types import Tool

from ..api import client_for
from ._common import guarded, schema


@dataclass(frozen=True)
class Resource:
    """One curated Omie resource → up to four generated tools."""

    ns: str                      # tool namespace: omie.<ns>.<action>
    path: str                    # endpoint path, relative to base_url
    label: str                   # human description of the entity
    list_call: Optional[str] = None
    get_call: Optional[str] = None
    upsert_call: Optional[str] = None
    delete_call: Optional[str] = None
    key_hint: str = ""           # which identifier fields `get`/`delete` expect
    filter_hint: str = ""        # useful filters for `list`
    lgpd: bool = False           # carries personal data (CPF/CNPJ/address/phone)
    extra: tuple[str, ...] = field(default_factory=tuple)  # notable extra methods


RESOURCES: tuple[Resource, ...] = (
    # --- geral / cadastros ---
    Resource(
        ns="clientes", path="/geral/clientes/", label="customers, suppliers and carriers",
        list_call="ListarClientes", get_call="ConsultarCliente",
        upsert_call="UpsertCliente", delete_call="ExcluirCliente",
        key_hint="codigo_cliente_omie (int) OR codigo_cliente_integracao (str) OR cnpj_cpf",
        filter_hint="clientesFiltro: cnpj_cpf, razao_social, nome_fantasia, cidade, "
                    "inativo ('S'/'N'), tags; apenas_importado_api ('S'/'N')",
        lgpd=True, extra=("ListarClientesResumido", "UpsertClienteCpfCnpj", "IncluirClientesPorLote"),
    ),
    Resource(
        ns="produtos", path="/geral/produtos/", label="product catalog entries",
        list_call="ListarProdutos", get_call="ConsultarProduto",
        upsert_call="UpsertProduto", delete_call="ExcluirProduto",
        key_hint="codigo_produto (int) OR codigo_produto_integracao (str) OR codigo (SKU)",
        filter_hint="filtrar_apenas_omiepdv, filtrar_por_data_de/ate, "
                    "apenas_importado_api, inativo",
        extra=("ListarProdutosResumido", "IncluirProdutosPorLote"),
    ),
    Resource(
        ns="categorias", path="/geral/categorias/", label="financial categories (chart of accounts)",
        list_call="ListarCategorias", get_call="ConsultarCategoria",
        key_hint="codigo (str)",
    ),
    Resource(
        ns="departamentos", path="/geral/departamentos/", label="departments / cost centres",
        list_call="ListarDepartamentos", get_call="ConsultarDepartamento",
        delete_call="ExcluirDepartamento", key_hint="codigo (str)",
    ),
    Resource(
        ns="projetos", path="/geral/projetos/", label="projects",
        list_call="ListarProjetos", get_call="ConsultarProjeto",
        upsert_call="UpsertProjeto", delete_call="ExcluirProjeto",
        key_hint="codigo (int) OR codInt (str)",
    ),
    Resource(
        ns="vendedores", path="/geral/vendedores/", label="sales reps",
        list_call="ListarVendedores", get_call="ConsultarVendedor",
        upsert_call="UpsertVendedor", delete_call="ExcluirVendedor",
        key_hint="codigo (int) OR codInt (str)", lgpd=True,
    ),
    Resource(
        ns="empresas", path="/geral/empresas/", label="companies on the account",
        list_call="ListarEmpresas", get_call="ConsultarEmpresa",
        key_hint="codigo_empresa (int) OR codigo_empresa_integracao (str)",
    ),
    Resource(
        ns="contas_correntes", path="/geral/contacorrente/", label="bank / cash accounts",
        list_call="ListarContasCorrentes", get_call="ConsultarContaCorrente",
        upsert_call="UpsertContaCorrente", delete_call="ExcluirContaCorrente",
        key_hint="nCodCC (int) OR cCodCCInt (str)",
        extra=("ListarResumoContasCorrentes", "PesquisarContaCorrente"),
    ),
    # --- finanças ---
    Resource(
        ns="contas_pagar", path="/financas/contapagar/", label="accounts payable",
        list_call="ListarContasPagar", get_call="ConsultarContaPagar",
        upsert_call="UpsertContaPagar", delete_call="ExcluirContaPagar",
        key_hint="codigo_lancamento_omie (int) OR codigo_lancamento_integracao (str)",
        filter_hint="filtrar_por_data_de/ate, filtrar_por_status "
                    "(ABERTO/ATRASADO/PAGO/...), filtrar_apenas_titulos_a_pagar, "
                    "codigo_cliente_fornecedor",
        extra=("LancarPagamento", "CancelarPagamento", "IncluirContaPagarPorLote"),
    ),
    Resource(
        ns="contas_receber", path="/financas/contareceber/", label="accounts receivable",
        list_call="ListarContasReceber", get_call="ConsultarContaReceber",
        upsert_call="UpsertContaReceber", delete_call="ExcluirContaReceber",
        key_hint="codigo_lancamento_omie (int) OR codigo_lancamento_integracao (str)",
        filter_hint="filtrar_por_data_de/ate, filtrar_por_status "
                    "(ABERTO/ATRASADO/RECEBIDO/...), codigo_cliente_fornecedor",
        extra=("LancarRecebimento", "CancelarRecebimento", "ConciliarRecebimento",
               "DesconciliarRecebimento", "CancelarContaReceber"),
    ),
    Resource(
        ns="lancamentos_cc", path="/financas/contacorrentelancamentos/",
        label="current-account entries",
        list_call="ListarLancCC", get_call="ConsultaLancCC",
        delete_call="ExcluirLancCC", key_hint="nCodLanc (int) OR cCodIntLanc (str)",
    ),
    Resource(
        ns="extrato", path="/financas/extrato/", label="bank statement lines",
        list_call="ListarExtrato",
        filter_hint="nCodCC (account), dPeriodoInicial / dPeriodoFinal (dd/mm/yyyy)",
    ),
    Resource(
        ns="pix", path="/financas/pix/", label="PIX charges",
        list_call="ListarPix", get_call="ObterPix",
        key_hint="nCodTitulo (int) OR cCodIntTitulo (str)",
        extra=("GerarPix", "GerarQrCodePix", "CancelarPix", "ObterStatusPix"),
    ),
    # --- vendas / faturamento ---
    Resource(
        ns="pedidos_venda", path="/produtos/pedido/", label="sales orders",
        list_call="ListarPedidos", get_call="ConsultarPedido",
        delete_call="ExcluirPedido",
        key_hint="numero_pedido (str) OR codigo_pedido (int) OR codigo_pedido_integracao",
        filter_hint="filtrar_por_data_de/ate, filtrar_por_etapa, "
                    "filtrar_apenas_pedidos_com_nf, codigo_cliente",
        extra=("IncluirPedido", "AlterarPedidoVenda", "TrocarEtapaPedido",
               "StatusPedido", "DevolverPedido", "SimularImpostos"),
    ),
    Resource(
        ns="pedidos_compra", path="/produtos/pedidocompra/", label="purchase orders",
        list_call="PesquisarPedCompra", get_call="ConsultarPedCompra",
        upsert_call="UpsertPedCompra", delete_call="ExcluirPedCompra",
        key_hint="nCodPed (int) OR cCodIntPed (str)",
    ),
    Resource(
        ns="notas_fiscais", path="/produtos/nfconsultar/", label="issued NF-e invoices",
        list_call="ListarNF", get_call="ConsultarNF",
        key_hint="nIdNF (int) OR nNF (invoice number) + cSerie",
        filter_hint="dEmiInicial / dEmiFinal (dd/mm/yyyy), cnpj_cpf, nCodCli, tpAmb",
    ),
    Resource(
        ns="ordens_producao", path="/produtos/op/", label="production orders",
        list_call="ListarOrdemProducao", get_call="ConsultarOrdemProducao",
        upsert_call="UpsertOrdemProducao", delete_call="ExcluirOrdemProducao",
        key_hint="nCodOP (int) OR cCodIntOP (str)",
        extra=("ConcluirOrdemProducao", "ReverterOrdemProducao"),
    ),
    # --- estoque ---
    Resource(
        ns="estoque", path="/estoque/consulta/", label="stock positions and movements",
        list_call="ListarPosEstoque",
        filter_hint="nIdProduto, dDataPosicao (dd/mm/yyyy), codigo_local_estoque",
        extra=("PosicaoEstoque", "ListarMovimentoEstoque", "MovimentoEstoque",
               "ListarSaldoPendente"),
    ),
    Resource(
        ns="estoque_ajustes", path="/estoque/ajuste/", label="stock adjustments",
        list_call="ListarAjusteEstoque", delete_call="ExcluirAjusteEstoque",
        key_hint="nCodAjuste / codigo_ajuste",
        extra=("IncluirAjusteEstoque", "AlterarEstoqueMinimo"),
    ),
    Resource(
        ns="estoque_locais", path="/estoque/local/", label="stock locations",
        list_call="ListarLocaisEstoque",
    ),
    # --- serviços ---
    Resource(
        ns="servicos", path="/servicos/servico/", label="service catalog entries",
        list_call="ListarCadastroServico", get_call="ConsultarCadastroServico",
        upsert_call="UpsertCadastroServico", delete_call="ExcluirCadastroServico",
        key_hint="nCodServ (int) OR cCodIntServ (str)",
    ),
    Resource(
        ns="ordens_servico", path="/servicos/os/", label="service orders (OS)",
        list_call="ListarOS", get_call="ConsultarOS", delete_call="ExcluirOS",
        key_hint="nCodOS (int) OR cCodIntOS (str) OR cNumOS",
        filter_hint="dDtPrevisaoDe/Ate, cEtapa, nCodCli",
        extra=("IncluirOS", "AlterarOS", "TrocarEtapaOS", "StatusOS"),
    ),
    Resource(
        ns="contratos", path="/servicos/contrato/", label="service contracts",
        list_call="ListarContratos", get_call="ConsultarContrato",
        upsert_call="UpsertContrato",
        key_hint="nCodCtr (int) OR cCodIntCtr (str)",
    ),
    Resource(
        ns="nfse", path="/servicos/nfse/", label="issued NFS-e service invoices",
        list_call="ListarNFSEs",
        filter_hint="dtEmissaoDe / dtEmissaoAte (dd/mm/yyyy), nCodCli",
    ),
    # --- CRM ---
    Resource(
        ns="crm_contas", path="/crm/contas/", label="CRM accounts",
        list_call="ListarContas", get_call="ConsultarConta",
        upsert_call="UpsertConta", delete_call="ExcluirConta",
        key_hint="nCod (int) OR cCodInt (str)", lgpd=True,
    ),
    Resource(
        ns="crm_oportunidades", path="/crm/oportunidades/", label="CRM opportunities (deals)",
        list_call="ListarOportunidades", get_call="ConsultarOportunidade",
        upsert_call="UpsertOportunidade", delete_call="ExcluirOportunidade",
        key_hint="nCodOp (int) OR cCodIntOp (str)",
        filter_hint="nCodConta, nCodFase, dDtPrevisaoDe/Ate",
    ),
    Resource(
        ns="crm_contatos", path="/crm/contatos/", label="CRM contacts",
        list_call="ListarContatos", get_call="ConsultarContato",
        upsert_call="UpsertContato", delete_call="ExcluirContato",
        key_hint="nCod (int) OR cCodInt (str)", lgpd=True,
    ),
    Resource(
        ns="crm_tarefas", path="/crm/tarefas/", label="CRM tasks",
        list_call="ListarTarefas", get_call="ConsultarTarefa",
        upsert_call="UpsertTarefa", delete_call="ExcluirTarefa",
        key_hint="nCodTarefa (int) OR cCodIntTarefa (str)",
        extra=("CalendarioTarefas",),
    ),
    # --- contador ---
    Resource(
        ns="documentos_fiscais", path="/contador/xml/", label="fiscal document XMLs",
        list_call="ListarDocumentos",
        filter_hint="nPagina, dDtIni / dDtFim (dd/mm/yyyy), cModelo (55/65/NFSe)",
    ),
)


def _lgpd_note(r: Resource) -> str:
    return (
        " LGPD: records carry personal data (CPF/CNPJ, addresses, phones) — "
        "handle accordingly; this server does not persist responses."
        if r.lgpd else ""
    )


def _make_list(r: Resource):
    async def handler(args: dict) -> dict:
        async def run():
            c = client_for(args.get("environment"))
            out = await c.paginate(
                r.path, r.list_call, args.get("filters") or {},
                page_size=int(args.get("page_size") or 50),
                max_pages=int(args.get("max_pages") or 5),
                max_records=args.get("max_records"),
            )
            return {"environment": c.env.name, "call": r.list_call,
                    "endpoint": r.path, **out}
        return await guarded(run)
    return handler


def _make_get(r: Resource):
    async def handler(args: dict) -> dict:
        async def run():
            c = client_for(args.get("environment"))
            return {"environment": c.env.name, "call": r.get_call,
                    "record": await c.call(r.path, r.get_call, args.get("key") or {})}
        return await guarded(run)
    return handler


def _make_write(r: Resource, call: str, action: str):
    async def handler(args: dict) -> dict:
        async def run():
            c = client_for(args.get("environment"))
            return {
                "environment": c.env.name, "call": call, "action": action,
                "result": await c.call(
                    r.path, call, args.get("data") or args.get("key") or {},
                    confirm=bool(args.get("confirm")),
                ),
            }
        return await guarded(run)
    return handler


def _build() -> tuple[dict, list[Tool]]:
    handlers: dict = {}
    tools: list[Tool] = []
    for r in RESOURCES:
        extras = (f" Related methods on this endpoint (via omie.call.invoke): "
                  f"{', '.join(r.extra)}." if r.extra else "")
        if r.list_call:
            name = f"omie.{r.ns}.list"
            handlers[name] = _make_list(r)
            tools.append(Tool(
                name=name,
                description=(
                    f"List {r.label} from Omie ({r.list_call} on {r.path}). "
                    f"Auto-paginates (Omie caps 100/page) and reports `truncated` "
                    f"when more pages remain."
                    + (f" Useful filters — {r.filter_hint}." if r.filter_hint else "")
                    + _lgpd_note(r) + extras
                ),
                inputSchema=schema({
                    "filters": {"type": "object", "description":
                                "Method params passed through verbatim (filters, date "
                                "ranges). See omie.catalog.describe_method for the full schema."},
                    "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
                    "max_pages": {"type": "integer", "default": 5, "minimum": 1,
                                  "description": "Page budget; result reports `truncated` if hit."},
                    "max_records": {"type": "integer", "description": "Optional hard cap on records."},
                }),
            ))
        if r.get_call:
            name = f"omie.{r.ns}.get"
            handlers[name] = _make_get(r)
            tools.append(Tool(
                name=name,
                description=(
                    f"Fetch one of {r.label} from Omie ({r.get_call} on {r.path}). "
                    f"Key: {r.key_hint or 'see omie.catalog.describe_method'}."
                    + _lgpd_note(r)
                ),
                inputSchema=schema({
                    "key": {"type": "object", "description":
                            f"Identifier object. {r.key_hint or 'See omie.catalog.describe_method.'}"},
                }, required=["key"]),
            ))
        if r.upsert_call:
            name = f"omie.{r.ns}.upsert"
            handlers[name] = _make_write(r, r.upsert_call, "upsert")
            tools.append(Tool(
                name=name,
                description=(
                    f"Create or update one of {r.label} in Omie ({r.upsert_call} on "
                    f"{r.path}). WRITE — requires confirm=true, and is refused "
                    f"outright on a readonly environment."
                    + _lgpd_note(r)
                ),
                inputSchema=schema({
                    "data": {"type": "object", "description":
                             "Full record payload. Get the exact schema + a live "
                             f"example from omie.catalog.describe_method(call='{r.upsert_call}')."},
                }, required=["data"], confirm=True),
            ))
        if r.delete_call:
            name = f"omie.{r.ns}.delete"
            handlers[name] = _make_write(r, r.delete_call, "delete")
            tools.append(Tool(
                name=name,
                description=(
                    f"Delete one of {r.label} in Omie ({r.delete_call} on {r.path}). "
                    f"DESTRUCTIVE and irreversible — Omie has no undo. Requires "
                    f"confirm=true; refused on a readonly environment. "
                    f"Key: {r.key_hint or 'see omie.catalog.describe_method'}."
                ),
                inputSchema=schema({
                    "key": {"type": "object", "description":
                            f"Identifier object. {r.key_hint or ''}"},
                }, required=["key"], confirm=True),
            ))
    return handlers, tools


HANDLERS, _TOOLS = _build()


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return list(_TOOLS)


__all__ = ["RESOURCES", "Resource", "HANDLERS", "register", "tool_descriptors"]
