/**
 * The Agent SDK runtime prefix/suffix that wraps every studio agent's
 * compiled prompt at launch time — NOT part of `CompiledOut.texto`, NOT
 * covered by `hash`, and NOT counted in `tokens_estimados`. §A4/§A7's
 * promise ("the inspector shows what runs") only holds if the inspector
 * ALSO shows this: the Agent SDK unconditionally prepends a fixed identity
 * line and appends a `# Environment` block (working directory, platform,
 * model id) that the studio compiler cannot remove or influence
 * (`prompt_mode="custom"` still launches through the SDK, §A5/§E3).
 *
 * This constant mirrors `STUDIO_SYSTEM_PROMPT` in
 * `products/agents/backend/app/runtime/claude_runtime.py` (Agent SDK
 * 0.2.152's fixed preamble) — ONE place for the literal text so the
 * inspector and `/studio/prompts/:hash` never drift from what the runtime
 * finding documented. If the SDK's wording changes, this is the only file
 * to update on the frontend side.
 */

/** The SDK's fixed identity line — prepended verbatim, before the compiled text. */
export const RUNTIME_PREFIX_LINE = "You are a Claude agent, built on Anthropic's Claude Agent SDK.";

/** What the SDK's trailing `# Environment` block contains — described, not
 * reproduced: the literal values (cwd, platform, model id) are runtime-only
 * and never available to a static inspector view. */
export const RUNTIME_SUFFIX_DESCRIPTION =
  "O SDK anexa um bloco `# Environment` com diretório de trabalho, plataforma e id do modelo — gerado a cada execução, não incluído no texto compilado.";

/** A rough, documented estimate — never added to `tokens_estimados` itself,
 * shown as a separate line so the total on screen still matches the
 * server's `hash`-covered count. */
export const RUNTIME_PREAMBLE_TOKEN_ESTIMATE = 60;
