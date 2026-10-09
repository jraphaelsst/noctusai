import fs from "fs";
import os from "os";
import path from "path";
import { describe, expect, it } from "vitest";
import { resolveProductSlug } from "../vite.config.factory";

function repoWith(registryRow: string | null) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "slug-"));
  if (registryRow) {
    fs.writeFileSync(
      path.join(root, "start.sh"),
      `# BEGIN_PRODUCTS_REGISTRY\nPRODUCTS=(\n  "${registryRow}"\n)\n# END_PRODUCTS_REGISTRY\n`,
    );
  }
  const dir = path.join(root, "products", "dir-name", "frontend");
  fs.mkdirSync(dir, { recursive: true });
  return { root, dir };
}

describe("resolveProductSlug", () => {
  it("prefers the start.sh registry row matching the frontend port", () => {
    const { root, dir } = repoWith("reg-slug:Reg Name:8999:8998");
    expect(resolveProductSlug(dir, root, 8998)).toBe("reg-slug");
  });
  it("falls back to the products/<slug>/frontend directory name", () => {
    const { root, dir } = repoWith(null);
    expect(resolveProductSlug(dir, root, 1)).toBe("dir-name");
  });
  it("is undefined when neither source applies", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "slug-"));
    expect(resolveProductSlug(root, root, 1)).toBeUndefined();
  });
});
