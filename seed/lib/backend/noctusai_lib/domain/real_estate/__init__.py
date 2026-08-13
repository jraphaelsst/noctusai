"""Real estate domain — pure value objects + helpers.

Public surface:

Value objects:
    `PropertyData`

Functions:
    `build_youtube_metadata`, `imovel_to_property_data`,
    `validate_product_code`, `extract_product_code`, `find_product_codes`

Constants:
    `PRODUCT_CODE_PATTERN` (anchored, for validation),
    `PRODUCT_CODE_SCAN_PATTERN` (word-bounded, for free-text extraction)

Lifted 2026-05-20 from
``products/social-wiring/backend/app/services/crm_service.py``
via ``social-wiring-vista-seed-lift``. The Vista REST transport sits
under ``noctusai_lib.integrations.vista`` (Protocol + Fake + Real +
factory); this module holds the cross-CRM domain shape so other
adapters (other tenants, other CRMs) map to/from the same vocabulary.
"""

from noctusai_lib.domain.real_estate.imovel import (
    CARACTERISTICA_COLLISIONS,
    Corretor,
    Imovel,
    ImovelPage,
    caracteristica_slug,
    clean_text,
    derive_finalidades,
    normalize_place_name,
    parse_area,
    parse_caracteristicas,
    parse_corretores,
    parse_count,
    parse_date,
    parse_money,
    parse_sim_nao,
)
from noctusai_lib.domain.real_estate.metadata import (
    build_youtube_metadata,
    imovel_to_property_data,
)
from noctusai_lib.domain.real_estate.types import PropertyData
from noctusai_lib.domain.real_estate.validators import (
    PRODUCT_CODE_PATTERN,
    PRODUCT_CODE_SCAN_PATTERN,
    extract_product_code,
    find_product_codes,
    validate_product_code,
)

__all__ = [
    "PRODUCT_CODE_PATTERN",
    "PRODUCT_CODE_SCAN_PATTERN",
    "PropertyData",
    # The canonical property model + its wire-coercion contract.
    # `PropertyData` stays the narrow YouTube-metadata carrier; `Imovel` is
    # the full listing. Both are domain shapes — neither is a Vista shape.
    "CARACTERISTICA_COLLISIONS",
    "Corretor",
    "Imovel",
    "ImovelPage",
    "caracteristica_slug",
    "clean_text",
    "derive_finalidades",
    "normalize_place_name",
    "parse_area",
    "parse_caracteristicas",
    "parse_corretores",
    "parse_count",
    "parse_date",
    "parse_money",
    "parse_sim_nao",
    "build_youtube_metadata",
    "imovel_to_property_data",
    "extract_product_code",
    "find_product_codes",
    "validate_product_code",
]
