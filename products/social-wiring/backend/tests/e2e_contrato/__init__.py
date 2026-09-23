"""SW contract-generation e2e harness — read-only, real-data-capable.

See `README.md` in this package for usage. Nothing here is collected by the
default pytest run (no `test_*.py` module touches a live database); only
`test_comparador_offline.py` is collected, and it never opens a network
connection.
"""
