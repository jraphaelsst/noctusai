import { createProductVitestConfig } from "../../../seed/framework/frontend/vitest.config.factory";

export default createProductVitestConfig({
  setupFilesExtra: ["./src/test/setup.ts"],
});
