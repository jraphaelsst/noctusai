import { createRoot } from "react-dom/client";
import { validateEnv } from "@noctusai/shared";
import App from "./App.tsx";
import "./index.css";

validateEnv();

createRoot(document.getElementById("root")!).render(<App />);
