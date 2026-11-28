"""Diretor de Edição -- the approval -> Reel production seam (project ``diretor-edicao-reels``).

Structure only. Every audiovisual decision (storytelling, scene composition, the generator, the render) is a NAMED SEAM
(:mod:`portas`) whose Real implementation is an open owner decision: only the Fakes exist, and :func:`fabrica.make_adaptadores`
refuses (never silently degrades) until they are decided. Nothing here imports a vendor or runs a renderer.

* :mod:`passos`    -- the stages of a production run, as data, + the outcome enum + the graph builder.
* :mod:`portas`    -- the four seams (style, scene planner, media generator, assembler) as Protocols.
* :mod:`fakes`     -- deterministic doubles, flagged ``sintetico``.
* :mod:`fabrica`   -- Fake-or-refuse factory.
* :mod:`validacao` -- the decision-free guards (plan anchored by word id, no new text, measured checks).
* :mod:`handlers`  -- the step handlers over the ports (seed ``StepRegistry``).
* :mod:`gatilho`   -- the trigger: headline AND roteiro approved => one idempotent production request.

Contract + decisions: ``products/social-wiring/projects/diretor-edicao-reels/``. Imports are deliberately NOT re-exported
here: ``criacao_rotas`` imports :mod:`passos`, so this package init must stay import-free.
"""
