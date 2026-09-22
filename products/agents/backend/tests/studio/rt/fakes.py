"""Test doubles shared by the BE-RT suite (real subclasses / adapters of the
product's own Fakes — never monkeypatches)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.stores.errors import NotFound
from app.studio.evals import Criterion, JudgeVerdict, parse_judge_output


def publish(defs: Any, org_id: UUID, agent: Any, version_id: UUID, user_id: UUID, *, catalog: Any = None) -> Any:
    """Publish a draft the way the publish route does (M1): compile it, stamp
    the hash, then flip under ``expected_hash`` with the proof-of-use text —
    here via an override reason (no eval run)."""
    from app.stores.studio_knowledge import FakeStudioKnowledgeStore
    from app.studio.bundles import compile_version
    from app.studio.catalog import StoreKnowledgeCatalog

    catalog = catalog or StoreKnowledgeCatalog(FakeStudioKnowledgeStore())
    draft = defs.get_version(org_id, version_id)
    compiled = compile_version(defs, catalog, org_id, agent, draft)
    defs.set_compiled_hash(org_id, version_id, compiled.hash)
    return defs.publish_version(
        org_id, version_id, user_id, None, "publicação de teste do BE-RT",
        expected_hash=compiled.hash, texto=compiled.texto, manifest=compiled.manifest_json(),
    )


class ScriptedJudge:
    """A :class:`~app.studio.evals.Judge` that answers with canned RAW judge
    text, parsed by the production strict parser. ``answers`` maps a case
    ``entrada`` to either a raw string, a list of booleans (one per
    criterion — rendered as valid judge JSON, with a bogus judge ``score``
    the runner must ignore), or an Exception to raise."""

    def __init__(self, answers: dict[str, Any] | None = None, default: Any = True) -> None:
        self.answers = dict(answers or {})
        self.default = default
        self.calls: list[dict[str, Any]] = []

    async def judge(
        self, *, org_id: UUID, entrada: str, contexto: str | None, criterios: list[Criterion],
        rubrica: str | None, saida: str,
    ) -> JudgeVerdict:
        self.calls.append({"entrada": entrada, "saida": saida, "criterios": criterios})
        answer = self.answers.get(entrada, self.default)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, str):
            return parse_judge_output(answer, criterios)
        oks = [answer] * len(criterios) if isinstance(answer, bool) else list(answer)
        import json

        raw = json.dumps({
            "veredito": [
                {"n": i, "ok": ok, "motivo": "ok" if ok else "falhou"}
                for i, (c, ok) in enumerate(zip(criterios, oks), 1)
            ],
            "score": 0.99,
            "notas": "notas do juiz",
        })
        return parse_judge_output(raw, criterios)


class WriteForbidden(AssertionError):
    pass


class ReadOnlyProxy:
    """Wraps a store; any method outside ``reads`` raises — proves a dry run
    performs ZERO writes."""

    def __init__(self, inner: Any, reads: set[str]) -> None:
        self._inner = inner
        self._reads = reads
        self.touched: list[str] = []

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr
        if name not in self._reads:
            def _refuse(*a: Any, **k: Any) -> Any:
                raise WriteForbidden(f"dry_run called write method {name}")
            return _refuse
        self.touched.append(name)
        return attr


__all__ = [
    "publish",
    "NotFound",
    "ReadOnlyProxy",
    "ScriptedJudge",
    "WriteForbidden",
]
