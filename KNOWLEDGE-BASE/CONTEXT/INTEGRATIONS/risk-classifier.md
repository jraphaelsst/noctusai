# Risk classifier — consume-side reference

> Seed organ: `noctusai_lib.integrations.risk_classifier` (project `limiar-open-question`, slice S2). Generic: the consumer supplies the labels; first consumer is the Limiar public-ask route (`products/agents`), a therapy platform is a likely second.

## What ships

- Protocol `RiskClassifier.classify(text, *, labels: LabelSet, context=None) -> Classificacao`; Fake `FakeRiskClassifier` (lookup by normalized text hash); Real `RealRiskClassifier`; factory `make_risk_classifier`.
- `LabelSet{niveis (ordered ascending severity), sinais, descricoes}` — validated (no empties/duplicates, every label described, `indeterminado` reserved).
- `Classificacao{nivel, sinais, confianca, modelo, versao_prompt}` — NEVER contains or echoes the input.

## Fail-closed

Timeout, invalid JSON, schema mismatch (missing/extra keys), unknown label/signal, confidence below threshold (default 0.6), or any provider exception ⇒ `nivel == "indeterminado"` (`.indeterminado`), never an exception. Callers treat it as "no generation". The Fake returns it for unknown text and for scripted verdicts outside the label set.

## Real posture

`chat_completion` (seed LLM layer), model `claude-haiku-4-5` (provider `anthropic`), temperature 0, `response_format={"type":"json_object"}` (the Anthropic provider has no JSON-schema mode; the strict schema check is ours), **`cache=False`** (honoured by `llm/chat.py`: no cache read and no write — proven by a spy-backend test), the text inside a per-call random nonce block (`<<<TEXTO-{nonce}>>>`) with an instruction that it is data. `versao_prompt = "risk-v1+<sha256[:12] of the template>"`. Nothing logs text; failures log the exception TYPE only.

## Factory

`make_risk_classifier(provider=None|'fake'|'real', chat=None, ...)`; env `RISK_CLASSIFIER_PROVIDER`; unset ⇒ fake under pytest, otherwise ValueError (no silent Fake in prod). Real resolves the key via `resolve_api_key` (existing credential resolution) and raises `LLMNotConfigured` at build time if absent. `chat=` is the DI seam for tests.

See `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `projects/limiar-open-question/PROJECT.md` §5.
