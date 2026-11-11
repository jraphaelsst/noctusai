"""Catalogue adapters: what an agent can offer, behind :class:`~app.catalogos.protocolo.CatalogoOpcoes`."""
from app.catalogos.factory import CATALOGOS, CatalogoDesconhecido, CatalogoIndisponivel, catalogo_para, chaves_de_catalogo
from app.catalogos.fixture import FixtureCatalogo
from app.catalogos.imoveis_sw import ImoveisSwCatalogo
from app.catalogos.protocolo import CATALOGO_PADRAO, Busca, CatalogoOpcoes

__all__ = [
    "CATALOGOS", "CATALOGO_PADRAO", "Busca", "CatalogoDesconhecido", "CatalogoIndisponivel", "CatalogoOpcoes",
    "FixtureCatalogo", "ImoveisSwCatalogo", "catalogo_para", "chaves_de_catalogo",
]
