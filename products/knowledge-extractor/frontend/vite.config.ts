import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";

// Single-container model: the production/container build sets
// VITE_SAME_ORIGIN=1, so the API base is the runtime origin
// (window.location.origin) and the backend-port lookup never runs.
// `backendPort: 8012` (the start.sh registry backend port for
// knowledge-extractor) is supplied explicitly so the two-port/native
// dev path (no VITE_SAME_ORIGIN) also resolves without depending on the
// frontend `port` matching a registry frontend-port row.
export default createViteConfig({ port: 8150, backendPort: 8012 });
