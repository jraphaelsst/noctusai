"""Agent Studio — versioned, UI-managed agent definitions
(contract: ``products/agents/projects/agent-studio-isaia/CONTRACT.md``).

``models`` holds the pure bundle dataclasses the compiler consumes plus the
cross-slice seams (§J2: ``EvalGate`` / ``KnowledgeCatalog``); ``compiler``
holds THE one ``compile_prompt`` (§A4) — the runtime, the inspector and the
publish step all call it, nobody re-implements composition.
"""
from __future__ import annotations

from app.studio.compiler import compile_prompt
from app.studio.models import (
    ClientBundle,
    ClientEntryData,
    CollectionSummary,
    CompiledPrompt,
    CompileInput,
    CompileWarning,
    EvalGate,
    FakeEvalGate,
    FakeKnowledgeCatalog,
    GateRun,
    KnowledgeCatalog,
    ManifestOrigin,
    ManifestSection,
    OnDemandItem,
    SectionData,
    SkillData,
    SkillFileRef,
    VersionBundle,
)

__all__ = [
    "ClientBundle",
    "ClientEntryData",
    "CollectionSummary",
    "CompileInput",
    "CompileWarning",
    "CompiledPrompt",
    "EvalGate",
    "FakeEvalGate",
    "FakeKnowledgeCatalog",
    "GateRun",
    "KnowledgeCatalog",
    "ManifestOrigin",
    "ManifestSection",
    "OnDemandItem",
    "SectionData",
    "SkillData",
    "SkillFileRef",
    "VersionBundle",
    "compile_prompt",
]
