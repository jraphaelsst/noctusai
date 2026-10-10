"""`Content-Disposition: attachment` for a filename that may carry accents.

HTTP header values are latin-1 on the wire, so a raw `filename="João.zip"`
raises inside Starlette and 500s the whole download — for anyone whose name
carries an accent, which in a Brazilian product is most people. RFC 6266:
send an ASCII-folded `filename=` every client understands PLUS a
percent-encoded UTF-8 `filename*=` that every current browser prefers, so the
user still sees the accented name.

Formalized at N=3 (social-wiring certidões + matrículas carried verbatim
copies; edição de fotos a third, divergent one).
"""
from __future__ import annotations

from urllib.parse import quote

from noctusai_lib.primitives.accents import fold_accents_ascii


def attachment_disposition(filename: str, *, fallback: str = "download") -> str:
    """The header value for downloading `filename` as an attachment.

    An all-non-ASCII name folds to `""`; `fallback` replaces it, because a
    header with an empty filename is worse than a generic one (some clients
    then save under the URL path). Double quotes are dropped from the ASCII
    form so they cannot terminate the quoted string early.
    """
    ascii_name = fold_accents_ascii(filename).replace('"', "").strip() or fallback
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


__all__ = ["attachment_disposition"]
