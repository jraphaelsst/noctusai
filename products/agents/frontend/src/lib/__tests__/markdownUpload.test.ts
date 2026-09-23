/**
 * `markdownUpload.ts` — front matter parsing + filename/caminho derivation
 * for the Studio multi-file uploaders (CONTRACT.md §G items 1/2).
 */
import { describe, expect, it } from "vitest";
import {
  caminhoFromFile,
  firstMarkdownHeading,
  formatFileSize,
  parseFrontMatter,
  sanitizeCaminho,
  slugFromFilename,
  slugify,
  titleFromFilename,
} from "@/lib/markdownUpload";

describe("parseFrontMatter", () => {
  it("parses a front matter block and strips quoted values", () => {
    const raw = [
      "---",
      "slug: au-00-comece-aqui",
      "titulo: Método 01 — Audience",
      "tipo: indice",
      'proveniencia: "Curso Audience — aula 1"',
      "---",
      "# Método 01",
      "",
      "Conteúdo aqui.",
    ].join("\n");

    const { data, content } = parseFrontMatter(raw);

    expect(data).toEqual({
      slug: "au-00-comece-aqui",
      titulo: "Método 01 — Audience",
      tipo: "indice",
      proveniencia: "Curso Audience — aula 1",
    });
    expect(content).toBe("# Método 01\n\nConteúdo aqui.");
  });

  it("falls back to an empty data map and the raw text when there is no front matter block", () => {
    const raw = "# Só markdown\n\nSem front matter nenhum.";
    const { data, content } = parseFrontMatter(raw);
    expect(data).toEqual({});
    expect(content).toBe(raw);
  });

  it("does not treat a stray '---' mid-document as a front matter delimiter", () => {
    const raw = "# Título\n\nTexto antes\n\n---\n\nTexto depois de um separador visual.";
    const { data, content } = parseFrontMatter(raw);
    expect(data).toEqual({});
    expect(content).toBe(raw);
  });

  it("ignores a malformed line inside the block instead of throwing", () => {
    const raw = ["---", "titulo: Ok", "isto não é uma linha chave:valor válida sem dois pontos no formato certo", "---", "corpo"].join(
      "\n",
    );
    const { data, content } = parseFrontMatter(raw);
    expect(data.titulo).toBe("Ok");
    expect(content).toBe("corpo");
  });
});

describe("firstMarkdownHeading", () => {
  it("returns the first '# heading' line", () => {
    expect(firstMarkdownHeading("intro\n# Título Real\nresto")).toBe("Título Real");
  });

  it("returns null when there is no heading", () => {
    expect(firstMarkdownHeading("apenas texto, sem cabeçalho")).toBeNull();
  });

  it("does not match a deeper '## heading' — only a top-level '# heading'", () => {
    expect(firstMarkdownHeading("## Subtítulo\n# Título")).toBe("Título");
  });
});

describe("slugify / slugFromFilename / titleFromFilename", () => {
  it("slugifies accents, spaces and punctuation", () => {
    expect(slugify("Método 01 — Audience!")).toBe("metodo-01-audience");
  });

  it("never returns an empty slug", () => {
    expect(slugify("@@@")).toBe("documento");
  });

  it("derives a slug from a filename, stripping the extension", () => {
    expect(slugFromFilename("au-00-comece-aqui.md")).toBe("au-00-comece-aqui");
    expect(slugFromFilename("Aula 1 - Introdução.markdown")).toBe("aula-1-introducao");
  });

  it("derives a human title from a filename", () => {
    expect(titleFromFilename("tom-de-voz_final.md")).toBe("tom de voz final");
  });
});

describe("sanitizeCaminho / caminhoFromFile", () => {
  it("lowercases and legalizes characters, collapsing '..' runs", () => {
    expect(sanitizeCaminho("References/Tom De Voz..md")).toBe("references/tom-de-voz.md");
  });

  it("strips a leading non-alphanumeric so the path always starts [a-z0-9]", () => {
    expect(sanitizeCaminho("/references/x.md")).toBe("references/x.md");
  });

  it("preserves a references/ prefix when the file carries a relative path with one", () => {
    const file = new File(["conteudo"], "tom-de-voz.md", { type: "text/markdown" });
    Object.defineProperty(file, "webkitRelativePath", { value: "isaia/references/tom-de-voz.md" });
    expect(caminhoFromFile(file)).toBe("references/tom-de-voz.md");
  });

  it("falls back to the bare filename when there is no references/ segment", () => {
    const file = new File(["conteudo"], "Tom-De-Voz.md", { type: "text/markdown" });
    expect(caminhoFromFile(file)).toBe("tom-de-voz.md");
  });

  it("falls back to the bare filename when webkitRelativePath is present but has no references/ segment", () => {
    const file = new File(["conteudo"], "tom-de-voz.md", { type: "text/markdown" });
    Object.defineProperty(file, "webkitRelativePath", { value: "isaia/skills/tom-de-voz.md" });
    expect(caminhoFromFile(file)).toBe("tom-de-voz.md");
  });
});

describe("formatFileSize", () => {
  it("formats bytes, KB and MB", () => {
    expect(formatFileSize(500)).toBe("500 B");
    expect(formatFileSize(1536)).toBe("1.5 KB");
    expect(formatFileSize(1024 * 1024 * 2)).toBe("2.0 MB");
  });
});
