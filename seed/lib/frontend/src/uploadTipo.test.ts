import { describe, expect, it } from "vitest";
import { tipoArquivoAceito } from "./uploadTipo";

describe("tipoArquivoAceito", () => {
  const pdf = ["application/pdf"];
  it("accepts a listed type", () => expect(tipoArquivoAceito({ type: "application/pdf" }, pdf)).toBe(true));
  it("leaves an extension-less file to the server sniff", () => {
    expect(tipoArquivoAceito({ type: "" }, pdf)).toBe(true);
    expect(tipoArquivoAceito({ type: "application/octet-stream" }, pdf)).toBe(true);
  });
  it("refuses a known, unaccepted type", () => expect(tipoArquivoAceito({ type: "text/plain" }, pdf)).toBe(false));
});
