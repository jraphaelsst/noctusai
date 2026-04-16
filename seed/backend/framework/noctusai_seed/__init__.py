"""
NoctusAI Seed Framework — structural bones for all products.

The seed is the spine of every product. All products inherit their
structural infrastructure from here. Change the seed, change all products.

Two layers:
  - seed/lib/  (noctusai_shared) = reusable code library (auth, roles, utils)
  - seed/framework/ (noctusai_seed)  = structural framework (app factory, database, deps)

Products import from both. Domain-specific code lives in the product only.
"""
from noctusai_seed.app import create_product_app
from noctusai_seed.config import ProductSettings
from noctusai_seed.database import create_database_module
from noctusai_seed.dependencies import create_dependencies

__all__ = [
    "create_product_app",
    "ProductSettings",
    "create_database_module",
    "create_dependencies",
]
