import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // e2e/ is Playwright (its `use` fixture trips react-hooks/rules-of-hooks as a
  // false positive); those tests aren't React components, so exclude from this
  // React-oriented lint.
  { ignores: ["dist", "**/e2e/**", "**/playwright-report/**", "**/test-results/**"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": "off",
      // Legacy adoption: the fleet's product code carries many pragmatic `any`s
      // (dynamic API payloads, CSS-custom-property + react-hook-form `as any`
      // workarounds). Enforce as a non-blocking warning — visible for
      // incremental cleanup — rather than a hard error. (2026-05-22.)
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
);
