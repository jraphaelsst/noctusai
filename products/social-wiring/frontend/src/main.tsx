import { createRoot } from "react-dom/client";
import { validateEnv, assertSupabaseBuildEnv } from "@noctusai/lib";
import App from "./App";
import "./index.css";

validateEnv();
// W1.E7 contract: the two boot-critical VITE_SUPABASE_* vars are
// Vite-inlined at `vite build` time. An empty value here means the
// build itself was misconfigured (Docker build-args not passed in the
// image stage that runs `vite build`) — fail fast with the actionable
// message instead of rendering a blank page that throws deep in
// createProductSupabase on first auth use. Skipped under dev-autologin.
// VITE_BACKEND_API_URL is intentionally NOT asserted — it stays
// runtime-detected (apiBase) so one image serves direct/tunnel/proxy.
assertSupabaseBuildEnv();

createRoot(document.getElementById("root")!).render(<App />);
