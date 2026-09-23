/**
 * Client-side parsing shared by the Studio multi-file uploaders (Conhecimento
 * `KnowledgeTab.tsx`, Skills `SkillsTab.tsx` — CONTRACT.md §G items 1/2 of the
 * "build IsaIA entirely through the UI" audit).
 *
 * Front matter is the minimal YAML-ish block the audit's example uses:
 *
 *   ---
 *   slug: au-00-comece-aqui
 *   titulo: Método 01 — Audience
 *   tipo: indice
 *   proveniencia: "Curso Audience — aula 1"
 *   ---
 *   <conteúdo markdown>
 *
 * Scalar `chave: valor` lines land in `data`; a value's surrounding quotes are
 * stripped so `proveniencia: "Curso Audience — aula 1"` reads as the bare
 * string. ONE level of nesting is read into `nested` — a key with an empty
 * value followed by indented `  subchave: valor` lines — because structured
 * provenance is written that way:
 *
 *   proveniencia:
 *     origem: "Método Kênia — curadoria"
 *     referencia: "00-comece-aqui.md"
 *
 * Deeper nesting and lists are not read. A file
 * with no front matter block falls all the way through: `data` is `{}` and
 * `content` is the raw text, unchanged — the caller derives slug/título from
 * the filename/first heading instead of erroring.
 */

export interface ParsedFrontMatter {
  data: Record<string, string>;
  /** One-level maps: `chave:` (empty value) followed by indented `sub: valor` lines. */
  nested: Record<string, Record<string, string>>;
  content: string;
}

const FRONT_MATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n?([\s\S]*)$/;
const FRONT_MATTER_LINE_RE = /^([A-Za-z0-9_]+):[ \t]*(.*)$/;
const FRONT_MATTER_NESTED_LINE_RE = /^[ \t]+([A-Za-z0-9_]+):[ \t]*(.*)$/;

function unquote(raw: string): string {
  const value = raw.trim();
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if (first === '"' && last === '"') {
      // Double-quoted values are JSON strings when written by a tool (escapes
      // like \" or \n); fall back to the bare slice for hand-written text.
      try {
        const parsed: unknown = JSON.parse(value);
        if (typeof parsed === "string") return parsed;
      } catch {
        // not valid JSON — a hand-written quoted value; the bare slice below is the answer
      }
      return value.slice(1, -1);
    }
    if (first === "'" && last === "'") return value.slice(1, -1);
  }
  return value;
}

export function parseFrontMatter(raw: string): ParsedFrontMatter {
  const match = FRONT_MATTER_RE.exec(raw);
  if (!match) return { data: {}, nested: {}, content: raw };
  const [, block, rest] = match;
  const data: Record<string, string> = {};
  const nested: Record<string, Record<string, string>> = {};
  let openMap: string | null = null;
  for (const line of block.split(/\r?\n/)) {
    const sub = FRONT_MATTER_NESTED_LINE_RE.exec(line);
    if (sub) {
      if (openMap === null) continue;
      const value = unquote(sub[2]);
      if (value) (nested[openMap] ??= {})[sub[1]] = value;
      continue;
    }
    const m = FRONT_MATTER_LINE_RE.exec(line);
    if (!m) {
      openMap = null;
      continue;
    }
    const value = unquote(m[2]);
    if (value) {
      data[m[1]] = value;
      openMap = null;
    } else {
      openMap = m[1];
    }
  }
  return { data, nested, content: rest };
}

/** First `# heading` line of markdown content, or `null` if there is none. */
export function firstMarkdownHeading(content: string): string | null {
  const m = /^#[ \t]+(.+)$/m.exec(content);
  return m ? m[1].trim() : null;
}

/** Filename without its extension — `"au-00-comece-aqui.md"` → `"au-00-comece-aqui"`. */
export function stripExtension(fileName: string): string {
  const base = fileName.split("/").pop() ?? fileName;
  return base.replace(/\.[^./]+$/, "");
}

/** Filename (no extension) → a human-ish title: dashes/underscores → spaces. */
export function titleFromFilename(fileName: string): string {
  const base = stripExtension(fileName).replace(/[-_]+/g, " ").trim();
  return base || fileName;
}

/**
 * Any string → a `SLUG_RE`-compliant slug (`/^[a-z0-9]+(-[a-z0-9]+)*$/`,
 * `api/studio/types.ts`): lowercase, accents stripped, every run of
 * non-alphanumerics collapsed to one `-`, no leading/trailing `-`. Never
 * returns an empty string — an unslugifiable input (e.g. all punctuation)
 * falls back to `"documento"` rather than producing an invalid empty slug.
 */
export function slugify(input: string): string {
  const s = input
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return s || "documento";
}

/** Filename (no extension) → a `SLUG_RE`-compliant slug. */
export function slugFromFilename(fileName: string): string {
  return slugify(stripExtension(fileName));
}

/**
 * Any string → a `CAMINHO_RE`-compliant path
 * (`/^[a-z0-9][a-z0-9._/-]*$/`, plus no `..`, `api/studio/types.ts`):
 * lowercase, every disallowed character collapsed to `-`, `..` runs
 * collapsed to a single `.`, and any leading non-alphanumeric stripped (the
 * pattern requires the FIRST character be `[a-z0-9]`). Never returns an
 * empty string.
 */
export function sanitizeCaminho(path: string): string {
  let out = path.toLowerCase().replace(/[^a-z0-9._/-]/g, "-");
  while (out.includes("..")) out = out.replace(/\.\./g, ".");
  out = out.replace(/^[^a-z0-9]+/, "");
  return out || "arquivo";
}

/** Where a skill's reference files live (Agent Skills layout) — the path a skill body cites. */
export const SKILL_REFERENCES_DIR = "references/";

/**
 * A dropped/picked `File`'s skill-file `caminho` (item 2 of the audit).
 * Precedence: an explicit front-matter `caminho` → the `references/…` tail of
 * `webkitRelativePath` (folder pick) → `references/<filename>`. The default
 * carries the prefix because a skill body cites its files as
 * `references/<nome>.md` and `ler_arquivo_skill` matches `caminho` EXACTLY —
 * a picked file (the common case: no relative path) stored as the bare
 * filename is unreachable under the path the skill names. Always run through
 * `sanitizeCaminho` so it is `CAMINHO_RE`-legal.
 */
export function caminhoFromFile(file: File, frontMatterCaminho?: string): string {
  if (frontMatterCaminho?.trim()) return sanitizeCaminho(frontMatterCaminho.trim());
  const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath || "";
  const idx = relative.indexOf(SKILL_REFERENCES_DIR);
  const path = idx >= 0 ? relative.slice(idx) : `${SKILL_REFERENCES_DIR}${file.name}`;
  return sanitizeCaminho(path);
}

/** Human-readable file size — `1536` → `"1.5 KB"`. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

/** Reads a `File`'s contents as text — promise wrapper around `FileReader`. */
export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error ?? new Error(`Não foi possível ler o arquivo ${file.name}.`));
    reader.readAsText(file);
  });
}
