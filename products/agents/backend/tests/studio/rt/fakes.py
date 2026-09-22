"""Test doubles shared by the BE-RT suite (real subclasses / adapters of the
product's own Fakes — never monkeypatches)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.stores.errors import NotFound
from app.stores.studio_definitions import FakeStudioDefinitionStore, SectionInput
from app.stores.studio_knowledge import StudioAgentRef
from app.studio.evals import Criterion, JudgeVerdict, parse_judge_output


class FakeStudioStore(FakeStudioDefinitionStore):
    """``FakeStudioDefinitionStore`` + the transactional
    ``replace_draft_bundle(org_id, version_id, secoes, skills)`` entry point
    the importer calls. The hardening slice ships the real method on the
    store; until it lands, this thin fallback (built on the Fake's existing
    methods) lets the importer be tested — test-only, by agreement."""

    def replace_draft_bundle(
        self, org_id: UUID, version_id: UUID, secoes: list[SectionInput], skills: list[dict[str, Any]]
    ) -> None:
        self.replace_sections(org_id, version_id, secoes)
        for sk in self.list_skills(org_id, version_id):
            self.delete_skill(org_id, sk.id)
        for s in skills:
            rec = self.create_skill(
                org_id, version_id, nome=s["nome"], descricao=s["descricao"], corpo=s["corpo"],
                ordem=s["ordem"], ativo=s["ativo"],
            )
            for a in s["arquivos"]:
                self.upsert_skill_file(org_id, rec.id, caminho=a["caminho"], titulo=a["titulo"], conteudo=a["conteudo"])


class DefinitionsAgentLookup:
    """BE-KE's routers resolve agents through ``AgentLookup``; in production
    it reads the same ``agents.agents`` table the definitions store does.
    Over Fakes, this adapter gives both the SAME rows."""

    def __init__(self, store: FakeStudioDefinitionStore) -> None:
        self._store = store

    def get_by_key(self, org_id: UUID, key: str) -> StudioAgentRef:
        a = self._store.get_agent(org_id, key)  # raises NotFound
        return StudioAgentRef(
            id=a.id, org_id=a.org_id, key=a.key, nome=a.nome, definition_mode=a.definition_mode,
            ativo=a.ativo, publicacao_limiar=a.publicacao_limiar,
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
                {"criterio": c.texto, "tipo": c.tipo, "ok": ok, "motivo": "ok" if ok else "falhou"}
                for c, ok in zip(criterios, oks)
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
    "DefinitionsAgentLookup",
    "FakeStudioStore",
    "NotFound",
    "ReadOnlyProxy",
    "ScriptedJudge",
    "WriteForbidden",
]
