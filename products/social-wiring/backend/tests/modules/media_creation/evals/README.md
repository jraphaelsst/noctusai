# media_creation eval cases

Shape-eval harness for the 3-stage LLM pipeline (storyboard → prompts → copy).
Each case is a JSON file under `cases/` that pins the LLM output (so the
test is deterministic in CI) and asserts the persisted artifact's shape.

Auto-skips when `cases/` is empty — landing the first JSON un-skips the
harness.

## Case schema

```json
{
  "name": "post1-condominios-premium",
  "brand_kit": {
    "name": "Granja Premium",
    "persona": "Voice: editorial, calm, premium.",
    "design_system": "Variant: premium. Warm dark earth tones.",
    "default_lang": "pt-BR"
  },
  "post": {
    "title": "Three condos in Cotia",
    "idea": "Three premium condos under R$1.5M near São Paulo",
    "format": "carousel",
    "variant": "premium",
    "slide_count": 3
  },
  "expected": {
    "storyboard": { "...verbatim LLM output, matches generate_storyboard contract..." },
    "image_prompts": [
      { "slide_n": 1, "nano_banana": "...", "galilai": "...", "midjourney": "..." }
    ],
    "copy": { "caption": "...", "hashtags": ["#x", "#y"], "alt_text_per_slide": ["...", "..."], "first_comment": "..." }
  },
  "asserts": {
    "min_slides": 3,
    "max_slides": 8,
    "min_caption_chars": 200,
    "min_hashtags": 3,
    "expect_cta_keyword": "DM"
  }
}
```

The `expected.*` blocks are returned verbatim by the stubbed LLM (via
`AsyncMock` on `noctusai_lib.integrations.llm.chat_completion`). The
`asserts.*` keys gate the persisted shape. All `asserts.*` keys are
optional — omit any to skip that check.

## Adding a case

1. Drop `<name>.json` here.
2. Re-run:
   `pytest products/social-wiring/backend/tests/modules/media_creation/evals/test_eval_loop.py -v`
3. The parametrized run picks it up automatically.

## Source of cases

Each case is a shape-eval fixture: pinned LLM outputs (storyboard /
prompts / copy) + asserted shape invariants. Cases originated from the
validated carousels produced by the **media-creator prototype**
(consolidated into this module 2026-05-20, prototype retired 2026-05-24 —
see `KB § PATTERNS/svg-render-mode.md`). Add a new case by curating a
real generation run into a `<name>.json` here; no external project is
required.
