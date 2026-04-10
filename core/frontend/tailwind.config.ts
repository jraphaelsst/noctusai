import type { Config } from "tailwindcss";
import base from "../../shared/frontend/src/design-system/tailwind.config.base";

export default {
  presets: [base],
  content: [
    "./src/**/*.{ts,tsx}",
    "../../shared/frontend/src/**/*.{ts,tsx}",
  ],
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
