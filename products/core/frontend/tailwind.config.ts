import type { Config } from "tailwindcss";
import base from "../../../seed/lib/frontend/src/design-system/tailwind.config.base";

export default {
  presets: [base],
  content: [
    "./src/**/*.{ts,tsx}",
    "../../../seed/lib/frontend/src/**/*.{ts,tsx}",
  ],
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
