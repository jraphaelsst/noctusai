import { createRoot } from "react-dom/client";
import { validateEnv } from "@noctusai/lib";
import App from "./App";
import "./styles.css";

validateEnv();

createRoot(document.getElementById("root")!).render(<App />);
