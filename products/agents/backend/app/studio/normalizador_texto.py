"""THE one place that decides which characters are invisible/dangerous and how obfuscated text is flattened for the
security detectors (pure functions, stdlib only, no IO).

Three consumers, one definition:

* :func:`caractere_proibido` -- the universal "no control / zero-width / bidi / tag / private-use" rule of an org's
  spec VALUE (``studio/spec_formatos``). Rejects.
* :func:`limpar` -- the lead's inbound text at the channel schema boundary: the same invisible characters
  (Cf, the U+E0000-E007F tag block used for "ASCII smuggling", variation-selector tails, stray controls) are
  STRIPPED, so what is stored, shown to the model and scanned is what a human would read.
* :func:`esqueleto` -- a throw-away copy for the detectors ONLY (never stored, never shown): confusable
  letters mapped to Latin, accents/case folded, spaced-out letters/digits collapsed, "ponto com" style links and
  "arroba" e-mails rewritten, so ``i g n o r e``, ``reserva one ponto com ponto br`` and a Cyrillic ``о`` all meet
  the same patterns as the plain text.
* :func:`tem_caractere_oculto` -- the OUTPUT side: a reply carrying any of these characters is blocked.
"""
from __future__ import annotations

# The implementation moved to the seed organ (noctusai_lib.integrations.llm.guardrails.obfuscation): one definition of
# the invisible-character rule and the detector skeleton for every product. Re-exported so agents' imports are unchanged.
from noctusai_lib.integrations.llm.guardrails.obfuscation import (  # noqa: F401
    caractere_proibido,
    esqueleto,
    limpar,
    tem_caractere_oculto,
)

__all__ = ["caractere_proibido", "esqueleto", "limpar", "tem_caractere_oculto"]
