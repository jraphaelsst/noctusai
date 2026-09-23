/**
 * Website client entry (contract §4). Hydrates onto whatever prerendered
 * page the browser loaded — `BrowserRouter` reads `window.location`, so it
 * always resolves the SAME route the server rendered for this exact path
 * (`entry-server.tsx` used `StaticRouter` with the identical path), which is
 * what makes `hydrateRoot` succeed without a mismatch.
 */
import { StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "./routes";
import "./styles/site.css";

const container = document.getElementById("root");

if (container) {
  hydrateRoot(
    container,
    <StrictMode>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </StrictMode>,
  );
}
