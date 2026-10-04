"""Python interpreter of the vendored Limiar safety pack (limiar-app ``safety/regras.json``).

Reproduces the algorithm of limiar-app ``src/safety/{normalize,triage}.ts``; EVERY constant
and pattern comes from the JSON — this module holds only the algorithm. Patterns compile
with ``re.ASCII`` (JS ``\\b``/``.`` are ASCII-only). The result carries rule ids only,
never any part of the input text.

The pack is verified against ``SOURCE.lock`` (sha256 per file) on load; a mismatch refuses.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACK_DIR = Path(__file__).parent / "limiar"
LOCK_PATH = Path(__file__).parent / "SOURCE.lock"
PACK_FILES = ("regras.json", "conformance.json")


class PackError(RuntimeError):
    """The vendored pack is missing, tampered with, or malformed."""


def verify_lock(pack_dir: Path = PACK_DIR, lock_path: Path = LOCK_PATH) -> dict[str, Any]:
    """Check every sha256 in the lock against the vendored files; return the lock."""
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackError(f"safety pack SOURCE.lock unreadable: {exc}") from exc
    files = lock.get("files")
    if not isinstance(files, dict) or not files:
        raise PackError("safety pack SOURCE.lock has no 'files' map")
    for name, expected in files.items():
        try:
            actual = hashlib.sha256((pack_dir / name).read_bytes()).hexdigest()
        except OSError as exc:
            raise PackError(f"safety pack file {name} unreadable: {exc}") from exc
        if actual != expected:
            raise PackError(
                f"safety pack file {name} does not match SOURCE.lock "
                f"(expected sha256 {expected}, got {actual}) - re-sync with noctus.dev.safety_pack_sync"
            )
    return lock


@dataclass(frozen=True)
class TriageResult:
    """Rule ids only - NEVER user text."""

    nivel: str
    sinais: tuple[str, ...]
    regras: tuple[str, ...]
    versao: str


def _squeeze(text: str) -> str:
    out: list[str] = []
    prev = ""
    for ch in text:
        if ch == prev and "a" <= ch <= "z":
            continue
        out.append(ch)
        prev = ch
    return "".join(out)


def _squeeze_pattern(source: str) -> str:
    out: list[str] = []
    prev = ""
    i = 0
    while i < len(source):
        ch = source[i]
        if ch == "\\":
            out.append(ch + (source[i + 1] if i + 1 < len(source) else ""))
            i += 2
            prev = ""
            continue
        if ch == prev and "a" <= ch <= "z":
            i += 1
            continue
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out)


class SafetyEngine:
    def __init__(self, rules: dict[str, Any]) -> None:
        try:
            self._versao: str = rules["versao"]
            n = rules["normalizacao"]
            t = rules["triagem"]
            env = rules["compilacao"]["envelope"]
            self._acentos: dict[str, str] = n["acentos"]
            self._leet: dict[str, str] = n["leet"]
            self._abrev: dict[str, str] = n["abreviacoes"]
            self._combinantes: tuple[int, int] = (n["marcas_combinantes"][0], n["marcas_combinantes"][1])
            self._marca: str = n["marca_de_frase"]
            self._re_subst = [
                (re.compile(s["padrao"], re.ASCII), s["texto"]) for s in n["substituicoes_previas"]
            ]
            self._re_soletrado = re.compile(n["soletrado"], re.ASCII)
            self._re_sep_soletrado = re.compile(n["separador_soletrado"], re.ASCII)
            self._re_pontuacao = re.compile(n["pontuacao"], re.ASCII)
            self._re_espacos = re.compile(f"(?:{n['espaco']})+", re.ASCII)
            self._re_sep_token = re.compile(n["separador_de_token"], re.ASCII)
            self._mascara: str = t["mascara"]
            self._re_mascaravel = re.compile(t["palavra_mascaravel"], re.ASCII)
            self._negadores = frozenset(t["negadores"])
            self._nivel_negado: str = t["nivel_negado"]
            self._sufixo: str = t["sufixo_negada"]
            self._ordem_nivel: dict[str, int] = t["ordem_nivel"]
            self._ordem_sinal: list[str] = t["ordem_sinal"]

            def compile_(padrao: str) -> re.Pattern[str]:
                return re.compile(env[0] + _squeeze_pattern(padrao) + env[1], re.ASCII)

            self._idiomas = [compile_(i["padrao"]) for i in rules["idiomas"]]
            self._regras = [(r, compile_(r["padrao"])) for r in rules["regras"]]
        except (KeyError, IndexError, TypeError, re.error) as exc:
            raise PackError(f"safety pack regras.json malformed: {exc!r}") from exc

    @property
    def versao(self) -> str:
        return self._versao

    # -- normalization -------------------------------------------------
    def _strip_accents(self, text: str) -> str:
        lo, hi = self._combinantes
        out: list[str] = []
        for ch in text:
            if lo <= ord(ch) <= hi:
                continue
            out.append(self._acentos.get(ch, ch))
        return "".join(out)

    def _de_leet(self, token: str) -> str:
        if not re.search("[a-z]", token) or not re.search("[0-9@]", token):
            return token
        return "".join(self._leet.get(ch, ch) for ch in token)

    def _expand(self, raw: str) -> str:
        direct = self._abrev.get(raw)
        if direct is not None:
            return _squeeze(direct)
        sq = _squeeze(raw)
        via = self._abrev.get(sq)
        if via is not None:
            return _squeeze(via)
        if len(sq) > 2 and sq[0] == "k" and sq[1] in ("e", "i"):
            return _squeeze("qu" + sq[1:])
        return sq

    def normalize(self, text: str) -> str:
        t = self._strip_accents(text.lower())
        for rx, texto in self._re_subst:
            t = rx.sub(lambda m, texto=texto: m.group(1) + texto, t)
        t = self._re_soletrado.sub(lambda m: self._re_sep_soletrado.sub("", m.group(0)), t)
        t = self._re_pontuacao.sub(f" {self._marca} ", t)
        tokens: list[str] = []
        for chunk in self._re_espacos.split(t):
            if chunk == self._marca:
                if tokens and tokens[-1] != self._marca:
                    tokens.append(self._marca)
                continue
            for raw in self._re_sep_token.split(chunk):
                tok = raw.strip("@")
                if tok:
                    tokens.append(self._expand(self._de_leet(tok)))
        while tokens and tokens[-1] == self._marca:
            tokens.pop()
        return " ".join(tokens)

    # -- triage --------------------------------------------------------
    def _mask_idioms(self, texto: str) -> str:
        def mask(m: re.Match[str]) -> str:
            return " ".join(
                self._mascara if self._re_mascaravel.search(w) else w for w in m.group(0).split(" ")
            )

        for rx in self._idiomas:
            texto = rx.sub(mask, texto)
        return texto

    def normalized_for_rules(self, text: str) -> str:
        """Matching form after idiom masking (tests only; never log it)."""
        return self._mask_idioms(self.normalize(text))

    def _negated_at(self, texto: str, index: int) -> bool:
        antes = texto[:index].rstrip(" ")
        ultima = antes[antes.rfind(" ") + 1 :]
        return ultima in self._negadores

    def triage(self, text: str) -> TriageResult:
        texto = self.normalized_for_rules(text)
        verde = TriageResult("verde", (), (), self._versao)
        if not texto:
            return verde
        hits: list[tuple[dict[str, Any], str, str]] = []
        for regra, rx in self._regras:
            plena = negada = False
            for m in rx.finditer(texto):
                if regra.get("negavel") is not False and self._negated_at(texto, m.start()):
                    negada = True
                else:
                    plena = True
                if plena:
                    break
            if plena:
                hits.append((regra, regra["nivel"], regra["id"]))
            elif negada:
                hits.append((regra, self._nivel_negado, regra["id"] + self._sufixo))
        specific = [h for h in hits if not h[0].get("rede")]
        valid = specific or hits
        if not valid:
            return verde
        nivel = "verde"
        for _, n, _ in valid:
            if self._ordem_nivel[n] > self._ordem_nivel[nivel]:
                nivel = n
        present = {h[0]["sinal"] for h in valid}
        return TriageResult(
            nivel,
            tuple(s for s in self._ordem_sinal if s in present),
            tuple(sorted({h[2] for h in valid})),
            self._versao,
        )


def load_engine(pack_dir: Path = PACK_DIR, lock_path: Path = LOCK_PATH) -> SafetyEngine:
    """Verify the lock, then build the engine from the vendored ``regras.json``."""
    verify_lock(pack_dir, lock_path)
    try:
        rules = json.loads((pack_dir / "regras.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackError(f"safety pack regras.json unreadable: {exc}") from exc
    return SafetyEngine(rules)
