"""Parity: every social-wiring accent fold migrated onto the seed
`noctusai_lib.primitives.accents` returns byte-identical output to the private
copy it replaced — stored slugs, Content-Disposition names and match keys
must not move.

Each entry holds the call site's function source VERBATIM as it stood before
the migration (AST-extracted). It is executed inside a COPY of its own
module's namespace (so module helpers like `_texto` / `_strip_marcadores`
resolve exactly as they did) and compared against the live function.
"""
from __future__ import annotations

import importlib
import unicodedata
from urllib.parse import quote

import pytest

from noctusai_lib.primitives.content_disposition import attachment_disposition

CORPUS = [
    "",
    " ",
    "São Paulo/SP",
    "FILIAÇÃO",
    "Ação  de   Cobrança\n\tJoão",
    "Gilson Tangerino — CoreStudio",
    "Nós no Limiar",
    "Rose Oliveira | Nutricionista Oncológica",
    "nei_nunes",
    "certidoes_João_da_Silva_2026.zip",
    'arquivo "com aspas" ação.pdf',
    "Rua Três, nº 81 – 1ª andar, apto 2º",
    "Ｒｕａ １２３ ﬁnal x²",
    "Straße Øresund Æble Łódź",
    "CARTÓRIO DO 2º OFÍCIO DE REGISTRO DE IMÓVEIS | CNS 12.345-6",
    "Livro 2 - Registro Geral 1º Registro de Imóveis de São Paulo",
    "Área total 250,00 m² — terreno.",
    "emoji 😀 e ç",
    "MARIA DA CONCEIÇÃO\r\nJOSÉ",
    "\u00a0nbsp\u2003em-space",
]

FROZEN = [
    (
        'app.modules.card_hub.contrato_gerador.citacao_matricula',
        '_dobrar',
        'def _dobrar(texto: str) -> str:\n    sem = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()\n    return re.sub(r"\\s+", " ", sem.lower()).strip()',
    ),
    (
        'app.modules.card_hub.contrato_gerador.derivacao',
        '_dobra_acentos',
        'def _dobra_acentos(texto: str) -> str:\n    """Upper-case, accent-stripped — same fold `parse_brl`\'s BRL grammar\n    does not need but this module\'s free-text matching does (comparing a\n    CRM street name / hunting an "área ... m²" phrase inside prose)."""\n    sem_acento = "".join(\n        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)\n    )\n    return sem_acento.upper()',
    ),
    (
        'app.modules.certidoes.aprendizado',
        '_sem_acento',
        'def _sem_acento(texto: str) -> str:\n    return "".join(\n        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)\n    )',
    ),
    (
        'app.modules.certidoes.routers.certidoes',
        '_content_disposition',
        'def _content_disposition(filename: str) -> str:\n    """An attachment header that survives an accented filename.\n\n    🔴 NOT COSMETIC, AND NOT HYPOTHETICAL. HTTP header values are latin-1 on\n    the wire, so returning `filename="certidoes_João_da_Silva_...zip"` raises\n    inside Starlette and the whole response 500s. The download therefore failed\n    for anyone whose name carries an accent — which in a Brazilian real-estate\n    product is most people. The ERP original built the header the same way and\n    had the same latent defect; it is fixed here rather than ported.\n\n    RFC 6266: an ASCII-folded `filename=` that any client understands, PLUS a\n    percent-encoded UTF-8 `filename*=` that every current browser prefers — so\n    the accented name is what the user actually sees, and nothing breaks if it\n    is not understood.\n    """\n    folded = (\n        unicodedata.normalize("NFKD", filename)\n        .encode("ascii", "ignore")\n        .decode("ascii")\n        .replace(\'"\', "")\n        .strip()\n    )\n    # An all-non-ASCII name folds to "" — a header with an empty filename is\n    # worse than a generic one, because some clients save it as the URL path.\n    ascii_name = folded or "download"\n    return (\n        f\'attachment; filename="{ascii_name}"; \'\n        f"filename*=UTF-8\'\'{quote(filename, safe=\'\')}"\n    )',
    ),
    (
        'app.modules.imovel_hub.campos_extraidos_service',
        '_norm_texto',
        'def _norm_texto(valor: Any) -> str:\n    texto = unicodedata.normalize("NFKD", str(valor))\n    texto = "".join(c for c in texto if not unicodedata.combining(c))\n    return _WS.sub(" ", texto).strip().casefold().rstrip(".")',
    ),
    (
        'app.modules.matriculas.router',
        '_content_disposition',
        'def _content_disposition(filename: str) -> str:\n    """An attachment header that survives an accented filename.\n\n    Copied from `certidoes/routers/certidoes.py::_content_disposition`\n    (identical bug, identical fix — an unescaped accented `filename=` raises\n    inside Starlette and 500s the whole download) rather than imported: the\n    two modules share no common parent this platform lets them both import\n    from within THIS slice\'s scope. Flagged as `scoped-improvement:` in\n    S3\'s delivery note — a third caller makes this N=3, the DRY recurrence\n    rule\'s MUST-formalize threshold.\n    """\n    folded = (\n        unicodedata.normalize("NFKD", filename)\n        .encode("ascii", "ignore")\n        .decode("ascii")\n        .replace(\'"\', "")\n        .strip()\n    )\n    ascii_name = folded or "download"\n    return (\n        f\'attachment; filename="{ascii_name}"; \'\n        f"filename*=UTF-8\'\'{quote(filename, safe=\'\')}"\n    )',
    ),
    (
        'app.modules.matriculas.titulo_service',
        '_sem_acento',
        'def _sem_acento(texto: str) -> str:\n    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()',
    ),
    (
        'app.modules.media_creation.services.branding_service',
        'slugify',
        'def slugify(text: str) -> str:\n    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")\n    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")\n    return slug or "branding"',
    ),
    (
        'app.services.divergencia_resolucao',
        '_sem_acento_upper',
        'def _sem_acento_upper(valor: str) -> str:\n    decomposed = unicodedata.normalize("NFKD", valor)\n    sem_acento = "".join(c for c in decomposed if not unicodedata.combining(c))\n    return re.sub(r"\\s+", " ", sem_acento.upper()).strip()',
    ),
    (
        'app.services.identidade_service',
        'normalize_name',
        'def normalize_name(raw: Optional[str]) -> str:\n    """`lower(unaccent(trim(collapse_whitespace(name))))`, plus punctuation and\n    origin-marker folding — the Python mirror of the §3 predicate\'s\n    normalization. Returns `""` (never `None`) for a nameless input, so\n    callers can test truthiness directly.\n\n    🔴 WIDENED 2026-08-25, FROM THE LIVE QUEUE, NOT FROM THEORY\n    ------------------------------------------------------------\n    351 groups were sitting in the review queue. Reading them showed that a\n    large share were not disagreements about WHO the person is at all:\n\n      `alex sandro` / `alex sandro*`        — a trailing asterisk\n      `nei nunes`   / `nei_nunes`           — an underscore for a space\n      `ricardo`     / `ricardo.santos`      — a dot for a space\n      `hp luiza`    / `luiza`               — the source pasted onto the name\n      `morgana`     / `retono morgana`      — same\n      `ju cantowitz +` / `juliana cantowitz`\n\n    Every one of those is the same letters with something non-alphabetic\n    around them, and every one cost a human two clicks. Punctuation now folds\n    to whitespace and origin markers are dropped from the ends, which moved\n    106 of the 351 groups into the auto-mergeable classes (C1/C2) — measured\n    against the live database, not estimated.\n\n    WHAT THIS DELIBERATELY DOES NOT DO\n    ----------------------------------\n    No fuzzy matching, no edit distance, no phonetics. `elisabeth`/`elizabeth`\n    and `erick`/`erik` are almost certainly the same person, and\n    `fernanda`/`lucilene ferreira alves` is almost certainly two people\n    sharing a phone — and NOTHING in the letters distinguishes those two cases\n    from each other. Guessing there merges strangers\' records. Those 245 stay\n    with a human, which is what the review queue is for.\n    """\n    if not raw:\n        return ""\n    # A social handle\'s tagline is not part of the name: "Rose Oliveira |\n    # Nutricionista Oncológica" and "Silas Brito | Estilo inglês Móveis" are\n    # the same people as "Rose Oliveira" and "Silas". Keep what precedes the\n    # bar — but ONLY when something precedes it, or "|Maria Veiga" would\n    # normalize to nothing and turn a named row into a nameless one.\n    if "|" in raw and raw.split("|", 1)[0].strip():\n        raw = raw.split("|", 1)[0]\n    collapsed = " ".join(raw.split())\n    decomposed = unicodedata.normalize("NFKD", collapsed)\n    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))\n    # Punctuation to whitespace, not to nothing: `nei_nunes` must become two\n    # tokens, matching `nei nunes`, rather than one glued `neinunes`.\n    folded = "".join(c if (c.isalnum() or c.isspace()) else " " for c in stripped)\n    tokens = _strip_marcadores(folded.lower().split())\n    return " ".join(tokens)',
    ),
    (
        'app.services.identificadores',
        'cartorio_normalizado',
        'def cartorio_normalizado(valor: Any) -> str:\n    """The serventia\'s NAME as comparison text: accents/case/whitespace\n    folded, the book header and the CNS fragment removed, separators (`|`,\n    stray dashes) collapsed. `""` for an empty value."""\n    texto = _texto(valor)\n    if not texto:\n        return ""\n    texto = _LIVRO_CABECALHO.sub(" ", texto)\n    texto = _CNS_FRAGMENTO.sub(" ", texto)\n    decomposto = unicodedata.normalize("NFKD", texto)\n    texto = "".join(c for c in decomposto if not unicodedata.combining(c)).upper()\n    texto = texto.replace("|", " ")\n    texto = re.sub(r"\\s+", " ", texto).strip(" -–—,.")\n    return texto',
    ),
]


REPLACED_BY = {
    ("app.modules.certidoes.routers.certidoes", "_content_disposition"): attachment_disposition,
    ("app.modules.matriculas.router", "_content_disposition"): attachment_disposition,
}


@pytest.mark.parametrize("mod,func,source", FROZEN, ids=[f"{m.rsplit('.', 1)[-1]}.{f}" for m, f, _ in FROZEN])
def test_site_output_unchanged(mod, func, source):
    module = importlib.import_module(mod)
    ns = dict(vars(module))
    # stdlib names the frozen bodies used; the migrated modules may no longer import them
    ns.update(unicodedata=unicodedata, quote=quote)
    exec(compile(source, f"<frozen {mod}.{func}>", "exec"), ns)
    old = ns[func]
    # A site whose private copy was DELETED (not rewired) is compared against
    # the seed function that replaced it.
    new = getattr(module, func, None) or REPLACED_BY[(mod, func)]
    for text in CORPUS:
        assert new(text) == old(text), (mod, func, text)
