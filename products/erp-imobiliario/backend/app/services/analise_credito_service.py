"""
Serviço de Análise de Crédito.

Integrates with credit bureaus (Serasa, Boa Vista) and supports manual credit entry.
Currently uses placeholder implementations for external APIs; swap with real
integrations when API contracts are available.
"""
import logging
from typing import Optional
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def consultar_serasa(cpf: str, config: Optional[dict] = None) -> dict:
    """
    Placeholder for Serasa API integration.

    When integrating with the real API, replace this function body with:
    1. Build the HTTP request using the Serasa API credentials from `config`.
    2. Send the CPF query.
    3. Parse the response into the standardized format below.

    Args:
        cpf: CPF number (11 digits, no formatting)
        config: API configuration (api_key, endpoint, etc.)

    Returns:
        Standardized credit analysis result dict.
    """
    logger.info(f"Serasa consulta (placeholder) para CPF ***{cpf[-4:]}")

    # Placeholder: return a simulated result
    return {
        "score": None,
        "status": "pendente",
        "resultado": {
            "fonte": "serasa",
            "mensagem": "Integração com Serasa pendente de configuração. "
                        "Configure as credenciais da API para ativar consultas automáticas.",
            "pendencias": [],
            "restricoes": [],
        },
        "validade": (date.today() + timedelta(days=30)).isoformat(),
    }


def consultar_boa_vista(cpf: str, config: Optional[dict] = None) -> dict:
    """
    Placeholder for Boa Vista (SCPC) API integration.

    When integrating with the real API, replace this function body with:
    1. Build the HTTP request using Boa Vista API credentials from `config`.
    2. Send the CPF query.
    3. Parse the response into the standardized format below.

    Args:
        cpf: CPF number (11 digits, no formatting)
        config: API configuration (api_key, endpoint, etc.)

    Returns:
        Standardized credit analysis result dict.
    """
    logger.info(f"Boa Vista consulta (placeholder) para CPF ***{cpf[-4:]}")

    return {
        "score": None,
        "status": "pendente",
        "resultado": {
            "fonte": "boa_vista",
            "mensagem": "Integração com Boa Vista pendente de configuração. "
                        "Configure as credenciais da API para ativar consultas automáticas.",
            "pendencias": [],
            "restricoes": [],
        },
        "validade": (date.today() + timedelta(days=30)).isoformat(),
    }


def analise_manual(cpf: str, score: Optional[int], detalhes: Optional[dict] = None) -> dict:
    """
    Process a manual credit analysis entry.

    Used when the agent enters credit data manually (e.g., from a printed report
    or phone confirmation with the bureau).

    Args:
        cpf: CPF number (11 digits)
        score: Credit score (0-1000), or None if unknown
        detalhes: Additional details about the analysis

    Returns:
        Standardized credit analysis result dict.
    """
    status = "pendente"
    recomendacao = "Análise manual registrada."

    if score is not None:
        if score >= 700:
            status = "aprovado"
            recomendacao = "Score alto — crédito aprovado. Baixo risco de inadimplência."
        elif score >= 400:
            status = "em_analise"
            recomendacao = (
                "Score médio — requer análise adicional. "
                "Recomenda-se verificar referências e comprovantes de renda."
            )
        else:
            status = "reprovado"
            recomendacao = (
                "Score baixo — crédito reprovado. "
                "Alto risco de inadimplência. Considerar garantias adicionais."
            )

    resultado = {
        "fonte": "manual",
        "score": score,
        "recomendacao": recomendacao,
        **(detalhes or {}),
    }

    return {
        "score": score,
        "status": status,
        "resultado": resultado,
        "validade": (date.today() + timedelta(days=90)).isoformat(),
    }


def executar_analise(
    cpf: str,
    nome: str,
    fonte: str,
    score_manual: Optional[int] = None,
    resultado_manual: Optional[dict] = None,
) -> dict:
    """
    Main entry point: dispatches credit analysis to the correct handler.

    Args:
        cpf: CPF number (11 digits)
        nome: Person's name
        fonte: Analysis source ('serasa', 'boa_vista', 'manual')
        score_manual: Score for manual analysis
        resultado_manual: Additional result details for manual analysis

    Returns:
        Standardized credit analysis result dict with keys:
        - score (int | None)
        - status (str)
        - resultado (dict)
        - validade (str, ISO date)
    """
    logger.info(f"Executando análise de crédito para {nome} (***{cpf[-4:]}) via {fonte}")

    if fonte == "serasa":
        return consultar_serasa(cpf)
    elif fonte == "boa_vista":
        return consultar_boa_vista(cpf)
    elif fonte == "manual":
        return analise_manual(cpf, score_manual, resultado_manual)
    else:
        logger.warning(f"Fonte desconhecida: {fonte} — usando análise manual")
        return analise_manual(cpf, score_manual, resultado_manual)
