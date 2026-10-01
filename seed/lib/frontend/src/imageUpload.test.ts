import { describe, it, expect, vi, afterEach } from "vitest";
import { prepareImageForUpload } from "./imageUpload";

const MB = 1024 * 1024;

function fakeFile(name: string, type: string, bytes: number): File {
  return new File([new Uint8Array(bytes)], name, { type });
}

function installCanvas(opts: { w: number; h: number; blobBytes: number | null; ctx?: boolean }) {
  const close = vi.fn();
  const drawImage = vi.fn();
  const bitmapFn = vi.fn().mockResolvedValue({ width: opts.w, height: opts.h, close });
  vi.stubGlobal("createImageBitmap", bitmapFn);
  const canvas: any = {
    width: 0,
    height: 0,
    getContext: () => (opts.ctx === false ? null : { drawImage }),
    toBlob: (cb: (b: Blob | null) => void) =>
      cb(opts.blobBytes === null ? null : new Blob([new Uint8Array(opts.blobBytes)], { type: "image/jpeg" })),
  };
  const real = document.createElement.bind(document);
  vi.spyOn(document, "createElement").mockImplementation(((tag: string) =>
    tag === "canvas" ? canvas : real(tag)) as any);
  return { canvas, bitmapFn, drawImage };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("prepareImageForUpload", () => {
  it("never touches PDFs", async () => {
    const f = fakeFile("a.pdf", "application/pdf", 9 * MB);
    expect(await prepareImageForUpload(f)).toBe(f);
  });

  it("passes small images through", async () => {
    installCanvas({ w: 1000, h: 800, blobBytes: 10 });
    const f = fakeFile("a.png", "image/png", 1 * MB);
    expect(await prepareImageForUpload(f)).toBe(f);
  });

  it("shrinks a big PNG to a scaled JPEG keeping the stem", async () => {
    const { canvas, bitmapFn } = installCanvas({ w: 6000, h: 3000, blobBytes: 1 * MB });
    const out = await prepareImageForUpload(fakeFile("foto.doc.png", "image/png", 10 * MB));
    expect(bitmapFn).toHaveBeenCalledWith(expect.anything(), { imageOrientation: "from-image" });
    expect(canvas.width).toBe(3000);
    expect(canvas.height).toBe(1500);
    expect(out.name).toBe("foto.doc.jpg");
    expect(out.type).toBe("image/jpeg");
    expect(out.size).toBe(1 * MB);
  });

  it("keeps the original when the JPEG would be larger", async () => {
    installCanvas({ w: 2000, h: 2000, blobBytes: 5 * MB });
    const f = fakeFile("a.png", "image/png", 4 * MB);
    expect(await prepareImageForUpload(f)).toBe(f);
  });

  it("falls back to the original on decode failure", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("boom")));
    const f = fakeFile("a.jpg", "image/jpeg", 8 * MB);
    expect(await prepareImageForUpload(f)).toBe(f);
  });

  it("falls back when the canvas context is unavailable", async () => {
    installCanvas({ w: 6000, h: 6000, blobBytes: 1, ctx: false });
    const f = fakeFile("a.jpg", "image/jpeg", 8 * MB);
    expect(await prepareImageForUpload(f)).toBe(f);
  });

  it("falls back when the encoder returns null", async () => {
    installCanvas({ w: 6000, h: 6000, blobBytes: null });
    const f = fakeFile("a.jpg", "image/jpeg", 8 * MB);
    expect(await prepareImageForUpload(f)).toBe(f);
  });
});
