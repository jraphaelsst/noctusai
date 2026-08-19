import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";

// `backendPort` deliberately NOT passed: the factory derives it from the
// `PRODUCTS` registry in start.sh (`p-studio:P Studio:8014:8180`), which is
// the single source of truth for product ports. It used to be hardcoded to
// 8020 — this product's PRE-absorption port, dead since migration 004 moved
// it to the house port 8014 — so the dev proxy pointed at nothing.
export default createViteConfig({ port: 8180 });
