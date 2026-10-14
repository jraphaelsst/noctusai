"""One-shot importers that move a host's legacy finance data into the finance organ (integer cents).

Each importer is: a PURE mapping (`plan_import`), a reconciliation (`reconcile`, to the cent, refuses on any
mismatch) and an idempotent writer (`apply_plan`, only through the organ's own services). Nothing here is
called by a router; the entry point is an MCP tool (`noctus.dev.finance_import_<host>`).
"""
