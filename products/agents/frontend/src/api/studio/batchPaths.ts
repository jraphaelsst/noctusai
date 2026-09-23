/**
 * Studio batch-upload route paths — CONTRACT.md §G items 1/2 ("build IsaIA
 * entirely through the UI" audit). Each path is a SINGLE function here and
 * nowhere else, so a backend shape change is a one-line flip, not a
 * grep-and-replace across hooks/tests.
 *
 * Confirmed against the landed backend (verb-as-segment, not `:batch`):
 *   - documents: `POST .../knowledge/{col_id}/documents/batch`, 1..100 items
 *     (422 beyond), body cap 20 MB.
 *   - skill files: `PUT .../draft/skills/{skill_id}/files/batch`, 1..50
 *     items (422 beyond), body cap 8 MB; whole-call 409 `version_immutable`
 *     when the version isn't a rascunho (not a per-item failure).
 *
 * `seg()` (percent-encodes a path segment) mirrors `hooks/studio/keys.ts`.
 */
function seg(value: string): string {
  return encodeURIComponent(value);
}

/**
 * `POST /api/studio/agents/{key}/knowledge/{col_id}/documents/batch` —
 * `{documentos:[...]}` → `{resultados, criados, atualizados, inalterados,
 * erros}`.
 */
export function knowledgeDocumentsBatchPath(agentKey: string, collectionId: string): string {
  return `/api/studio/agents/${seg(agentKey)}/knowledge/${seg(collectionId)}/documents/batch`;
}

/** Max `documentos` entries per `knowledgeDocumentsBatchPath` call (422 beyond). */
export const KNOWLEDGE_DOCUMENTS_BATCH_MAX = 100;
/** Max request-body size per `knowledgeDocumentsBatchPath` call. */
export const KNOWLEDGE_DOCUMENTS_BATCH_MAX_BYTES = 20 * 1024 * 1024;

/**
 * `PUT /api/studio/agents/{key}/draft/skills/{skill_id}/files/batch` —
 * `{arquivos:[...]}` → `{resultados, criados, atualizados, erros}`.
 */
export function skillFilesBatchPath(agentKey: string, skillId: string): string {
  return `/api/studio/agents/${seg(agentKey)}/draft/skills/${seg(skillId)}/files/batch`;
}

/** Max `arquivos` entries per `skillFilesBatchPath` call (422 beyond). */
export const SKILL_FILES_BATCH_MAX = 50;
/** Max request-body size per `skillFilesBatchPath` call. */
export const SKILL_FILES_BATCH_MAX_BYTES = 8 * 1024 * 1024;
