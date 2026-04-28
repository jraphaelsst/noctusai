import type { Config } from "tailwindcss";
import base from "../../../seed/frontend/lib/src/design-system/tailwind.config.base";

export default {
  presets: [base],
  content: [
    "./src/**/*.{ts,tsx}",
    "../../../seed/frontend/lib/src/**/*.{ts,tsx}",
  ],
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
