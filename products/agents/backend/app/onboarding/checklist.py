"""OUR onboarding checklist: what a new real-estate client tells us so its contextualised assistant (built on
``sdr-base``) can go live. One row per item, numbered in the order of the checklist blocks (identity, operations,
qualification, catalogue, handoff, sale, rental, pace).

Each item names WHERE its answer lands (:class:`Destino`): an org spec key (agents), a social-wiring operational
setting, or a human step (credentials / approvals the interview cannot perform). Pure data, no IO.
The human-readable twin is ``products/agents/projects/onboarding/CHECKLIST.md`` (a test keeps them in step).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["CHECKLIST", "Destino", "Item", "NIVEIS", "OPERACOES", "item_por_numero", "itens_aplicaveis", "ordem_entrevista"]

NIVEIS = ("R", "C", "O")  # required | conditional on the operations answer | optional (has a default)
OPERACOES = ("compra", "locacao", "administrativo", "captacao")
Kind = Literal["spec", "sw", "humano"]


@dataclass(frozen=True)
class Destino:
    kind: Kind
    #: spec key | SW setting id | the human step's name.
    alvo: str
    #: the SW route that takes the value when it exists today (informational; the report carries it).
    rota: str | None = None


@dataclass(frozen=True)
class Item:
    n: int
    bloco: str
    nivel: str
    titulo: str
    pergunta: str
    destino: Destino
    #: what the interview proposes when the client has no preference (``None`` = no default, must be answered).
    padrao: str | None = None
    #: a conditional item applies only when the operations answer contains one of these.
    quando: tuple[str, ...] = ()


def _spec(k: str) -> Destino:
    return Destino("spec", k)


def _sw(k: str, rota: str | None = None) -> Destino:
    return Destino("sw", k, rota)


def _h(k: str) -> Destino:
    return Destino("humano", k)


_I = Item
CHECKLIST: tuple[Item, ...] = (
    # A - identity and compliance
    _I(1, "A", "R", "Nome comercial", "Qual é o nome comercial da imobiliária?", _spec("nome_imobiliaria")),
    _I(2, "A", "R", "Nome do assistente", "Como o assistente deve se apresentar?", _sw("agente_nome"), "Julia"),
    _I(3, "A", "R", "CNPJ", "Qual é o CNPJ?", _spec("cnpj_oficial")),
    _I(4, "A", "R", "CRECI-J", "Qual é o CRECI da pessoa jurídica?", _spec("creci_j")),
    _I(5, "A", "R", "Domínios oficiais", "Quais são o site e os portais oficiais?", _spec("dominios_permitidos")),
    _I(6, "A", "R", "Aviso de privacidade",
       "Qual é o endereço do aviso de privacidade (gerado dos itens 1 a 4 e aprovado pelo dono)?", _spec("aviso_privacidade_url")),
    _I(7, "A", "O", "Mostrar o atendente humano", "O assistente pode citar o nome do atendente humano?",
       _sw("mostrar_atendente"), "não"),
    _I(8, "A", "O", "Perfil do WhatsApp", "Descrição, sobre, logo, endereço e e-mail do perfil do WhatsApp.",
       _h("perfil_whatsapp"), "texto gerado pela NoctusAI"),
    # B - operations and coverage
    _I(9, "B", "R", "Operações atendidas", "O assistente atende compra, locação, administrativo e/ou captação (donos)?",
       _spec("operacoes_atendidas")),
    _I(10, "B", "C", "Título do profissional", "Como chamar o profissional de cada operação?", _spec("titulo_profissional"),
       "Corretor", ("compra", "locacao", "captacao")),
    _I(11, "B", "R", "Regiões atendidas", "Quais regiões a imobiliária atende?", _spec("regioes_atendidas")),
    _I(12, "B", "O", "Regiões adjacentes", "Quais regiões vizinhas também aceita?", _spec("regioes_adjacentes")),
    _I(13, "B", "O", "Sobre a região", "Diferenciais, escolas e acessos que valem citar.", _spec("informacoes_regiao")),
    _I(14, "B", "R", "Horário de atendimento", "Em quais dias e horários a equipe humana atende?", _spec("horario_atendimento")),
    _I(15, "B", "R", "Retorno do humano", "Como descrever o retorno da equipe depois da transferência?", _spec("prazo_retorno_humano")),
    # C - qualification
    _I(16, "C", "R", "Lead pronto", "O que define um lead pronto para o corretor, em cada operação?", _spec("criterio_lead_pronto"),
       "operação + faixa de preço"),
    _I(17, "C", "O", "Perguntas extras",
       "Até 5 perguntas extras (nome, bairro, quartos, vagas, prazo de mudança, pets, financiamento).", _spec("perguntas_extras")),
    _I(18, "C", "O", "Mínimo para ofertar imóveis", "O que precisa saber antes de mostrar imóveis?", _spec("minimo_para_ofertar"),
       "operação + faixa de preço + região"),
    _I(19, "C", "O", "Captação", "Dono de imóvel vira lead ou só avisa a equipe?",
       _sw("envio_captacoes", "PUT /api/julia/envio/politicas"), "notificar"),
    # D - catalogue and property information
    _I(20, "D", "R", "Fonte do catálogo", "De onde vêm os imóveis (CRM ou XML) e qual a credencial?", _h("fonte_catalogo")),
    _I(21, "D", "R", "Endereço completo", "Pode enviar o endereço completo ou só o bairro?", _sw("politica_endereco")),
    _I(22, "D", "O", "IPTU", "Pode informar o IPTU?", _sw("politica_iptu"), "não"),
    _I(23, "D", "O", "Campanhas", "Imóveis ou empreendimentos de campanha atuais.", _h("imoveis_campanha")),
    # E - handoff and contacts
    _I(24, "E", "R", "Destino do lead pronto", "Para quem vai o lead pronto (equipe, distribuição, usuário do CRM)?",
       _sw("destino_lead_pronto", "PUT /api/julia/envio/regras")),
    _I(25, "E", "R", "Contatos por setor",
       "Quem atende administrativo, financeiro, jurídico e parcerias (setor, finalidade, nome, telefone)?", _spec("contatos_oficiais")),
    _I(26, "E", "R", "Destino no CRM", "Qual CRM recebe os leads e o envio é automático?", _h("crm_destino")),
    _I(27, "E", "O", "Leads frios e WhatsApp inválido", "Enviar ao CRM leads frios e WhatsApp inválido? Depois de quanto tempo?",
       _sw("envio_frios_invalido", "PUT /api/julia/envio/politicas"), "sim, após 30 minutos"),
    # F - sale (conditional on purchase)
    _I(28, "F", "C", "Financiamento", "A imobiliária acompanha financiamento? Quais serviços?", _spec("conhecimento_venda"), None, ("compra",)),
    _I(29, "F", "O", "Custos da compra", "Custos a informar (ITBI, registro...).", _spec("conhecimento_venda"), None, ("compra",)),
    _I(30, "F", "O", "Documentos de compra", "Documentos pessoais, de renda e de endereço.", _spec("conhecimento_venda"), None, ("compra",)),
    _I(31, "F", "O", "Permuta", "Aceita permuta?", _spec("conhecimento_venda"), None, ("compra",)),
    # G - rental (conditional on rental)
    _I(32, "G", "C", "Garantias", "Garantias aceitas e detalhes (caução, seguro, fiador, título).", _spec("conhecimento_locacao"),
       None, ("locacao",)),
    _I(33, "G", "O", "Prazos de contrato", "Prazos residencial e comercial.", _spec("conhecimento_locacao"), None, ("locacao",)),
    _I(34, "G", "O", "Multa rescisória", "Multa e isenção na rescisão.", _spec("conhecimento_locacao"), None, ("locacao",)),
    _I(35, "G", "O", "Documentos de locação", "Documentos exigidos.", _spec("conhecimento_locacao"), None, ("locacao",)),
    _I(36, "G", "O", "Chaves e assinatura", "Política de chaves e assinatura (digital ou física).", _spec("conhecimento_locacao"),
       None, ("locacao",)),
    # H - pace and after-service
    _I(37, "H", "O", "Reengajamento", "Quando lembrar e quando encerrar um lead que parou de responder?",
       _sw("reengajamento", "PUT /api/julia/reengajamento/config"), "lembrete 15 min, final 4 h"),
    _I(38, "H", "O", "Recesso", "Datas de recesso e a mensagem do período.", _sw("recesso", "PUT /api/julia/conhecimento/{secao}")),
    _I(39, "H", "O", "Pré-agendamento de visitas", "O assistente agenda visitas ou passa para o corretor?", _sw("visitas"),
       "passa para o corretor"),
    _I(40, "H", "O", "Link de avaliação", "Link de avaliação no Google.", _sw("avaliacao_google")),
    _I(41, "H", "O", "Pesquisa de satisfação", "Enviar pesquisa de satisfação?", _sw("pesquisa", "PUT /api/julia/envio/politicas"), "não"),
)

_POR_N = {i.n: i for i in CHECKLIST}
_RANK = {"R": 0, "C": 1, "O": 2}


def item_por_numero(n: int) -> Item | None:
    return _POR_N.get(n)


def itens_aplicaveis(operacoes: set[str] | None) -> tuple[Item, ...]:
    """The items that apply to a client attending ``operacoes`` (``None`` = item 9 not answered yet: every item
    stays, the interviewer asks 9 first)."""
    if operacoes is None:
        return CHECKLIST
    return tuple(i for i in CHECKLIST if not i.quando or operacoes & set(i.quando))


def ordem_entrevista(operacoes: set[str] | None) -> tuple[Item, ...]:
    """Interview order: required, then conditional, then optional; within a level the checklist order. Item 9 (the
    operations) leads, because it decides which conditional items exist at all."""
    itens = itens_aplicaveis(operacoes)
    return tuple(sorted(itens, key=lambda i: (i.n != 9, _RANK[i.nivel], i.n)))
