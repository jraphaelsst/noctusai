"""Guard for a `banco` value that carries agência/conta typed as free text.

Legacy card rows had e.g. "Itaú (341) Ag. 1234 CC 56789-0" in `banco` with
`agencia`/`conta` NULL; the migration-251 backfill copied it to the registry.
The bank NAME/code is public; the agência/conta digits are financial PII.

Detection only — the digits are NEVER parsed into agencia/conta (owner rule:
store only what the document/user states, in the right field).
"""
from __future__ import annotations

import re
from typing import Any, Optional

_PADRAO_CONTA = re.compile(
    r"(\bag\b\.?|ag[eê]ncia|\bc/c\b|\bcc\b|\bconta\b|\bc\.c\.?|\d{4,})",
    re.IGNORECASE,
)


def banco_tem_dados_de_conta(banco: Any) -> bool:
    return bool(_PADRAO_CONTA.search(str(banco or "")))


def banco_saneado(banco: Any) -> Optional[str]:
    """Only the bank name/code: text before the first agência/conta token."""
    texto = str(banco or "").strip()
    if not texto:
        return None
    m = _PADRAO_CONTA.search(texto)
    if m:
        texto = texto[: m.start()]
    return texto.strip(" \t-,;:/.") or None
