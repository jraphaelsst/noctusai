"""Quotes -- orçamentos / propostas as an L1 seed organ (roadmap E2/W4: igig `orcamento` + erp-imobiliario
`propostas` + social-wiring `atendimento_propostas`, N=3).

    draft -> sent -> viewed -> accepted | rejected | expired      (+ superseded when a newer version replaces it)

A quote is a customer (`pty_parties`) plus priced lines (optionally `itm_items`): integer-cent money computed on
the server, a per-org number shared by every version, a validity date that expires the offer lazily, and
revisions as new versions (a quote that left `draft` is frozen by the database). The customer decides on a
**signed, expiring public link** (no login); the decision is an append-only consent record (name, time, IP, the
exact sentence shown, sha256 of the terms). An accepted quote hands off through the **`QuoteAcceptHandler` seam**
(goods -> a commerce order, services -> a contract; wired by the HOST, never imported here) and can go on to
e-signature (`integrations.signature`). PDF via the seed's xhtml2pdf call site, DOCX via a host template.

Mount it from a product:

    cfg = QuotesConfig(schema="erp")                           # with_parties / with_items need those organs
    sql = quotes_migration(cfg, "erp")                         # -> migrations/0NN_quotes.sql
    app.include_router(make_quotes_router(cfg, auth_dependency, admin_dependency, resolve_context=..., get_db=...,
                                          get_handler=..., get_email=..., get_link_secret=..., accept_url=...))
    app.include_router(make_quotes_public_router(cfg, get_db=..., get_link_secret=..., get_handler=..., rate_limit=limiter.limit))
    quotes.expire_due(Scope(db, cfg, org_id))                  # optional nightly job (reads also expire lazily)
"""
from . import decisions, delivery, esign, links, public, quotes, render
from .config import QuotesConfig, QuotesContext
from .errors import QuotesError
from .handler import FakeQuoteAcceptHandler, NoopQuoteAcceptHandler, QuoteAcceptContext, QuoteAcceptHandler, QuoteConversion
from .router import make_quotes_public_router, make_quotes_router
from .sql import APPEND_ONLY_TABLES, QUOTES_TABLES, quotes_migration
from .types import Channel, ConversionStatus, ConvertTo, Decision, LineKind, QuoteStatus

__all__ = [
    "APPEND_ONLY_TABLES",
    "Channel",
    "ConversionStatus",
    "ConvertTo",
    "Decision",
    "FakeQuoteAcceptHandler",
    "LineKind",
    "NoopQuoteAcceptHandler",
    "QUOTES_TABLES",
    "QuoteAcceptContext",
    "QuoteAcceptHandler",
    "QuoteConversion",
    "QuoteStatus",
    "QuotesConfig",
    "QuotesContext",
    "QuotesError",
    "decisions",
    "delivery",
    "esign",
    "links",
    "make_quotes_public_router",
    "make_quotes_router",
    "public",
    "quotes",
    "quotes_migration",
    "render",
]
