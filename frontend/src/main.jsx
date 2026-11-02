import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles/index.css";
import { initTheme } from "./services/theme";
import { registerServiceWorker } from "./services/pwa";

initTheme();
registerServiceWorker();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
