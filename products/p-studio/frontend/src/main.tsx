import { createRoot } from "react-dom/client";
import { validateEnv, assertSupabaseBuildEnv } from "@noctusai/lib";
import App from "./App";
import "./index.css";

validateEnv();
// W1.E7 contract (see social-wiring): the two boot-critical VITE_SUPABASE_*
// vars are Vite-inlined at `vite build` time. An empty value here means the
// build itself was misconfigured — fail fast instead of rendering a blank
// page that throws deep in createProductSupabase on first auth use. The
// product's own Dockerfile already documents this exact contract (the
// VITE_SUPABASE_* ARG/ENV block predates this file calling the assertion —
// see `products/p-studio/backend/Dockerfile`).
assertSupabaseBuildEnv();

createRoot(document.getElementById("root")!).render(<App />);
