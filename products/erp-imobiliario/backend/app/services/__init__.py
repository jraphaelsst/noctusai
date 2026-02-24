"""
Services layer for business logic.

This module contains service classes that encapsulate business logic,
keeping routers thin and focused on HTTP handling.
"""
from app.services.clientes_service import ClientesService
from app.services.ativos_service import AtivosService
from app.services.comissoes_service import ComissoesService

__all__ = ["ClientesService", "AtivosService", "ComissoesService"]
